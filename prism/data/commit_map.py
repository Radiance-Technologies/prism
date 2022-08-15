"""
Module for looping over dataset and extracting caches.
"""
import os
import signal
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from typing import (
    Callable,
    Dict,
    Generic,
    Iterable,
    List,
    Optional,
    TypeVar,
    Union,
)

import tqdm

from prism.data.dataset import CoqProjectBaseDataset
from prism.project.repo import ProjectRepo

T = TypeVar('T')


@dataclass
class Except(Generic[T]):
    """
    A (return) value paired with an exception for delayed handling.
    """

    value: T
    exception: Exception


def project_commit_fmap(
    project: ProjectRepo,
    get_commit_iterator: Callable[[ProjectRepo],
                                  Iterable[str]],
    process_commit: Callable[[ProjectRepo,
                              str,
                              Optional[T]],
                             T]
) -> Union[T,
           Except[T]]:
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
    is_terminated = False

    def sigint_sigterm_handler(*args):
        nonlocal is_terminated
        is_terminated = True

    signal.signal(signal.SIGTERM, sigint_sigterm_handler)
    signal.signal(signal.SIGINT, sigint_sigterm_handler)
    os.chdir(project.path)
    iterator = get_commit_iterator(project)
    result = None
    for commit in tqdm.tqdm(iterator, desc=f"Commits: {project.name}"):
        if is_terminated:
            break
        try:
            result = process_commit(project, commit, result)
        except Exception as e:
            is_terminated = True
            result = Except(result, e)
    return result


def pass_func(args) -> List[T]:
    """
    Unpack arguments for `project_commit_fmap`.
    """
    return project_commit_fmap(*args)


class ProjectCommitMapper(Generic[T]):
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
                                     T],
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
            Function for deriving an iterable of commit SHAs
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

    def __call__(self, num_workers: int = 1) -> Dict[str, T]:
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
        is_terminated = False
        original_sigint_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
        original_sigterm_handler = signal.signal(signal.SIGTERM, signal.SIG_IGN)
        with ProcessPoolExecutor(max_workers=num_workers) as ex:
            results = {p: None for p in projects}
            with tqdm.tqdm(total=len(job_list),
                           desc=self.task_description) as progress_bar:
                futures = {}
                for job in job_list:
                    project_name = job[0]
                    future = ex.submit(pass_func, job)
                    futures[future] = project_name
                signal.signal(signal.SIGINT, original_sigint_handler)
                signal.signal(signal.SIGTERM, original_sigterm_handler)
                for future in as_completed(futures):
                    project_name = futures[future]
                    result = future.result()
                    results[project_name] = result
                    if isinstance(result, Except):
                        is_terminated = True
                    if is_terminated:
                        # keep doing this until pool is empty and exits
                        # naturally
                        for _pid, p in ex._processes.items():
                            # send SIGTERM to each process in pool
                            p.terminate()
                    progress_bar.update(1)
        return results

    @property
    def task_description(self) -> str:
        """
        Get a description of the map's purpose.
        """
        if self._task_description is None:
            return "Map over project commits"
        return self._task_description
