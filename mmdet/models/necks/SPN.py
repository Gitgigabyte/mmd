import torch.nn as nn
import torch.nn.functional as F
from mmcv.cnn import kaiming_init
import torch

from mmdet.core import auto_fp16, force_fp32
from mmdet.models.registry import NECKS
from mmdet.models.utils import ConvModule


@NECKS.register_module
class SemanticPyramidNeck(nn.Module):

    def __init__(self,
                 feature_channels=256,
                 mask_channels=80,
                 num_convs=3,
                 ds_method='interpolate',
                 num_levels = 5,
                 proto_out=8,
                 conv_out_channels=256,
                 groups=True,
                 conv_cfg=None,
                 norm_cfg=None):
        super(SemanticPyramidNeck, self).__init__()
        self.mask_channels = mask_channels
        self.num_convs = num_convs
        self.ds_method = ds_method
        self.num_levels = num_levels
        self.conv_out_channels = conv_out_channels
        self.feature_channels = feature_channels
        self.conv_cfg = conv_cfg
        self.norm_cfg = norm_cfg
        self.proto_out = proto_out
        self.fp16_enabled = False
        self.groups = groups
        if self.ds_method == 'conv':
            self.ds_convs = nn.ModuleList()
            for i in range(self.num_levels-1):
                self.ds_convs.append(
                    ConvModule(self.mask_channels, self.mask_channels, 3, stride=2, padding=1,
                               norm_cfg=norm_cfg, conv_cfg=conv_cfg)
                )

        # self.lateral_convs = nn.ModuleList()
        self.combine_convs = nn.ModuleList()
        # self.proto_convs = nn.ModuleList()
        for i in range(num_levels):
            # convs = nn.ModuleList()
            # feats_stride = 1 if i==0 else 2
            # if self.groups:
            #     self.lateral_convs.append(ConvModule(self.mask_channels,self.mask_channels, 3, stride=feats_stride, padding=1,
            #                                    groups = self.mask_channels,
            #                                    conv_cfg=self.conv_cfg,
            #                                    norm_cfg=self.norm_cfg))
            # else:
            #     self.lateral_convs.append(ConvModule(
            #         self.mask_channels, self.mask_channels, 3, stride=feats_stride, padding=1,
            #         conv_cfg=self.conv_cfg,
            #         norm_cfg=self.norm_cfg
            #     ))

            # self.proto_convs.append(ConvModule(self.mask_channels, self.proto_out, 1, conv_cfg=conv_cfg, norm_cfg=norm_cfg))
        # self.convs = nn.ModuleList()
        # for i in range(self.num_convs):
        #     # in_channels = self.in_channels if i == 0 else conv_out_channels
        #     if self.groups:
        #         self.convs.append(
        #             ConvModule(
        #                 conv_out_channels,
        #                 conv_out_channels,
        #                 3,
        #                 padding=1,
        #                 groups=in_channels,
        #                 conv_cfg=self.conv_cfg,
        #                 norm_cfg=self.norm_cfg))
        #     else:
        #         self.convs.append(
        #             ConvModule(
        #                 conv_out_channels,
        #                 conv_out_channels,
        #                 3,
        #                 padding=1,
        #                 conv_cfg=self.conv_cfg,
        #                 norm_cfg=self.norm_cfg))

        # self.conv_embedding = ConvModule(
        #     conv_out_channels,
        #     conv_out_channels,
        #     1,
        #     conv_cfg=self.conv_cfg,
        #     norm_cfg=self.norm_cfg)
        # self.conv_logits = nn.Conv2d(conv_out_channels, self.num_classes, 1)
        #     for j in range(self.num_convs):
        #         in_channel = self.mask_channels + self.feature_channels if j==0 else self.feature_channels
        #         convs.append(ConvModule(in_channel, self.conv_out_channels, 3, padding=1,
        #                                 norm_cfg=norm_cfg, conv_cfg=conv_cfg))
        #     self.combine_convs.append(convs)
            if self.num_convs == 3:
                self.combine_convs.append(
                    nn.Sequential(
                    ConvModule(self.mask_channels+self.feature_channels,
                               self.conv_out_channels,
                               3,
                               padding=1,
                               norm_cfg=norm_cfg,
                               conv_cfg=conv_cfg),
                    ConvModule(self.conv_out_channels,
                               self.conv_out_channels,
                               3,
                               padding=1,
                               norm_cfg=norm_cfg,
                               conv_cfg=conv_cfg),
                    ConvModule(self.conv_out_channels,
                               self.conv_out_channels,
                               3,
                               padding=1,
                               norm_cfg=norm_cfg,
                               conv_cfg=conv_cfg)))
            elif self.num_convs == 2:
                self.combine_convs.append(
                    nn.Sequential(
                        ConvModule(self.mask_channels + self.feature_channels,
                                   self.conv_out_channels,
                                   3,
                                   padding=1,
                                   norm_cfg=norm_cfg,
                                   conv_cfg=conv_cfg),
                        ConvModule(self.conv_out_channels,
                                   self.conv_out_channels,
                                   3,
                                   padding=1,
                                   norm_cfg=norm_cfg,
                                   conv_cfg=conv_cfg)))
            elif self.num_convs == 1:
                self.combine_convs.append(
                    nn.Sequential(
                        ConvModule(self.mask_channels + self.feature_channels,
                                   self.conv_out_channels,
                                   3,
                                   padding=1,
                                   norm_cfg=norm_cfg,
                                   conv_cfg=conv_cfg)))

    def init_weights(self):
        pass

    @auto_fp16()
    def forward(self, feats, masks):
        assert len(feats) == self.num_levels
        masks = F.interpolate(masks, feats[0].size()[-2:])
        feats = list(feats)
        for i in range(self.num_levels):
            if not i==0:
                if self.ds_method == 'interpolate':
                    masks = F.interpolate(masks, feats[i].size()[-2:])
                elif self.ds_method == 'max_pool':
                    masks = F.adaptive_max_pool2d(masks, feats[i].size()[-2:])
                elif self.ds_method == 'avg_pool':
                    masks = F.adaptive_avg_pool2d(masks, feats[i].size()[-2:])
                elif self.ds_method == 'conv':
                    masks = self.ds_convs[i-1](masks)
                else:
                    raise NotImplementedError
                # protos = self.proto_convs[i](masks)
            feats[i] = self.combine_convs[i](torch.cat([feats[i], masks], dim=1)) + feats[i]
            # feats[i] = self.combine_convs[i](torch.cat([feats[i], masks], dim=1))
        return tuple(feats)


        # combine_feature = sum(features) / len(features)
        #         # masks = self.lateral_conv(masks)
        #         # combine_feature = torch.cat([combine_feature, masks], dim=1)
        #         # combine_feature = self.combine_conv(combine_feature)
        #         # outs = []
        #         # for i in range(self.num_levels):
        #         #     out_size = feats[i].size()[2:]
        #         #     if i < self.combine_level:
        #         #         residual = F.interpolate(combine_feature, size=out_size, mode='nearest')
        #         #     else:
        #         #         residual = F.adaptive_max_pool2d(combine_feature, out_size)
        #         #     outs.append(residual + feats[i])
        #         # return feats

