from __future__ import print_function

import torch
import torch.optim as optim
import torchvision
from PIL import Image
import torchvision.utils as vutils
import torchvision.transforms.functional as TF
import torch.backends.cudnn as cudnn
import torchvision.transforms as transforms
import os
import argparse
from utils import mkdir_p, Logger, progress_bar, save_model, save_binary_img
from torchvision.datasets import ImageFolder
from ae import VAELoss,VanillaAE


parser = argparse.ArgumentParser(description='VAE training for NSF project')

# General MODEL parameters
parser.add_argument('--latent_dim', default=256, type=int)
# Parameters for  dataset
parser.add_argument('--input', default='../pair/data/emoji_rgb/train/0/240px-Emoji_u1f60d.svg.png', type=str)
parser.add_argument('--testdir', default='../pair/data/emoji_rgb/validate')

# Parameters for  training
parser.add_argument('--resume', default='checkpoint_best.pth', type=str, metavar='PATH', help='path to latest checkpoint')

args = parser.parse_args()
device = 'cuda' if torch.cuda.is_available() else 'cpu'

args.checkpoint = './checkpoints/%s-%s' % ( "VanillaVAE", args.latent_dim)

print('==> Load image..')
image = Image.open(args.input)
x = TF.to_tensor(image)
x = TF.resize(x,[240,240])
x = x*2-1.
x.unsqueeze_(0)
print(x.shape)
M_N = 0.111  # for the loss

def main():
    # Model
    print('==> Building model..')
    net = VanillaAE(in_channels=3, latent_dim=args.latent_dim)
    net.eval()
    net = net.to(device)

    if device == 'cuda':
        # net = torch.nn.DataParallel(net)
        cudnn.benchmark = True
    if args.resume:
        checkpoint = torch.load(args.resume, map_location=torch.device('cpu'))
        net.load_state_dict(checkpoint['net'])
        # Load checkpoint.
        print('==> Resuming from checkpoint, loaded..')

    else:
        print('==> No checkpoint, return.')
        return None
    print("===> start evaluating ...")
    generate_images(net, x, name="test_reconstruct")
    # sample_images(net, name="test_randsample")

def generate_images(net, x, name="val"):
    with torch.no_grad():
        img = x.to(device)
        vutils.save_image(((img+1.0)/2.0).float(), "inputs.png", nrow=1)

        recons = net(img)

        print(recons.max(), recons.min(), recons.shape)
        recons = (recons+1.0)/2.0
        vutils.save_image(recons.float(), "recons.png", nrow=1)

        # save_binary_img(recons.data,
        #                 os.path.join(args.checkpoint, f"{name}.png"),
        #                 nrow=args.val_num)


def sample_images(net, name="val"):
    with torch.no_grad():
        z = torch.randn(args.val_num, args.latent_dim)
        z = z.to(device)
        sampled = net.sample(z)
        save_binary_img(sampled.data,
                        os.path.join(args.checkpoint, f"{name}.png"),
                        nrow=args.val_num)


if __name__ == '__main__':
    main()
