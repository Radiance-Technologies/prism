"""
Module for looping over dataset and extracting caches.
"""
import os
from typing import Callable, Iterable, Union

from tqdm.contrib.concurrent import process_map

from prism.data.dataset import CoqProjectBaseDataset
from prism.project.repo import ProjectRepo


def loop_action(
        project: ProjectRepo,
        get_commit_iterator: Callable[[ProjectRepo],
                                      Iterable[str]],
        process_commit: Callable[[ProjectRepo,
                                  str],
                                 None],
        working_dir: Union[os.PathLike,
                           str]):
    """
    Perform a given action on a project with a given iterator generator.

    Parameters
    ----------
    project : ProjectRepo
        Project to be operated on.

    get_commit_iterator : Callable[[ProjectRepo], Iterable[str]]
        Function for obtaining an iterator of commits for
        the given project.

    process_commit : Callable[[ProjectRepo,str], None]
        Function for performing some action on or
        with the project at a given commit.

    working_dir : Union[os.PathLike, str]
        Directory in which all repositories for projects
        are housed.
    """
    os.chdir(working_dir)
    os.chdir("./{0}".format(project.name))
    iterator = get_commit_iterator(project)
    for commit in iterator:
        process_commit(project, commit)


def pass_func(args):
    """
    Unpack arguments.
    """
    loop_action(*args)


class ProjectLooper:
    """
    Loop through all commits in all projects.
    """

    def __init__(
            self,
            dataset: CoqProjectBaseDataset,
            get_commit_iterator: Callable[[ProjectRepo],
                                          Iterable[str]],
            process_commit: Callable[[ProjectRepo,
                                      str],
                                     None]):
        """
        Initialize ProjectLooper object.

        Parameters
        ----------
        dataset : CoqProjectBaseDataset
            Dataset object used to loop through all
            commits in all projects, building each
            commit and extracting the build cache.

        get_commit_iterator : Callable[[ProjectRepo], Iterable[str]]
            Function for deriving an iterable of commit shas
            from a ProjectRepo. Must be declared at the
            top-level of a module, and cannot be a lambda.

        process_commit : Callable[[ProjectRepo, str], None]
            Function for performing an operation on or with a
            project at a given commit. Must be declared at the
            top-level of a module, and cannot be a lambda.
        """
        self.dataset = dataset
        self.get_commit_iterator = get_commit_iterator
        self.process_commit = process_commit

    def __call__(self, working_dir, num_workers=1):
        """
        Run looping functionality.
        """
        projects = list(self.dataset.projects.values())
        job_list = [
            (x,
             self.get_commit_iterator,
             self.process_commit,
             working_dir) for x in projects
        ]
        process_map(
            pass_func,
            job_list,
            max_workers=num_workers,
            desc="Cache extraction")
