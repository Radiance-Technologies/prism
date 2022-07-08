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
    print(os.getcwd())
    os.chdir("./{0}".format(project.name))
    print(os.getcwd())
    print(project.name)
    iterator = CommitIterator(project, project.commit().hexsha)
    counter = 0
    for commit in iterator:
        print(commit.hexsha)
        print(project.metadata)
        project.git.checkout(commit)
        project.build()
        if counter == 5:
            break
        counter += 1
    print("", flush=True)


class Looper:

    def __init__(self, dataset: CoqGymBaseDataset):
        self.dataset = dataset
        return

    def __call__(self):
        wait_times = [0.5, 1.0, 1.5]
        vals = zip(self.dataset.projects.values(), wait_times)
        r = process_map(
            cache_extract,
            vals,
            max_workers=10,
            desc="Cache extraction")
