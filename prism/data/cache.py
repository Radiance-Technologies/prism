"""
Module for looping over dataset and extracting caches.
"""
import os
import random
import time
from multiprocessing import Process

from tqdm.contrib.concurrent import process_map

from prism.project.repo import CommitIterator, ProjectRepo

from .dataset import CoqGymBaseDataset


def cache_extract(input_tuple):
    project, wait_time = input_tuple
    time.sleep(wait_time)
    os.chdir("./{0}".format(project.name))
    iterator = CommitIterator(project, project.commit().hexsha)
    counter = 0
    for commit in iterator:
        project.git.checkout(commit)
        project.build()
        if counter == 0:
            break
        counter += 1


class Looper:

    def __init__(self, dataset: CoqGymBaseDataset):
        self.dataset = dataset
        return

    def __call__(self):
        r = process_map(
            cache_extract,
            self.dataset.projects.values(),
            max_workers=10,
            desc="Cache extraction")
