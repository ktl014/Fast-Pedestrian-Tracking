"""Prepare CalTech Pedestrian Train/Test Dataset Partitions

# Example
Run command as follows to prepare dataset:


"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

# Standard dist imports
import argparse
import glob
import json
import logging
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.pardir))
from PIL import Image

# Third party imports
import numpy as np
import pandas as pd

# Project level imports
from core.logger import Logger
from utils.constants import *

# Module level constants
DEBUG = True


def parse_cmds():
    parser = argparse.ArgumentParser(description='Generate dataset')
    parser.add_argument('--path', '-p', type=str, metavar='DIR',
                        help='Path to download dataset')
    parser.add_argument('--data-dir', dest='data_dir',
                        type=str, metavar='DIR', help='Data directory')
    args = parser.parse_args(sys.argv[1:])
    return args


def main():
    args = parse_cmds()
    if DEBUG:
        dest_dir = os.path.join(os.path.abspath(os.pardir), 'data')
        src_dir = '/Users/ktl014/PycharmProjects/ece285/caltech-pedestrian-dataset-converter'
    else:
        dest_dir = args.path
        src_dir = args.data_dir

    # Console logger
    log_filename = os.path.join(dest_dir, 'dataset.log')
    Logger(log_filename, logging.INFO)
    logger = logging.getLogger(__name__)
    Logger.section_break(title='Generate Dataset')

    # Initialize DatasetGenerator
    datagen = DatasetGenerator (src_dir, logger)
    datagen.generate()
    dataset = datagen.dataset_df

    # Partition dataset
    datagen.train_test_split(dataset)

    # Save dataset
    output_filename = os.path.join(dest_dir, 'data_{}.csv')
    datagen.save(output_filename)


class DatasetGenerator(object):
    """Generates datasets"""
    def __init__(self, src_dir, logger, check_valid=False):
        self.src_dir = src_dir
        self.logger = logger
        self.check_valid = check_valid
        self.dataset = {}

    def generate(self):
        """ Generates dataset

        Dataset is generated by retrieving image files and annotations then
        preparing them into one dataframe.

        Returns:
            None

        """
        self.images = self._get_images_paths()

        self.annotations = self._get_annotations()

        self._prepare_dataset()

        self._report_distribution()

    def train_test_split(self, dataset):
        """ Splits dataset into train, val, test partitions

        Sets00-05 are training and the remaining sets06-10 are testing.
        Validation sets are sampled from these training sets by 10% and is
        done with respect to each set.

        Args:
            dataset: (pandas dataframe) Dataset to be partitioned

        Returns:
            None

        """
        # Assign partitions
        train = {'set%02d' % i: TRAIN for i in range (6)}
        test = {'set%02d' % i: TEST for i in range (6, 11)}
        map_phase = train.copy()
        map_phase.update(test)
        dataset[Col.PHASE] = dataset[Col.SET].map(map_phase)

        # groupby sets 10% of each as valid
        self.train_set = dataset[dataset[Col.PHASE] == TRAIN]
        self.test_set = dataset[dataset[Col.PHASE] == TEST]
        grouped_sets = self.train_set.groupby(Col.SET)
        self.val_set = pd.DataFrame()
        for s, s_df in grouped_sets:
            sample_size = int(np.floor(.10*s_df.shape[0]))
            temp = s_df.sample(n=sample_size)
            self.train_set = self.train_set.drop(temp.index)
            self.val_set = self.val_set.append(temp, ignore_index=True)

    def save(self, output_filename):
        """ Save dataset

        Args:
            output_filename: (str) Path and filename of output.

        Returns:
            None

        """
        dataset = {TRAIN: self.train_set,
                   VAL: self.val_set,
                   TEST: self.test_set}
        self.logger.info('Saving datasets (train/val/test) to dir: {}'.format(
            os.path.dirname(output_filename)))
        for phase in dataset:
            # self._memory_usage(dataset[phase])
            self.logger.info('{} size: {}'.format(phase, dataset[phase].shape))
            dataset[phase].to_csv(output_filename.format(phase), index=False)

    def _get_images_paths(self):
        """Get image files from data directory"""
        if DEBUG:
            root = '/Users/ktl014/PycharmProjects/ece285/Fast-Pedestrian-Tracking/data/'
            # images = open(os.path.join(root, 'images.txt')).read().splitlines()
            # invalid_imgs = open(os.path.join(root, 'invaid_images.txt')).read().splitlines()
            valid_imgs = []
            for tp in [('images.txt', True), ('invalid_images.txt', False)]:
                images = open(os.path.join(root, tp[0])).read().splitlines()
                images = [(i, tp[1]) for i in images]
                valid_imgs.extend(images)

        if self.check_valid:
            images = glob.glob(os.path.join(self.src_dir, 'data', 'images', '*'))
            valid_imgs = []
            invalid_count = 0
            Logger.section_break('Invalid Images')
            for i in images:
                try:
                    im = Image.open(i)
                    im.verify()
                    valid_imgs.append((i, True))
                except (IOError, SyntaxError):
                    self.logger.info(i)
                    valid_imgs.append((i, False))
                    invalid_count += 1

            self.logger.info('Total invalid images: {}'.format(invalid_count))

        else:
            images = glob.glob(os.path.join(self.src_dir, 'data', 'images', '*'))
            valid_imgs = [(i, True) for i in images]

        self.logger.info ('')
        self.logger.info ('Total images retrieved: {}'.format (len (images)))
        return valid_imgs

    def _get_annotations(self):
        return json.load(open(os.path.join(self.src_dir,
                                           'data/annotations.json')))

    def _prepare_dataset(self):
        self.dataset[Col.IMAGES] = np.array(self.images)[:, 0]
        self.dataset[Col.VALID] = np.array(self.images)[:, 1]
        self.dataset_df = pd.DataFrame(self.dataset)

        # Split image filenames and clean up strings
        self._clean_up_filenames()

        # Grab coordinates and labels
        self.dataset_df = self.dataset_df.astype(object)
        coord = []
        lbl = []
        n_lbls = []
        for idx, row in self.dataset_df.iterrows():
            data = self.annotations[row[Col.SET]][row[Col.VIDEO]][
                Col.FRAME + 's']
            if str(row[Col.FRAME]) in data:
                data = data[str(row[Col.FRAME])]
                coordinates = [datum['pos'] for datum in data]
                label = [datum['lbl'] for datum in data]
                n_lbls.append(len(coordinates))
                coord.append(coordinates)
                lbl.append(label)
            else:
                n_lbls.append(0)
                coord.append(np.nan)
                lbl.append(np.nan)
        self.dataset_df[Col.COORD] = coord
        self.dataset_df[Col.LABEL] = lbl
        self.dataset_df[Col.N_LABELS] = n_lbls

        self.logger.info('Loaded annotations. Number of frames w/out '
                         'annotations\n{}'.format(self.dataset_df.isna().sum()))

        # Clean up nan values
        self._convert_nans()

        # Group frames to videos to sets
        self._group_objects()

    def _clean_up_filenames(self):
        """Grab meta data from filenames"""
        col_names = [Col.SET, Col.VIDEO, Col.FRAME]
        self.dataset_df[Col.IMAGES] = self.dataset_df[Col.IMAGES].apply(
            lambda x: os.path.basename(x))
        self.dataset_df[col_names] = self.dataset_df[
            Col.IMAGES].str.split('_', expand=True)
        self.dataset_df[Col.FRAME] = self.dataset_df[
            Col.FRAME].str.split('.').str[0].astype(int)
        data_dir = os.path.join(self.src_dir, 'data/images')
        self.dataset_df[Col.IMAGES] = data_dir + '/' + self.dataset_df[
            Col.IMAGES]

    def _group_objects(self):
        """Create helper dictionaries for accessing image files"""
        self.sets2videos = self.dataset_df.groupby (Col.SET)[
            Col.VIDEO].apply(set).to_dict()
        self.videos2frames = self.dataset_df.groupby (Col.VIDEO)[
            Col.IMAGES].apply(set).to_dict()
        self.sets2frames = self.dataset_df.groupby (Col.SET)[
            Col.IMAGES].apply(list).to_dict()

    def _convert_nans(self):
        """Fill NaN values"""
        self.dataset_df = self.dataset_df.fillna(value='[[0, 0, 0, 0]]')
        self.logger.info('Total annotations: {}'.
                         format(self.dataset_df[Col.N_LABELS].sum()))
        self.logger.info('Dataset size: {}'.format(self.dataset_df.shape))


    def _report_distribution(self):
        """Report distributions"""
        Logger.section_break('Image per video distribution')
        self.logger.info(self.dataset_df[Col.VIDEO].value_counts().sort_index())

        Logger.section_break('Videos per set distribution')
        for set, video in sorted(self.sets2videos.items()):
            total_imgs = len(self.sets2frames[set])
            self.logger.info('{} [{} videos / {} images]: {}\n'.
                             format(set, len(video), total_imgs, sorted(video)))

    def _memory_usage(self, df):
        """Used for debugging"""
        nbytes = sum (block.values.nbytes for block in df.blocks.values ())
        # self.logger.info('Memory usage: {}'.format(nbytes))


if __name__ == '__main__':
    main()
