"""
Module for looping over dataset and extracting caches.
"""
import functools
import logging
import os
import signal
import traceback
import typing
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import (
    Callable,
    Dict,
    Generic,
    Iterable,
    Optional,
    Tuple,
    TypeVar,
    Union,
)

import tqdm

from prism.project.metadata.storage import MetadataStorage
from prism.project.repo import ProjectRepo
from prism.util.exceptions import Except
from prism.util.logging import default_log_level

__all__ = ['Except', 'ProjectCommitMapper', 'ProjectCommitUpdateMapper']

logger = logging.getLogger(__file__)
logger.setLevel(default_log_level())

T = TypeVar('T')


def _project_commit_fmap(
        project: ProjectRepo,
        get_commit_iterator: Callable[[ProjectRepo],
                                      Iterable[str]],
        commit_fmap: Callable[[ProjectRepo,
                               str,
                               Optional[T]],
                              T],
        force_serial: bool) -> Union[Optional[T],
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
    commit_fmap : Callable[[ProjectRepo, str, Optional[T]], T]
        Function for performing some action on or
        with the project at a given commit.
        Results from prior commits are provided for optional
        accumulation.

    Returns
    -------
    Union[Optional[T], Except[T]]
        The accumulated result of applying `commit_fmap` to the commits
        or a captured exception with partially accumulated results.
    """
    is_terminated = False

    def sigint_sigterm_handler(*args):
        nonlocal is_terminated
        is_terminated = True

    signal.signal(signal.SIGTERM, sigint_sigterm_handler)
    signal.signal(signal.SIGINT, sigint_sigterm_handler)
    os.chdir(project.path)
    iterator = get_commit_iterator(project)
    result: Union[Optional[T], Except[T]] = None
    pbar = tqdm.tqdm(iterator, total=None, desc=f"Commits ({project.name})")
    for commit in pbar:
        if is_terminated:
            break
        pbar.set_description(f"Commit {commit[:8]} of {project.name}")
        try:
            result = commit_fmap(
                project,
                commit,
                typing.cast(Optional[T],
                            result))
        except Exception as e:
            if force_serial:
                raise e
            is_terminated = True
            result = Except(
                typing.cast(Optional[T],
                            result),
                e,
                traceback.format_exc())
    return result


def _project_commit_fmap_(args) -> Union[Optional[T], Except[T]]:
    """
    Unpack arguments for `project_commit_fmap`.
    """
    return _project_commit_fmap(*args)


class ProjectCommitMapper(Generic[T]):
    """
    Map a function over commits of all projects in a given collection.
    """

    def __init__(
            self,
            projects: Iterable[ProjectRepo],
            get_commit_iterator: Callable[[ProjectRepo],
                                          Iterable[str]],
            commit_fmap: Callable[[ProjectRepo,
                                   str,
                                   Optional[T]],
                                  T],
            task_description: Optional[str] = None,
            wait_on_interrupt: bool = True,
            terminate_on_except: bool = True):
        """
        Initialize ProjectCommitMapper object.

        Parameters
        ----------
        projects : Set[ProjectRepo]
            A set of projects over which to map a function.
        get_commit_iterator : Callable[[ProjectRepo], Iterable[str]]
            Function for deriving an iterable of commit SHAs
            from a ProjectRepo.
            Must be declared at the top-level of a module, and cannot be
            a lambda due to Python multiprocessing limitations.
        commit_fmap : Callable[[ProjectRepo, str, Optional[T]], T]
            The function that will be mapped over each project commit
            yielded from `get_commit_iterator`.
            Must be declared at the top-level of a module and cannot be
            a lambda due to Python multiprocessing limitations.
        task_description : Optional[str], optional
            A short description of the mapping operation yielded from
            `get_commit_iterator` and `commit_fmap`.
        wait_on_interrupt : bool, optional
            In the event of a user interrupt, whether to wait for
            subprocesses to finish processing their current commit or
            to kill them immediately (with a non-blockable SIGKILL).
            By default True.
        terminate_on_except : bool, optional
            Whether to terminate the process pool on the return of an
            `Except` value from a subprocess or to continue processing
            projects.
            By default True.
        """
        self.projects = list(projects)
        self.get_commit_iterator = get_commit_iterator
        self.commit_fmap = commit_fmap
        self._task_description = task_description
        self._wait = wait_on_interrupt
        self._terminate = terminate_on_except
        # By default True so that an arbitrary commit_fmap is allowed
        # to clean up any artifacts or state prior to termination

    def __call__(
            self,
            max_workers: int = 1,
            force_serial: bool = False) -> Dict[str,
                                                Union[Optional[T],
                                                      Except[T]]]:
        """
        Map over project commits.

        See Also
        --------
        map : For the public API.
        """
        job_list = [
            (p,
             self.get_commit_iterator,
             self.commit_fmap,
             force_serial) for p in self.projects
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
        results: Dict[str,
                      Union[Optional[T],
                            Except[T]]] = {
                                p.name: None for p in self.projects
                            }  # noqa: E126
        if force_serial:
            for job in tqdm.tqdm(job_list,
                                 total=len(job_list),
                                 desc=self.task_description):
                result: Union[Optional[T],
                              Except[T]] = _project_commit_fmap_(job)
                project_name = job[0].name
                results[project_name] = result
                if isinstance(result, Except) and self._terminate:
                    logger.critical(
                        f"Job {project_name} failed. Terminating process pool.",
                        exc_info=result.exception)
                    return results
        else:
            with ProcessPoolExecutor(max_workers=max_workers) as ex:
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
                            result = typing.cast(
                                Union[Optional[T],
                                      Except[T]],
                                future.result())
                            logger.debug(f"Job {project_name} completed.")
                            results[project_name] = result
                            if isinstance(result, Except) and self._terminate:
                                logger.critical(
                                    f"Job {project_name} failed."
                                    " Terminating process pool.",
                                    exc_info=result.exception)
                                is_terminated = True
                            if is_terminated:
                                # keep doing this until pool is empty
                                # and exits naturally
                                for _pid, p in ex._processes.items():
                                    # send SIGTERM to each process in
                                    # pool
                                    p.terminate()
                            progress_bar.update(1)
                    except KeyboardInterrupt:
                        logger.info(
                            "Terminating process pool due to user interrupt.")
                        if not self._wait:
                            for _pid, p in ex._processes.items():
                                # Do not wait for any jobs to finish.
                                # Terminate them immediately.
                                # However, since each child is set to
                                # ignore a SIGTERM until it finishes its
                                # current commit, we send SIGKILL
                                # instead.
                                p.kill()
                        ex.shutdown(wait=True)
                        raise
        return results

    def map(self,
            max_workers: int = 1,
            force_serial: bool = False) -> Dict[str,
                                                Union[Optional[T],
                                                      Except[T]]]:
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
        Dict[str, Except[T]]
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
        return self(max_workers, force_serial)

    @property
    def task_description(self) -> str:
        """
        Get a description of the map's purpose.
        """
        if self._task_description is None:
            return "Map over project commits"
        return self._task_description


def _commit_fmap_and_update(
        commit_fmap: Callable[[ProjectRepo,
                               str,
                               Optional[T]],
                              T],
        project: ProjectRepo,
        commit_sha: str,
        result: Optional[Tuple[T,
                               MetadataStorage]]) -> Tuple[T,
                                                           MetadataStorage]:
    """
    Return an updated `MetadataStorage` alongside a map result.
    """
    original_result = None
    if result is not None:
        original_result = result[0]
    original_result = commit_fmap(project, commit_sha, original_result)
    return original_result, project.metadata_storage


class ProjectCommitUpdateMapper(ProjectCommitMapper[T]):
    """
    Map a function over commits of all projects in a given collection.

    In addition, update the `MetadataStorage` of each project according
    to any changes incurred due to the provided map function. Note that
    if the initial `MetadataStorage` of each project differs,
    conflicting information is resolved in a first-come, first-serve
    basis.
    """

    def __init__(
            self,
            projects: Iterable[ProjectRepo],
            get_commit_iterator: Callable[[ProjectRepo],
                                          Iterable[str]],
            commit_fmap: Callable[[ProjectRepo,
                                   str,
                                   Optional[T]],
                                  T],
            task_description: Optional[str] = None,
            wait_on_interrupt: bool = True,
            terminate_on_except: bool = True):
        super().__init__(
            projects,
            get_commit_iterator,
            functools.partial(_commit_fmap_and_update,
                              commit_fmap),  # type: ignore
            task_description,
            wait_on_interrupt,
            terminate_on_except)

    def __call__(self,  # noqa: D102
                 max_workers: int = 1,
                 force_serial: bool = False) -> Dict[str,
                                                     Union[Optional[T], Except[T]]]:
        results = super().__call__(max_workers, force_serial)
        # get all project's metadata with the understanding that each
        # project only affected at most its own records
        storage = MetadataStorage()
        updated_projects = {p.name for p in self.projects}
        # ensure we sort insertions for deterministic serialization
        for p in sorted(self.projects, key=lambda p: p.name):
            result = typing.cast(
                Union[Optional[Tuple[T,
                                     MetadataStorage]],
                      Except[Tuple[T,
                                   MetadataStorage]]],
                results[p.name])
            exception = None
            value = result
            if isinstance(result, Except):
                exception = typing.cast(Except[T], result)
                value = result.value
            if value is None:
                warnings.warn(f"No results found for {p.name}")
                p_storage = p.metadata_storage
            else:
                value = typing.cast(Tuple[T, MetadataStorage], value)
                # strip storage from results
                if exception is not None:
                    # change mapped result value in place
                    exception.value = value[0]
                else:
                    results[p.name] = value[0]
                p_storage = value[1]
            for metadata in sorted(p_storage.get_all(p.name),
                                   key=lambda m: m.key):
                storage.insert(metadata)
            # capture non-updated metadata
            for other_p in sorted(
                    p_storage.projects.difference(updated_projects)):
                for metadata in sorted(p_storage.get_all(other_p),
                                       key=lambda m: m.key):
                    if metadata not in storage:
                        storage.insert(metadata)
        for p in self.projects:
            p.metadata_storage = storage
        return results

    def update_map(
        self,
        max_workers: int = 1,
        force_serial: bool = False
    ) -> Tuple[Dict[str,
                    Union[Optional[T],
                          Except[T]]],
               MetadataStorage]:
        """
        Map over the project commits and get updated metadata.

        Parameters
        ----------
        max_workers : int, optional
            The maximum number of subprocesses, by default 1, which
            will result in a sequential map over the projects.

        Returns
        -------
        Dict[str, Except[T}]
            The output of `map`.
        MetadataStorage
            The updated `MetadataStorage` for each mapped project.

        Warns
        -----
        UserWarning
            If a project does not have any results.

        See Also
        --------
        map : For more details on the return value.
        """
        result = self.map(max_workers, force_serial)
        storage = self.projects[0].metadata_storage
        return result, storage
