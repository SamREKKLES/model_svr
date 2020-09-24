import torch
import numpy as np

from torch.utils.data import Dataset
from PIL import Image
import matplotlib.pyplot as plt
import torchvision.transforms.functional as F


class ToTensor():
    """Convert a PIL image or numpy array to a PyTorch tensor."""

    def __init__(self, labeled=True):
        self.labeled = labeled

    def __call__(self, sample):
        rdict = {}
        input_data = sample['image']

        if isinstance(input_data, list):
            ret_input = [F.to_tensor(item)
                         for item in input_data]
        else:
            ret_input = F.to_tensor(input_data)

        rdict['image'] = ret_input

        if self.labeled:
            gt_data = sample['mask']
            if gt_data is not None:
                if isinstance(gt_data, list):
                    ret_gt = [F.to_tensor(item)
                              for item in gt_data]
                else:
                    ret_gt = F.to_tensor(gt_data)

                rdict['mask'] = ret_gt
        sample.update(rdict)
        return sample


class NormalizeInstance():
    """Normalize a tensor image with mean and standard deviation estimated
    from the sample itself.

    :param mean: mean value.
    :param std: standard deviation value.
    """

    def __call__(self, sample):
        input_data = sample['image']

        mean, std = input_data.mean(), input_data.std()
        input_data = F.normalize(input_data, [mean], [std])

        if input_data.max() == np.inf:
            print(input_data.max())

        rdict = {
            'image': input_data,
        }
        sample.update(rdict)
        return sample


class Normalize():
    """Normalize a tensor image with mean and standard deviation estimated
    from the sample itself.

    :param mean: mean value.
    :param std: standard deviation value.
    """

    def __init__(self, mean, std):
        self.mean = mean
        self.std = std

    def __call__(self, sample):
        input_data = sample['image']

        mean, std = self.mean, self.std
        input_data = F.normalize(input_data, [mean], [std])

        if input_data.max() == np.inf:
            print(input_data.max())

        rdict = {
            'image': input_data,
        }
        sample.update(rdict)
        return sample


class SampleMetadata(object):
    def __init__(self, d=None):
        self.metadata = {} or d

    def __setitem__(self, key, value):
        self.metadata[key] = value

    def __getitem__(self, key):
        return self.metadata[key]

    def __contains__(self, key):
        return key in self.metadata

    def keys(self):
        return self.metadata.keys()


class CTDataset(Dataset):
    def __init__(self, list_file, transform=None, transform1=None):
        with open(list_file) as f:
            self.records = f.read().splitlines()
        self.transform = transform
        self.transform1 = transform1

    def __getitem__(self, index):
        record = np.load(self.records[index])

        gt = record['roi'].astype('float32')
        dwi = record['dwi'].astype('float32')

        # data_dict = {
        #     'input': dwi,
        #     'gt': gt,
        #     'input_metadata': SampleMetadata({
        #         "zooms": (1,1),
        #         "data_shape": dwi.size,
        #     }),
        #     'gt_metadata': SampleMetadata({
        #         "zooms": (1,1),
        #         "data_shape": gt.size,
        #     })
        #
        # }

        if self.transform:
            data_dict = self.transform(image=dwi, mask=gt)

        if self.transform1:
            data_dict = self.transform1(data_dict)

        # data_dict['orign'] = dwi

        return data_dict

    def __len__(self):
        return len(self.records)
