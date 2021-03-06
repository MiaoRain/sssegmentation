'''
Function:
    Implementation of DMNet
Author:
    Zhenchao Jin
'''
import copy
import torch
import torch.nn as nn
import torch.nn.functional as F
from ...backbones import *
from ..base import BaseModel
from .dcm import DynamicConvolutionalModule


'''DMNet'''
class DMNet(BaseModel):
    def __init__(self, cfg, **kwargs):
        super(DMNet, self).__init__(cfg, **kwargs)
        align_corners, norm_cfg, act_cfg = self.align_corners, self.norm_cfg, self.act_cfg
        # build dcm
        dcm_cfg = cfg['dcm']
        self.dcm_modules = nn.ModuleList()
        for filter_size in dcm_cfg['filter_sizes']:
            self.dcm_modules.append(
                DynamicConvolutionalModule(
                    filter_size=filter_size,
                    is_fusion=dcm_cfg['is_fusion'],
                    in_channels=dcm_cfg['in_channels'],
                    out_channels=dcm_cfg['out_channels'],
                    norm_cfg=norm_cfg,
                    act_cfg=act_cfg,
                )
            )
        # build decoder
        decoder_cfg = cfg['decoder']
        self.decoder = nn.Sequential(
            nn.Conv2d(decoder_cfg['in_channels'], decoder_cfg['out_channels'], kernel_size=3, stride=1, padding=1, bias=False),
            BuildNormalization(norm_cfg['type'], (decoder_cfg['out_channels'], norm_cfg['opts'])),
            BuildActivation(act_cfg['type'], **act_cfg['opts']),
            nn.Dropout2d(decoder_cfg['dropout']),
            nn.Conv2d(decoder_cfg['out_channels'], cfg['num_classes'], kernel_size=1, stride=1, padding=0)
        )
        # build auxiliary decoder
        auxiliary_cfg = cfg['auxiliary']
        self.auxiliary_decoder = nn.Sequential(
            nn.Conv2d(auxiliary_cfg['in_channels'], auxiliary_cfg['out_channels'], kernel_size=3, stride=1, padding=1, bias=False),
            BuildNormalization(norm_cfg['type'], (auxiliary_cfg['out_channels'], norm_cfg['opts'])),
            BuildActivation(act_cfg['type'], **act_cfg['opts']),
            nn.Dropout2d(auxiliary_cfg['dropout']),
            nn.Conv2d(auxiliary_cfg['out_channels'], cfg['num_classes'], kernel_size=1, stride=1, padding=0)
        )
        # freeze normalization layer if necessary
        if cfg.get('is_freeze_norm', False): self.freezenormalization()
    '''forward'''
    def forward(self, x, targets=None, losses_cfg=None):
        h, w = x.size(2), x.size(3)
        # feed to backbone network
        x3, x4 = self.transforminputs(self.backbone_net(x), selected_indices=self.cfg['backbone'].get('selected_indices'))
        # feed to dcm
        dcm_outs = [x4]
        for dcm_module in self.dcm_modules:
            dcm_outs.append(dcm_module(x4))
        feats = torch.cat(dcm_outs, dim=1)
        # feed to decoder
        preds = self.decoder(feats)
        # feed to auxiliary decoder and return according to the mode
        if self.mode == 'TRAIN':
            preds = F.interpolate(preds, size=(h, w), mode='bilinear', align_corners=self.align_corners)
            preds_aux = self.auxiliary_decoder(x3)
            preds_aux = F.interpolate(preds_aux, size=(h, w), mode='bilinear', align_corners=self.align_corners)
            return self.calculatelosses(
                predictions={'loss_cls': preds, 'loss_aux': preds_aux}, 
                targets=targets, 
                losses_cfg=losses_cfg
            )
        return preds
    '''return all layers'''
    def alllayers(self):
        return {
            'backbone_net': self.backbone_net,
            'dcm_modules': self.dcm_modules,
            'decoder': self.decoder,
            'auxiliary_decoder': self.auxiliary_decoder
        }