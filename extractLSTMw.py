import torch
from torch.autograd import Variable
import torch.nn as nn
import numpy as np
from torch.utils.data import DataLoader
import os
from scipy import ndimage
from skimage import io
import math
from tqdm import tqdm
import cv2

from data.STdatas import STTrainData, STValData
from models.LSTMnet import lstmnet
from utils import *

"""
Extract attention weights, save them for training LSTM and later use.

"""

class st_extract(nn.Module):
    def __init__(self, features_s):
        super(st_extract, self).__init__()
        self.features_s = features_s

    def forward(self, x_s):
        x = self.features_s(x_s)
        return x

def crop_feature_var(feature, maxind, size):
    H = feature.size(2)
    W = feature.size(3)
    for b in range(feature.size(0)):
        ind = maxind[b].item()
        fmax = np.unravel_index(ind, (H,W))
        fmax = np.clip(fmax, size/2, H-int(math.ceil(size/2.0)))
        cfeature = feature[b,:,(fmax[0]-size/2):(fmax[0]+int(math.ceil(size/2.0))),(fmax[1]-size/2):(fmax[1]+int(math.ceil(size/2.0)))]
        cfeature = cfeature.unsqueeze(0)
        if b==0:
            res = cfeature
        else:
            res = torch.cat((res, cfeature),0)
    return res

def extractw(loader, model, savepath, crop_size=3):
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    fixflag = False
    fix2flag = False
    downsample = nn.AvgPool2d(16)
    with torch.no_grad():
        for i, sample in tqdm(enumerate(loader)):
            fixsac = sample['fixsac']
            if fixflag == False and float(fixsac) == 1.0:
                fixflag=True
            elif fixflag == False and float(fixsac) == 0.0:
                continue
            elif fixflag == True and fix2flag == False and float(fixsac) == 1.0:
                fix2flag = True
                currname = sample['imname'][0][:-4]
                inp = sample['image']  #(1,3,224,224)
                inp = inp.float().to(device)
                target = sample['gt'] #(1,1,224,224)
                target = target.float().to(device)
                target_flat = downsample(target).view(target.size(0), target.size(1), -1) #(1,1,196)
                _, maxind = torch.max(target_flat, 2) #(1,1)

                out = model(inp) #(1,512,14,14)
                cfeature = crop_feature_var(out, maxind, crop_size) #(1,512,3,3)
                cfeature = cfeature.contiguous()
                chn_weight = cfeature.view(cfeature.size(0), cfeature.size(1), -1)
                chn_weight = torch.mean(chn_weight, 2) #(1,512)
                chn_weight = chn_weight.data.squeeze() #(512)
                torch.save(chn_weight, os.path.join(savepath , 'fix_'+currname+'.pth.tar'))
            elif fixflag == True and fix2flag ==True and float(fixsac) == 1.0:
                continue
            elif fixflag == True and fix2flag == True and float(fixsac) == 0.0:
                fixflag = False
                fix2flag = False
            else:
                raise RuntimeError('fixation is not processed.')

        
def extract_LSTM_training_data(save_path='512w', trained_model='savefusion/00004_fusion3d_bn_floss_checkpoint.pth.tar', device='0', crop_size=3):
    batch_size = 1

    STTrainLoader = DataLoader(dataset=STTrainData, batch_size=batch_size, shuffle=False, num_workers=1, pin_memory=True)
    STValLoader = DataLoader(dataset=STValData, batch_size=batch_size, shuffle=False, num_workers=1, pin_memory=True)
    print('building model...')
    model = st_extract(make_layers(cfg['D'], 3))
    model.to(device)
    pretrained_dict = torch.load(trained_model)
    pretrained_dict = pretrained_dict['state_dict']
    load_dict = {k:v for k,v in pretrained_dict.items() if 'features_s' in k}
    model_dict = model.state_dict()
    for k in load_dict.keys():
        if k not in model_dict.keys():
            del load_dict[k]
    model_dict.update(load_dict)
    model.load_state_dict(model_dict)
    del pretrained_dict, load_dict


    extractw(STTrainLoader, model, os.path.join(save_path, 'train'), crop_size)
    extractw(STValLoader, model, os.path.join(save_path, 'test'), crop_size)
    print('Attention weight for training LSTMnet successfully extracted.')