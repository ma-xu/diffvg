'''Some helper functions for PyTorch, including:
    - get_mean_and_std: calculate the mean and std value of dataset.
    - msr_init: net parameter initialization.
    - progress_bar: progress bar mimic xlua.progress.
'''
import os
import sys
import time
import errno
import shutil
import torch
import torch.nn as nn
import torch.nn.init as init
import torchvision.utils as vutils
from typing import List
import numpy as np
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt

__all__ = ["get_mean_and_std", "progress_bar", "format_time",
           'adjust_learning_rate', 'AverageMeter', 'Logger', 'mkdir_p','generate_similar_img']


def merge(x):
    return 2 * x - 1.


def get_mean_and_std(dataset):
    '''Compute the mean and std value of dataset.'''
    dataloader = torch.utils.data.DataLoader(dataset, batch_size=1, shuffle=True, num_workers=2)
    print('==> Computing mean and std..')
    mean, std = 0, 0
    for inputs, targets in dataloader:
        mean += inputs[:, 0, :, :].mean()
        std += inputs[:, 0, :, :].std()
    mean.div_(len(dataset))
    std.div_(len(dataset))
    return mean, std


def init_params(net):
    '''Init layer parameters.'''
    for m in net.modules():
        if isinstance(m, nn.Conv2d):
            init.kaiming_normal(m.weight, mode='fan_out')
            if m.bias:
                init.constant(m.bias, 0)
        elif isinstance(m, nn.BatchNorm2d):
            init.constant(m.weight, 1)
            init.constant(m.bias, 0)
        elif isinstance(m, nn.Linear):
            init.normal(m.weight, std=1e-3)
            if m.bias:
                init.constant(m.bias, 0)


# _, term_width = os.popen('stty size', 'r').read().split()
# term_width = int(term_width)

TOTAL_BAR_LENGTH = 65.
last_time = time.time()
begin_time = last_time


def progress_bar(current, total, msg=None):
    global last_time, begin_time
    if current == 0:
        begin_time = time.time()  # Reset for new bar.

    cur_len = int(TOTAL_BAR_LENGTH * current / total)
    rest_len = int(TOTAL_BAR_LENGTH - cur_len) - 1

    sys.stdout.write(' [')
    for i in range(cur_len):
        sys.stdout.write('=')
    sys.stdout.write('>')
    for i in range(rest_len):
        sys.stdout.write('.')
    sys.stdout.write(']')

    cur_time = time.time()
    step_time = cur_time - last_time
    last_time = cur_time
    tot_time = cur_time - begin_time

    L = []
    L.append('  Step: %s' % format_time(step_time))
    L.append(' | Tot: %s' % format_time(tot_time))
    if msg:
        L.append(' | ' + msg)

    msg = ''.join(L)
    sys.stdout.write(msg)
    # for i in range(term_width-int(TOTAL_BAR_LENGTH)-len(msg)-3):
    #     sys.stdout.write(' ')

    # Go back to the center of the bar.
    # for i in range(term_width-int(TOTAL_BAR_LENGTH/2)+2):
    #     sys.stdout.write('\b')
    sys.stdout.write(' %d/%d ' % (current + 1, total))

    if current < total - 1:
        sys.stdout.write('\r')
    else:
        sys.stdout.write('\n')
    sys.stdout.flush()


def format_time(seconds):
    days = int(seconds / 3600 / 24)
    seconds = seconds - days * 3600 * 24
    hours = int(seconds / 3600)
    seconds = seconds - hours * 3600
    minutes = int(seconds / 60)
    seconds = seconds - minutes * 60
    secondsf = int(seconds)
    seconds = seconds - secondsf
    millis = int(seconds * 1000)

    f = ''
    i = 1
    if days > 0:
        f += str(days) + 'D'
        i += 1
    if hours > 0 and i <= 2:
        f += str(hours) + 'h'
        i += 1
    if minutes > 0 and i <= 2:
        f += str(minutes) + 'm'
        i += 1
    if secondsf > 0 and i <= 2:
        f += str(secondsf) + 's'
        i += 1
    if millis > 0 and i <= 2:
        f += str(millis) + 'ms'
        i += 1
    if f == '':
        f = '0ms'
    return f


def write_record(file_path, str):
    if not os.path.exists(file_path):
        # os.makedirs(file_path)
        os.system(r"touch {}".format(file_path))
    f = open(file_path, 'a')
    f.write(str)
    f.close()


def count_parameters(model, all=True):
    # If all= Flase, we only return the trainable parameters; tested
    return sum(p.numel() for p in model.parameters() if p.requires_grad or all)


def adjust_learning_rate(optimizer, epoch, lr, factor=0.1, step=30):
    """Sets the learning rate to the initial LR decayed by factor every step epochs"""
    lr = lr * (factor ** (epoch // step))
    for param_group in optimizer.param_groups:
        param_group['lr'] = lr


class ProgressMeter(object):
    def __init__(self, num_batches, meters, prefix=""):
        self.batch_fmtstr = self._get_batch_fmtstr(num_batches)
        self.meters = meters
        self.prefix = prefix

    def display(self, batch):
        entries = [self.prefix + self.batch_fmtstr.format(batch)]
        entries += [str(meter) for meter in self.meters]
        print('\t'.join(entries))

    def _get_batch_fmtstr(self, num_batches):
        num_digits = len(str(num_batches // 1))
        fmt = '{:' + str(num_digits) + 'd}'
        return '[' + fmt + '/' + fmt.format(num_batches) + ']'


def accuracy(output, target, topk=(1,)):
    """Computes the accuracy over the k top predictions for the specified values of k"""
    with torch.no_grad():
        maxk = max(topk)
        batch_size = target.size(0)

        _, pred = output.topk(maxk, 1, True, True)
        pred = pred.t()
        correct = pred.eq(target.view(1, -1).expand_as(pred))

        res = []
        for k in topk:
            correct_k = correct[:k].view(-1).float().sum(0, keepdim=True)
            res.append(correct_k.mul_(100.0 / batch_size))
        return res


class AverageMeter(object):
    """Computes and stores the average and current value"""

    def __init__(self, name, fmt=':f'):
        self.name = name
        self.fmt = fmt
        self.reset()

    def reset(self):
        self.val = 0
        self.avg = 0
        self.sum = 0
        self.count = 0

    def update(self, val, n=1):
        self.val = val
        self.sum += val * n
        self.count += n
        self.avg = self.sum / self.count

    def __str__(self):
        fmtstr = '{name} {val' + self.fmt + '} ({avg' + self.fmt + '})'
        return fmtstr.format(**self.__dict__)


class Logger(object):
    '''Save training process to log file with simple plot function.'''

    def __init__(self, fpath, title=None, resume=False):
        self.file = None
        self.resume = resume
        self.title = '' if title == None else title
        if fpath is not None:
            if resume:
                self.file = open(fpath, 'r')
                name = self.file.readline()
                self.names = name.rstrip().split('\t')
                self.numbers = {}
                for _, name in enumerate(self.names):
                    self.numbers[name] = []

                for numbers in self.file:
                    numbers = numbers.rstrip().split('\t')
                    for i in range(0, len(numbers)):
                        self.numbers[self.names[i]].append(numbers[i])
                self.file.close()
                self.file = open(fpath, 'a')
            else:
                self.file = open(fpath, 'w')

    def set_names(self, names):
        if self.resume:
            pass
        # initialize numbers as empty list
        self.numbers = {}
        self.names = names
        for _, name in enumerate(self.names):
            self.file.write(name)
            self.file.write('\t')
            self.numbers[name] = []
        self.file.write('\n')
        self.file.flush()

    def append(self, numbers):
        assert len(self.names) == len(numbers), 'Numbers do not match names'
        for index, num in enumerate(numbers):
            self.file.write("{0:.6f}".format(num))
            self.file.write('\t')
            self.numbers[self.names[index]].append(num)
        self.file.write('\n')
        self.file.flush()

    def close(self):
        if self.file is not None:
            self.file.close()


def mkdir_p(path):
    '''make dir if not exist'''
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def save_model(net, optimizer, epoch, path, **kwargs):
    state = {
        'net': net.state_dict(),
        'optimizer': optimizer.state_dict(),
        'epoch': epoch
    }
    for key, value in kwargs.items():
        state[key] = value
    torch.save(state, path)


def save_binary_img(tensor, file_path="./val.png", nrow=8):
    # tensor [b,1,w,h]
    predicted = torch.sigmoid(tensor) > 0.5
    vutils.save_image(predicted.float(), file_path, nrow=nrow)


def plot_spectrum(spectrums: List[torch.Tensor], labels: List[str], save_path: str = "./spectrum.png"):
    assert len(spectrums) >= 1
    assert len(spectrums) == len(labels)

    colors = ['C0', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8', 'C9']
    markers = ['o', 'v', 's', '*', 'p', '+', 'x']
    spectrums = torch.stack(spectrums)  # [n, batch, 182, 2]
    print(f"spectrums shape: {spectrums.shape}")
    spectrums = spectrums.permute(1, 0, 2, 3)
    batch, n, points, _ = spectrums.shape
    spectrums = spectrums.data.cpu().numpy()
    plt.figure(figsize=(9 * batch, 6))
    for i in range(0, batch):
        i_batch = spectrums[i]
        plt.subplot(1, batch, i + 1)
        for j in range(0, n):
            j_data = i_batch[j]  # j in n data / i in batch
            plt.plot(j_data[:, 0], j_data[:, 1], color=colors[j], marker=markers[j], label=labels[j])
        plt.legend()
        plt.title(f"sample_No_{i + 1}")
    plt.tight_layout()
    plt.savefig(save_path, bbox_inches='tight', dpi=200)
    plt.close()

    # for i in range(0, len(spectrums)):
    #     spectrum_batch = spectrums[i].data.cpu().numpy()
    #     label = labels[i]
    #     for j in range(0, spectrums[0].shape[0]):
    #         spectrum = spectrums[i][j].data.cpu().numpy()
    #
    #         plt.plot(spectrum[:,0], spectrum[:,1], label=label)
    # plt.legend()
    # plt.savefig(save_path, bbox_inches='tight', dpi=200)
    # plt.close()


def plot_amplitude(spectrum_list: List[torch.Tensor], labels: List[str], save_path: str = "./spectrum.png"):
    assert len(spectrum_list) >= 1
    assert len(spectrum_list) == len(labels)
    x_range = np.linspace(600, 1200, 61)

    colors = ['C0', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8', 'C9']
    markers = ['o', 'v', 's', '*', 'p', '+', 'x']
    amplitude_list = []
    for spectrum in spectrum_list:
        amplitude_list.append(spectrum[:, :, 0])

    amplitudes = torch.stack(amplitude_list, dim=2)  # [batch, 183, n]
    amplitudes = amplitudes.permute(0, 2, 1) # [batch, n, 183]
    batch, n, points = amplitudes.shape
    amplitudes = amplitudes.data.cpu().numpy()
    plt.figure(figsize=(9 * batch, 6*3))
    # plot amplitude
    for nnn in range(3):
        for i in range(0, batch):
            i_batch = amplitudes[i]  # [n, 183]
            plt.subplot(3, batch, batch*nnn+i+1)
            for j in range(0, n):
                j_data = i_batch[j]  # j in n data / i in batch [183]
                plt.plot(x_range, j_data[61*nnn:61*(nnn+1)], color=colors[j], marker=markers[j], label=labels[j])
            plt.legend()
            plt.title(f"amplitude{nnn+1} sample_No_{i + 1}")


    plt.tight_layout()
    plt.savefig(save_path, bbox_inches='tight', dpi=150)
    plt.close()


def demo():
    a = torch.rand(5, 10, 2)
    b = torch.rand(5, 10, 2)
    plot_spectrum([a, b], ["a", "b"])


