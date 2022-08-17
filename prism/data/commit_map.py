"""
Module for looping over dataset and extracting caches.
"""
import logging
import os
import signal
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from typing import (
    Callable,
    Dict,
    Generic,
    Iterable,
    Iterator,
    Optional,
    TypeVar,
    Union,
)

import tqdm

from prism.project.repo import ProjectRepo
from prism.util.logging import default_log_level

__all__ = ['Except', 'ProjectCommitMapper']

logger = logging.getLogger(__file__)
logger.setLevel(default_log_level())

T = TypeVar('T')


@dataclass
class Except(Generic[T]):
    """
    A (return) value paired with an exception for delayed handling.
    """

    value: Optional[T]
    """
    A return value preempted by an exception.

    If None, then the exception was likely raised before any return
    value was computed.
    If not None, then the value may or may not be complete.
    """
    exception: Exception
    """
    An exception raised during the computation of `value`.
    """


def _project_commit_fmap(
    project: ProjectRepo,
    get_commit_iterator: Callable[[ProjectRepo],
                                  Iterable[str]],
    process_commit: Callable[[ProjectRepo,
                              str,
                              Optional[T]],
                             T]
) -> Union[Optional[T],
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


def _project_commit_fmap_(args) -> Union[Optional[T], Except[T]]:
    """
    Unpack arguments for `project_commit_fmap`.
    """
    return _project_commit_fmap(*args)


class ProjectCommitMapper(Generic[T]):
    """
    Map a function over commits in all projects of a dataset.
    """

    def __init__(
            self,
            projects: Iterable[ProjectRepo],
            get_commit_iterator: Callable[[ProjectRepo],
                                          Iterator[str]],
            process_commit: Callable[[ProjectRepo,
                                      str,
                                      Optional[T]],
                                     T],
            task_description: Optional[str] = None,
            wait_on_interrupt: bool = True):
        """
        Initialize ProjectCommitMapper object.

        Parameters
        ----------
        projects : Set[ProjectRepo]
            A set of projects over which to map a function.
        get_commit_iterator : Callable[[ProjectRepo], Iterator[str]]
            Function for deriving an iterable of commit SHAs
            from a ProjectRepo.
            Must be declared at the top-level of a module, and cannot be
            a lambda due to Python multiprocessing limitations.
        process_commit : Callable[[ProjectRepo, str, Optional[T]], T]
            The function that will be mapped over each project commit
            yielded from `get_commit_iterator`.
            Must be declared at the top-level of a module and cannot be
            a lambda due to Python multiprocessing limitations.
        task_description : Optional[str], optional
            A short description of the mapping operation yielded from
            `get_commit_iterator` and `process_commit`.
        wait_on_interrupt : bool, optional
            In the event of a user interrupt, whether to wait for
            subprocesses to finish processing their current commit or
            to kill them immediately (with a non-blockable SIGKILL).
            By default True.
        """
        self.projects = list(projects)
        self.get_commit_iterator = get_commit_iterator
        self.process_commit = process_commit
        self._task_description = task_description
        self._wait = wait_on_interrupt
        # By default True so that an arbitrary process_commit is allowed
        # to clean up any artifacts or state prior to termination

    def __call__(self, max_workers: int = 1) -> Dict[str, T]:
        """
        Map over project commits.

        See Also
        --------
        map : For the public API.
        """
        job_list = [
            (p,
             self.get_commit_iterator,
             self.process_commit) for p in self.projects
        ]
        # BUG: Multiprocessing pools may cause an OSError on program
        # exit in Python 3.8 or earlier.
        is_terminated = False
        # ignore SIGINT and SIGTERM so that child processes will ignore
        # each by default
        logger.debug("Temporarily ignoring SIGTERM and SIGINT")
        original_sigint_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
        original_sigterm_handler = signal.signal(signal.SIGTERM, signal.SIG_IGN)
        logger.debug(f"Initializing pool of {max_workers} workers")
        with ProcessPoolExecutor(max_workers=max_workers) as ex:
            results = {p.name: None for p in self.projects}
            with tqdm.tqdm(total=len(job_list),
                           desc=self.task_description) as progress_bar:
                futures = {}
                for job in job_list:
                    project_name = job[0].name
                    future = ex.submit(_project_commit_fmap_, job)
                    futures[future] = project_name
                    logger.debug(f"Job submitted for {project_name}")
                signal.signal(signal.SIGINT, original_sigint_handler)
                signal.signal(signal.SIGTERM, original_sigterm_handler)
                logger.debug("Default signal handlers restored.")
                try:
                    for future in as_completed(futures):
                        project_name = futures[future]
                        result = future.result()
                        logger.debug(f"Job {project_name} completed.")
                        results[project_name] = result
                        if isinstance(result, Except):
                            logger.critical(
                                f"Job {project_name} failed. Terminating process pool.",
                                exc_info=result.exception)
                            is_terminated = True
                        if is_terminated:
                            # keep doing this until pool is empty and
                            # exits naturally
                            for _pid, p in ex._processes.items():
                                # send SIGTERM to each process in pool
                                p.terminate()
                        progress_bar.update(1)
                except KeyboardInterrupt:
                    logger.info(
                        "Terminating process pool due to user interrupt.")
                    if not self._wait:
                        for _pid, p in ex._processes.items():
                            # Do not wait for any jobs to finish.
                            # Terminate them immediately.
                            # However, since each child is set to ignore
                            # a SIGTERM until it finishes its current
                            # commit, we send SIGKILL instead.
                            p.kill()
                    ex.shutdown(wait=True)
                    raise
        return results

    def map(self, max_workers: int = 1) -> Dict[str, T]:
        """
        Map over the project commits.

        Mapping occurs in an asynchronous manner by employing a pool of
        subprocesses, one per project at a time.

        Parameters
        ----------
        max_workers : int, optional
            The maximum number of subprocesses, by default 1, which
            will result in a sequential map over the projects.

        Returns
        -------
        Dict[str, T]
            The results of the map as applied to each iterated project
            commit.
            If an unhandled exception is encountered during the
            operation, then the map is terminated.
            Partial results will be returned corresponding to the
            accumulation of results for commits iterated prior to the
            error.
            The results of the project(s) that raised the unhandled
            exception will be wrapped in an `Except` object for
            subsequent handling or re-raising by the caller.
        """
        return self(max_workers)

    @property
    def task_description(self) -> str:
        """
        Get a description of the map's purpose.
        """
        if self._task_description is None:
            return "Map over project commits"
        return self._task_description
