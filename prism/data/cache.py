"""
Module for looping over dataset and extracting caches.
"""
import random
import time

from multiprocessing import Process

from prism.project.base import Project
from prism.project.repo import ProjectRepo, CommitIterator

from .dataset import CoqGymBaseDataset

def cache_extract(project: ProjectRepo):
    time.sleep(random.random())
    print(project.name)
    iterator = CommitIterator(project, project.commit().hexsha)
    counter = 0
    for commit in iterator:
        print(commit.hexsha)
        if counter == 5:
            break
        counter += 1
    print("", flush=True)


class Looper:
    def __init__(self, dataset: CoqGymBaseDataset):
        self.dataset = dataset
        return

    def __call__(self):
        processes = []
        for project_name, proj in self.dataset.projects.items():
            project_process = Process(target=cache_extract, args=(proj,))
            project_process.start()
            processes.append(project_process)

        for process in processes:
            process.join()
            


