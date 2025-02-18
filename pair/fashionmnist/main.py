"""
Example:
    python main.py --msg bs64-e80-lr001-path8-seg5-zdim1024-scale0-1
"""


import argparse
import os
import logging
import datetime
import torch
import torch.nn as nn
import torch.nn.parallel
import torch.backends.cudnn as cudnn
import torch.optim
import torch.utils.data
import torch.utils.data.distributed
from torch.utils.data import DataLoader
from torch.optim.lr_scheduler import CosineAnnealingLR
import numpy as np
from torchvision.datasets.mnist import FashionMNIST, MNIST
from torchvision import transforms
import torchvision.utils as vutils
from tqdm import tqdm
import models as models
import matplotlib.pyplot as plt
from helper import mkdir_p, save_model, save_args, set_seed, Logger


def parse_args():
    """Parameters"""
    parser = argparse.ArgumentParser('training')
    parser.add_argument('-c', '--checkpoint', type=str, metavar='PATH',
                        help='path to save checkpoint (default: checkpoint)')
    parser.add_argument('--msg', type=str, help='message after checkpoint')
    parser.add_argument('--model', default='VectorMNISTAE', help='model name [default: pointnet_cls]')
    # training
    parser.add_argument('--batch_size', type=int, default=64, help='batch size in training')
    parser.add_argument('--epoch', default=80, type=int, help='number of epoch in training')
    parser.add_argument('--learning_rate', default=0.001, type=float, help='learning rate in training')
    parser.add_argument('--weight_decay', type=float, default=1e-4, help='decay rate')
    parser.add_argument('--seed', type=int, help='random seed')
    parser.add_argument('--workers', default=8, type=int, help='workers')
    parser.add_argument('--frequency', default=200, type=int, help='workers')
    # models
    # imsize = 28, paths = 4, segments = 5, samples = 2, zdim = 1024, stroke_width = None
    parser.add_argument('--imsize', default=28, type=int)
    parser.add_argument('--paths', default=8, type=int)
    parser.add_argument('--segments', default=5, type=int)
    parser.add_argument('--samples', default=2, type=int)
    parser.add_argument('--zdim', default=1024, type=int)

    return parser.parse_args()


args = parse_args()
os.environ["HDF5_USE_FILE_LOCKING"] = "FALSE"

# Verbose operations: make folder, init logger,  fix seed, set device
time_str = str(datetime.datetime.now().strftime('-%Y%m%d%H%M%S'))
message = time_str if args.msg is None else "-" + args.msg
args.checkpoint = 'checkpoints/' + args.model + message
if not os.path.isdir(args.checkpoint):
    mkdir_p(args.checkpoint)
screen_logger = logging.getLogger("Model")
screen_logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(message)s')
file_handler = logging.FileHandler(os.path.join(args.checkpoint, "screen_out.txt"))
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)
screen_logger.addHandler(file_handler)


def printf(str):
    screen_logger.info(str)
    print(str)


def main():
    if args.seed is not None:
        set_seed(args.seed)
        printf(f'==> fixing the random seed to: {args.seed}')
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    printf(f'==> using device: {device}')
    printf(f"==> args: {args}")

    # building models
    printf(f'==> Building model: {args.model}')
    net = models.__dict__[args.model](imsize=args.imsize, paths=args.paths,
                                      segments=args.segments, samples=args.samples, zdim=args.zdim)
    criterion = nn.L1Loss().to(device)
    net = net.to(device)
    if device == 'cuda':
        net = torch.nn.DataParallel(net)
        cudnn.benchmark = True

    best_test_loss = float("inf")
    start_epoch = 0  # start from epoch 0 or last checkpoint epoch
    optimizer_dict = None

    if not os.path.isfile(os.path.join(args.checkpoint, "last_checkpoint.pth")):
        save_args(args)
        logger = Logger(os.path.join(args.checkpoint, 'log.txt'), title="main")
        logger.set_names(["Epoch-Num", 'Learning-Rate', 'Train-Loss', 'Test-Loss'])
    else:
        printf(f"Resuming last checkpoint from {args.checkpoint}")
        checkpoint_path = os.path.join(args.checkpoint, "last_checkpoint.pth")
        checkpoint = torch.load(checkpoint_path)
        net.load_state_dict(checkpoint['net'])
        start_epoch = checkpoint['epoch']
        best_test_loss = checkpoint['best_test_loss']
        logger = Logger(os.path.join(args.checkpoint, 'log.txt'), title="main", resume=True)
        optimizer_dict = checkpoint['optimizer']

    printf('==> Preparing data..')
    transform = transforms.Compose([
        transforms.ToTensor()
    ])
    train_loader = DataLoader(FashionMNIST('../data', train=True, download=True, transform=transform),
                              num_workers=args.workers, batch_size=args.batch_size, shuffle=True, pin_memory=True)
    test_loader = DataLoader(FashionMNIST('../data', train=False, download=True, transform=transform),
                             num_workers=args.workers, batch_size=args.batch_size, shuffle=False, pin_memory=True)
    optimizer = torch.optim.SGD(net.parameters(), lr=args.learning_rate, momentum=0.9, weight_decay=args.weight_decay)
    if optimizer_dict is not None:
        optimizer.load_state_dict(optimizer_dict)
    scheduler = CosineAnnealingLR(optimizer, args.epoch, eta_min=args.learning_rate / 100, last_epoch=start_epoch - 1)
    # init save images
    visualize(net, train_loader, device, args.checkpoint +'/epoch-0', nrow=8)
    for epoch in range(start_epoch, args.epoch):
        printf('Epoch(%d/%s) Learning Rate %s:' % (epoch + 1, args.epoch, optimizer.param_groups[0]['lr']))
        train_out = train(net, train_loader, optimizer, criterion, device)  # {"loss"}
        test_out = validate(net, test_loader, criterion, device)  # {"loss"}
        scheduler.step()

        if test_out["loss"] < best_test_loss:
            best_test_loss = test_out["loss"]
            is_best = True
        else:
            is_best = False

        save_model(net, epoch, path=args.checkpoint, is_best=is_best, best_test_loss = best_test_loss,
                   test_loss=test_out["loss"], optimizer=optimizer.state_dict())
        logger.append([epoch, optimizer.param_groups[0]['lr'], train_out["loss"], test_out["loss"]])

        printf(f"Train loss:{train_out['loss']} Test loss:{test_out['loss']} [best test loss:{best_test_loss}]")
        printf(f"==> saving visualized images ... \n\n")
        img_save_path = args.checkpoint +'/epoch'+str(epoch+1)
        visualize(net, train_loader, device, img_save_path, nrow=8)

    logger.close()


def train(net, trainloader, optimizer, criterion, device):
    net.train()
    train_loss = 0
    time_cost = datetime.datetime.now()
    for batch_idx, (data, label) in enumerate(trainloader):
        data, label = data.to(device), label.to(device)
        optimizer.zero_grad()
        out = net(data)
        loss = criterion(out, data)
        loss.backward()
        optimizer.step()
        train_loss += loss.item()
        if batch_idx > 1 and batch_idx % args.frequency == 0:
            time_cost = int((datetime.datetime.now() - time_cost).total_seconds())
            printf(
                f"[{batch_idx}/{len(trainloader)}]\t  Train time {time_cost}s  Train loss {train_loss / (batch_idx + 1)}")
            time_cost = datetime.datetime.now()
    return {
        "loss": float("%.3f" % (train_loss / (batch_idx + 1)))
    }


def validate(net, testloader, criterion, device):
    net.eval()
    test_loss = 0
    with torch.no_grad():
        for batch_idx, (data, label) in enumerate(tqdm(testloader)):
            data, label = data.to(device), label.to(device)
            out = net(data)
            loss = criterion(out, data)
            test_loss += loss.item()
    return {
        "loss": float("%.3f" % (test_loss / (batch_idx + 1)))
    }


def visualize(net, trainloader, device, path,  nrow=8):
    data, label = next(iter(trainloader))
    data = data.to(device)
    net.eval()
    with torch.no_grad():
        out = net(data)
    vutils.save_image(data, f"{path}_gt.png", nrow=nrow, normalize=True)
    vutils.save_image(out, f"{path}_out.png", nrow=nrow, normalize=True)


if __name__ == '__main__':
    main()
