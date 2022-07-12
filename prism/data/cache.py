"""
Module for looping over dataset and extracting caches.
"""
import os

from tqdm.contrib.concurrent import process_map

from prism.project.repo import CommitIterator

from .dataset import CoqGymBaseDataset


def cache_extract(project):
    """
    Extract cache from series of commits.
    """
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
    """
    Loop through all commits in all projects.
    """

    def __init__(self, dataset: CoqGymBaseDataset):
        """
        Initialize Looper object.

        Parameters
        ----------
        dataset : CoqGymBaseDataset
            Dataset object used to loop through all
            commits in all projects, building each
            commit and extracting the build cache.
        """
        self.dataset = dataset

    def __call__(self, working_dir):
        """
        Run looping functionality.
        """
        os.chdir(working_dir)
        process_map(
            cache_extract,
            self.dataset.projects.values(),
            max_workers=10,
            desc="Cache extraction")
