"""
Module for looping over dataset and extracting caches.
"""
import os
from typing import Callable, Iterable, Optional

from tqdm.contrib.concurrent import process_map

from prism.data.dataset import CoqProjectBaseDataset
from prism.project.repo import ProjectRepo


def project_commit_fmap(
        project: ProjectRepo,
        get_commit_iterator: Callable[[ProjectRepo],
                                      Iterable[str]],
        process_commit: Callable[[ProjectRepo,
                                  str],
                                 None]) -> None:
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
    """
    os.chdir(project.path)
    iterator = get_commit_iterator(project)
    for commit in iterator:
        process_commit(project, commit)


def pass_func(args):
    """
    Unpack arguments.
    """
    project_commit_fmap(*args)


class ProjectCommitMapper:
    """
    Map a function over commits in all projects of a dataset.
    """

    def __init__(
            self,
            dataset: CoqProjectBaseDataset,
            get_commit_iterator: Callable[[ProjectRepo],
                                          Iterable[str]],
            process_commit: Callable[[ProjectRepo,
                                      str],
                                     None],
            task_description: Optional[str] = None):
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
        task_description : Optional[str], optional
            A short description of the mapping operation yielded from
            `get_commit_iterator` and `process_commit`.
        """
        self.dataset = dataset
        self.get_commit_iterator = get_commit_iterator
        self.process_commit = process_commit
        self._task_description = task_description

    def __call__(self, working_dir, num_workers: int = 1):
        """
        Run looping functionality.
        """
        projects = list(self.dataset.projects.values())
        job_list = [
            (p,
             self.get_commit_iterator,
             self.process_commit) for p in projects
        ]
        # BUG: This may cause an OSError on program exit in Python 3.8
        # or earlier.
        process_map(
            pass_func,
            job_list,
            max_workers=num_workers,
            desc=self.task_description)

    @property
    def task_description(self) -> str:
        """
        Get a description of the map's purpose.
        """
        if self._task_description is None:
            return "Map over project commits"
        return self._task_description
