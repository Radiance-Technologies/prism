"""
Module for storing cache extraction functions.
"""
import calendar
import copy
import logging
import multiprocessing as mp
import os
import typing
from datetime import datetime
from functools import partial
from io import StringIO
from multiprocessing import Pool
from pathlib import Path
from subprocess import CalledProcessError, TimeoutExpired
from threading import BoundedSemaphore
from time import time
from typing import (
    Callable,
    Dict,
    Generator,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
    TypeAlias,
    Union,
)

import tqdm
from seutil import io
from tqdm.contrib.concurrent import process_map
from traceback_with_variables import format_exc

from prism.data.cache.command_extractor import CommandExtractor
from prism.data.cache.server import (
    CacheStatus,
    CoqProjectBuildCache,
    CoqProjectBuildCacheProtocol,
    CoqProjectBuildCacheServer,
)
from prism.data.cache.types import (
    CommentDict,
    ProjectBuildEnvironment,
    ProjectBuildResult,
    ProjectCommitData,
    VernacCommandDataList,
    VernacDict,
)
from prism.data.commit_map import Except, ProjectCommitUpdateMapper
from prism.data.util import get_project_func
from prism.interface.coq.exception import CoqExn
from prism.interface.coq.re_patterns import QUALIFIED_IDENT_PATTERN
from prism.language.heuristic.parser import CoqComment, CoqSentence
from prism.project.base import SEM
from prism.project.exception import MissingMetadataError, ProjectBuildError
from prism.project.metadata import version_info
from prism.project.metadata.dataclass import ProjectMetadata
from prism.project.metadata.storage import MetadataStorage
from prism.project.repo import (
    ChangedCoqCommitIterator,
    CommitTraversalStrategy,
    ProjectRepo,
)
from prism.util.opam.version import OpamVersion, Version
from prism.util.radpytools import PathLike
from prism.util.radpytools.os import pushd
from prism.util.re import regex_from_options
from prism.util.swim import SwitchManager, UnsatisfiableConstraints

_loadpath_problem_pattern = regex_from_options(
    [
        s.replace(" ",
                  r"\s+")
        for s in [
            "[Ff]ile not found on loadpath",
            f"Can(?:'|no)t find file {QUALIFIED_IDENT_PATTERN.pattern}",
            r"[Cc]annot find library "
            rf"(?P<library>{QUALIFIED_IDENT_PATTERN.pattern})",
            "Cannot find a physical path bound ",
            "Unable to locate library"
        ]
    ] + [
        r".*library.*",
        r".*vo.*",
        r".*path.*",
        r".*[Ff]ile.*",
        r".*suffix.*",
        r".*prefix.*"
    ],
    False,
    False)

_DEBUG_SINGLE_COMMIT = False
"""
Set to True to skip cleaning prior to extraction.
"""
FALLBACK_EXCEPTION_MSG = (
    "Fallback extraction in the case of a failed build is not yet implemented.")


class ExtractVernacCommandsError(RuntimeError):
    """
    Extended RuntimeError with filename and parent properties.
    """

    def __init__(
            self,
            message: str,
            filename: str = "",
            parent_exception: Optional[Exception] = None,
            parent_stacktrace: Optional[str] = None):
        super().__init__(message)
        self.filename = filename
        self.parent = parent_exception
        self.parent_stacktrace = parent_stacktrace


class DefaultProcessProjectFallbackError(NotImplementedError):
    """
    A special case of parent raised by default_process_project_fallback.
    """

    pass


def extract_vernac_commands(
    project: ProjectRepo,
    files_to_use: Optional[Iterable[str]] = None,
    force_serial: bool = False,
    worker_semaphore: Optional[BoundedSemaphore] = None
) -> Tuple[VernacDict,
           CommentDict]:
    """
    Compile vernac commands from a project into a dict.

    Parameters
    ----------
    project : ProjectRepo
        The project from which to extract the vernac commands
    files_to_use : Iterable[str] | None
        An iterable of filenames to use for this project; or None. If
        None, all files are used. By default, None.
        This argument is especially useful for profiling.
    force_serial : bool, optional
        If this argument is true, disable parallel execution. Useful for
        debugging. By default False.
    worker_semaphore : Semaphore or None, optional
        Semaphore used to control the number of file workers than
        can run at once. By default None. If None, ignore.

    Returns
    -------
    VernacDict
        A map from file names to their extracted commands.
    """
    command_data: Dict[str,
                       VernacCommandDataList] = {}
    comment_data: Dict[str,
                       List[CoqComment]] = {}
    with pushd(project.dir_abspath):
        file_list = project.get_file_list(relative=True, dependency_order=True)
        if files_to_use:
            file_list = [f for f in file_list if f in files_to_use]
        # Remove files that don't have corresponding .vo files
        final_file_list = []
        for filename in file_list:
            path = Path(filename)
            vo = path.parent / (path.stem + ".vo")
            if not os.path.exists(vo):
                logging.info(
                    f"Skipped extraction for file {filename}. "
                    "No .vo file found.")
            else:
                final_file_list.append(filename)
        if force_serial:
            pbar = tqdm.tqdm(
                final_file_list,
                total=len(final_file_list),
                desc=f"Caching {project.name}@{project.short_sha}")
            for filename in pbar:
                # Verify that accompanying vo file exists first
                pbar.set_description(
                    f"Caching {project.name}@{project.short_sha}:{filename}")
                result = _extract_vernac_commands_worker(filename, project)
                if isinstance(result, ExtractVernacCommandsError):
                    if result.parent is not None:
                        raise result from result.parent
                    else:
                        raise result
                sentences, comments = result
                command_data[filename] = sentences
                comment_data[filename] = comments
        else:
            if worker_semaphore is None:
                raise ValueError(
                    "force_serial is False but the worker_semaphore is None. "
                    "This is not a valid combination of arguments.")
            arg_list = [(f, project, worker_semaphore) for f in final_file_list]
            results = process_map(
                _extract_vernac_commands_worker_star,
                arg_list,
                desc=f"Caching {project.name}@{project.short_sha}")
            for f, result in zip(final_file_list, results):
                if isinstance(result, ExtractVernacCommandsError):
                    if result.parent is not None:
                        raise result from result.parent
                    else:
                        raise result
                sentences, comments = result
                command_data[f] = sentences
                comment_data[f] = comments
    return command_data, comment_data


def _extract_vernac_commands_worker(
    filename: str,
    project: ProjectRepo,
    worker_semaphore: Optional[BoundedSemaphore] = None,
    pbar: Optional[tqdm.tqdm] = None
) -> Union[Tuple[VernacCommandDataList,
                 List[CoqComment]],
           ExtractVernacCommandsError]:
    """
    Provide worker function for file-parallel cache extraction.
    """
    if worker_semaphore is not None:
        worker_semaphore.acquire()
    try:
        assert project.serapi_options is not None, \
            "serapi_options must not be None"
        (sentences,
         comments) = typing.cast(
             Tuple[List[CoqSentence],
                   List[CoqComment]],
             project.get_sentences(
                 filename,
                 SEM.HEURISTIC,
                 return_locations=True,
                 return_comments=True,
                 glom_proofs=False))
        result = CommandExtractor(
            filename,
            sentences,
            opam_switch=project.opam_switch,
            serapi_options=project.serapi_options)
    except Exception as e:
        return ExtractVernacCommandsError(
            f"Error on {filename}",
            filename,
            e,
            format_exc(e))
    finally:
        if worker_semaphore is not None:
            worker_semaphore.release()
    if pbar is not None:
        pbar.update(1)
    return result.extracted_commands, comments


def _extract_vernac_commands_worker_star(
    args
) -> Union[Tuple[VernacCommandDataList,
                 List[CoqComment]],
           ExtractVernacCommandsError]:
    return _extract_vernac_commands_worker(*args)


def extract_cache(
    build_cache_client: CoqProjectBuildCacheProtocol,
    switch_manager: SwitchManager,
    project: ProjectRepo,
    commit_sha: str,
    process_project_fallback: Callable[[ProjectRepo],
                                       Tuple[VernacDict,
                                             CommentDict]],
    coq_version: Optional[str] = None,
    recache: Optional[Callable[
        [CoqProjectBuildCacheProtocol,
         ProjectRepo,
         str,
         str],
        bool]] = None,
    block: bool = False,
    files_to_use: Optional[Iterable[str]] = None,
    force_serial: bool = False,
    worker_semaphore: Optional[BoundedSemaphore] = None,
    max_memory: Optional[int] = None,
    max_runtime: Optional[int] = None,
) -> None:
    r"""
    Extract data from project commit and insert into `build_cache`.

    The cache is implemented as a file-and-directory-based
    repository structure (`CoqProjectBuildCache`) that provides
    storage of artifacts and concurrent access for parallel
    processes through the operating system's own file system.
    Directories identify projects and commits with a separate cache
    file per build environment (i.e., Coq version). The presence or
    absence of a cache file within the structure indicates whether
    the commit has been cached yet. The cache files themselves
    contain two key pieces of information (reflected in
    `ProjectCommitData`): the metadata for the commit and a map from
    Coq file paths in the project to sets of per-sentence build
    artifacts (represented by `VernacCommandData`).

    This function does not return any cache extracted. Instead, it
    modifies on-disk build cache by inserting any previously unseen
    cache artifacts.

    Parameters
    ----------
    build_cache_client : CoqProjectBuildCacheProtocol
        The client that can insert the build artifacts into the on-disk
        build cache.
    switch_manager : SwitchManager
        A source of switches in which to process the project.
    project : ProjectRepo
        The project from which to extract data.
    commit_sha : str
        The commit whose data should be extracted.
    process_project_fallback : Callable[[ProjectRepo], \
                                        Tuple[VernacDict, CommentDict]]
        Function that provides fallback vernacular command
        extraction for projects that do not build.
    coq_version : str or None, optional
        The version of Coq in which to build the project, by default
        None.
    recache : Callable[[CoqProjectBuildCache, ProjectRepo, str, str], \
                       bool] \
            or None, optional
        A function that for an existing entry in the cache returns
        whether it should be reprocessed or not.
    block : bool, optional
        Whether to use blocking cache writes, by default False
    files_to_use : Iterable[str] | None
        An iterable of files to use from this project; or None. If None,
        all files are used. By default, None.
        This argument is especially useful for profiling.
    force_serial : bool, optional
        If this argument is true, disable parallel execution. Useful for
        debugging. By default False.
    worker_semaphore : Semaphore or None, optional
        Semaphore used to control the number of file workers than
        can run at once, by default None. If None, ignore.
    max_memory : Optional[int], optional
        Maximum memory (bytes) allowed to build project, by default
        None
    max_runtime : Optional[int], optional
        Maximum cpu time (seconds) allowed to build project, by default
        None

    See Also
    --------
    prism.data.build_cache.CoqProjectBuildCache
    prism.data.build_cache.ProjectCommitData
    prism.data.build_cache.VernacCommandData
    """
    if coq_version is None:
        coq_version = project.metadata.coq_version
    assert coq_version is not None, "coq_version must not be None"
    if (not build_cache_client.contains((project.name,
                                         commit_sha,
                                         coq_version))
            or (recache is not None and recache(build_cache_client,
                                                project,
                                                commit_sha,
                                                coq_version))):
        extract_cache_new(
            build_cache_client,
            switch_manager,
            project,
            commit_sha,
            process_project_fallback,
            coq_version,
            block,
            files_to_use,
            force_serial,
            worker_semaphore,
            max_memory,
            max_runtime)


def _handle_build_error(
    build_error: Union[ProjectBuildError,
                       TimeoutExpired],
    build_cache_client: CoqProjectBuildCacheProtocol,
    project: ProjectRepo,
    block: bool,
    process_project_fallback: Callable[[ProjectRepo],
                                       Tuple[VernacDict,
                                             CommentDict]]
) -> Tuple[VernacDict,
           CommentDict]:
    r"""
    Handle and log a build error during cache extraction.

    Parameters
    ----------
    build_error : Union[ProjectBuildError, TimeoutExpired]
        The error thrown during the build process.
    build_cache_client : CoqProjectBuildCacheProtocol
        The cache.
    project : ProjectRepo
        The project checked out at the commit to be extracted.
    block : bool
        Whether to use blocking cache writes
    process_project_fallback : Callable[[ProjectRepo], \
                                        Tuple[VernacDict, CommentDict]]
        Function that provides fallback Vernacular command extraction
        for projects that do not build.

    Returns
    -------
    command_data : VernacDict
        Extracted commands from the `process_project_fallback`.
    comment_data : CommentDict]
        Extracted comments from the `process_project_fallback`.
    """
    if isinstance(build_error, ProjectBuildError):
        build_result = (
            build_error.return_code,
            build_error.stdout,
            build_error.stderr)
    else:
        stdout = build_error.stdout.decode(
            "utf-8") if build_error.stdout is not None else ''
        stderr = build_error.stderr.decode(
            "utf-8") if build_error.stderr is not None else ''
        build_result = (1, stdout, stderr)
    # Write the log before calling process_project_fallback
    # in case it raises an exception.
    build_cache_client.write_build_error_log(
        project.metadata,
        block,
        ProjectBuildResult(*build_result))
    return process_project_fallback(project)


def _handle_cache_error(
        cache_error: ExtractVernacCommandsError,
        build_cache_client: CoqProjectBuildCacheProtocol,
        project: ProjectRepo,
        block: bool,
        files_to_use: Optional[Iterable[str]],
        force_serial: bool,
        worker_semaphore: Optional[BoundedSemaphore],
        logger: logging.Logger,
        logger_stream: StringIO) -> Tuple[VernacDict,
                                          CommentDict]:
    """
    Handle and log errors during cache extraction proper.

    Parameters
    ----------
    cache_error : ExtractVernacCommandsError
        An error raised when extracting individual commands from a Coq
        file.
    build_cache_client : CoqProjectBuildCacheProtocol
        The cache.
    project : ProjectRepo
        The project checked out at the commit to be extracted.
    block : bool
        Whether to use blocking cache writes
    files_to_use : Iterable[str] | None
        An iterable of files to use from this project; or None. If None,
        all files are used. By default, None.
        This argument is especially useful for profiling.
    force_serial : bool
        If this argument is true, disable parallel execution. Useful for
        debugging.
    worker_semaphore : Optional[BoundedSemaphore]
        Semaphore used to control the number of file workers that can
        run at once. If None, ignore.
    logger : logging.Logger
        A logger with which to record the error.
    logger_stream : StringIO
        A flushable stream for the `logger`.

    Returns
    -------
    command_data : VernacDict
        Extracted commands from a repeated attempt at
        `extract_vernac_commands` if the error can be handled.
    comment_data : CommentDict]
        Extracted comments from a repeated attempt at
        `extract_vernac_commands` if the error can be handled.

    Raises
    ------
    ExtractVernacCommandsError
        If the given `cache_error` could not be handled
    """
    if isinstance(cache_error.parent, CoqExn):
        m = _loadpath_problem_pattern.search(cache_error.parent.msg)
        if m is not None:
            # problem with loadpath implies likely
            # IQR flag issue
            project.infer_serapi_options()
            try:
                return extract_vernac_commands(
                    project,
                    files_to_use,
                    force_serial,
                    worker_semaphore)
            except ExtractVernacCommandsError as e2:
                # replace error
                cache_error = e2
    logger.critical(f"Filename: {cache_error.filename}\n")
    logger.critical(f"Parent stack trace:\n{cache_error.parent_stacktrace}\n")
    logger.exception(cache_error)
    logger_stream.flush()
    logged_text = logger_stream.getvalue()
    build_cache_client.write_cache_error_log(
        project.metadata,
        block,
        logged_text)
    raise


def _handle_misc_error(
        misc_error: Exception,
        build_cache_client: CoqProjectBuildCacheProtocol,
        project_metadata: ProjectMetadata,
        block: bool,
        logger: logging.Logger,
        logger_stream: StringIO) -> None:
    """
    Log any unexpected errors in the cache extraction process.

    Parameters
    ----------
    misc_error : Exception
        An unhandled error raised during cache extraction.
    build_cache_client : CoqProjectBuildCacheProtocol
        The cache.
    project_metadata : ProjectMetadata
        The metadata corresponding to the extracted commit and
        Coq version.
    block : bool
        Whether to use blocking cache writes
    logger : logging.Logger
        A logger with which to record the error.
    logger_stream : StringIO
        A flushable stream for the `logger`.
    """
    logger.critical(
        "An exception occurred outside of extracting vernacular commands.\n")
    # If a subprocess command failed, capture the standard
    # output and error
    if isinstance(misc_error, CalledProcessError):
        logger.critical(f"stdout:\n{misc_error.stdout}\n")
        logger.critical(f"stderr:\n{misc_error.stderr}\n")
    logger.exception(misc_error)
    logger_stream.flush()
    logged_text = logger_stream.getvalue()
    build_cache_client.write_misc_error_log(
        project_metadata,
        block,
        logged_text)


def extract_cache_new(
    build_cache_client: CoqProjectBuildCacheProtocol,
    switch_manager: SwitchManager,
    project: ProjectRepo,
    commit_sha: str,
    process_project_fallback: Callable[[ProjectRepo],
                                       Tuple[VernacDict,
                                             CommentDict]],
    coq_version: str,
    block: bool,
    files_to_use: Optional[Iterable[str]],
    force_serial: bool,
    worker_semaphore: Optional[BoundedSemaphore],
    max_memory: Optional[int],
    max_runtime: Optional[int],
):
    r"""
    Extract a new cache object and insert it into the build cache.

    Parameters
    ----------
    build_cache_client : CoqProjectBuildCacheClient
        The client that can communicate the build cache to be written to
        the build cache server
    switch_manager : SwitchManager
        A source of switches in which to process the project.
    project : ProjectRepo
        The project from which to extract data.
    commit_sha : str
        The commit whose data should be extracted.
    process_project_fallback : Callable[[ProjectRepo], \
                                        Tuple[VernacDict, CommentDict]]
        Function that provides fallback Vernacular command extraction
        for projects that do not build.
    coq_version : str
        The version of Coq in which to build the project.
    block : bool
        Whether to use blocking cache writes
    files_to_use : Iterable[str] | None
        An iterable of files to use from this project; or None. If None,
        all files are used. By default, None.
        This argument is especially useful for profiling.
    force_serial : bool
        If this argument is true, disable parallel execution. Useful for
        debugging.
    worker_semaphore : BoundedSemaphore or None
        Semaphore used to control the number of file workers that can
        run at once. If None, ignore.
    max_memory : Optional[int]
        Maximum memory (bytes) allowed to build project
    max_runtime : Optional[int]
        Maximum cpu time (seconds) allowed to build project
    """
    # Construct a logger local to this function and unique to this PID
    pname = project.name
    sha = commit_sha or project.commit_sha
    coq = coq_version or project.coq_version
    pid: int = os.getpid()

    # Construct project build logger.
    build_logger = logging.getLogger(f'{pname}-{sha}-{coq}')
    build_logger.setLevel(logging.DEBUG)
    build_logger_stream = StringIO()
    build_handler = logging.StreamHandler(build_logger_stream)
    build_handler.setFormatter(logging.Formatter('%(name)-12s: %(message)s'))
    build_logger.addHandler(build_handler)

    # Construct error logger.
    extract_logger = logging.getLogger(f'extract_vernac_commands-{pid}')
    extract_logger_stream = StringIO()
    extract_handler = logging.StreamHandler(extract_logger_stream)
    extract_logger.addHandler(extract_handler)

    # Peform extraction using build_logger to log internal project log
    # messages.
    with project.project_logger(build_logger) as _:
        original_switch = project.opam_switch
        managed_switch_kwargs = {
            'coq_version': coq_version,
            'variables': {
                'build': True,
                'post': True,
                'dev': True
            },
            'release': False,
            'switch_manager': switch_manager,
        }
        # Initialize these variables so fallback data can definitely
        # be written later.
        commit_message = None
        comment_data = None
        file_dependencies = None
        build_result = (1, "", "")
        try:
            # Make sure there aren't any changes or uncommitted files
            # left over from previous iterations, then check out the
            # current commit
            if not _DEBUG_SINGLE_COMMIT:
                project.git.reset('--hard')
                project.git.clean('-fdx')
            project.git.checkout(commit_sha)
            if not _DEBUG_SINGLE_COMMIT:
                project.submodule_update(
                    init=True,
                    recursive=True,
                    keep_going=True,
                    force_remove=True,
                    force_reset=True)
            # process the commit
            commit_message = project.commit().message
            if isinstance(commit_message, bytes):
                commit_message = commit_message.decode("utf-8")
            try:
                build_result = project.build(
                    managed_switch_kwargs=managed_switch_kwargs,
                    max_runtime=max_runtime,
                    max_memory=max_memory)
            except (ProjectBuildError, TimeoutExpired) as pbe:
                (command_data,
                 comment_data) = _handle_build_error(
                     build_error=pbe,
                     build_cache_client=build_cache_client,
                     project=project,
                     block=block,
                     process_project_fallback=process_project_fallback)
            else:
                inner_start_time = time()
                try:
                    command_data, comment_data = extract_vernac_commands(
                        project,
                        files_to_use,
                        force_serial,
                        worker_semaphore)
                except ExtractVernacCommandsError as e:
                    (command_data,
                     comment_data) = _handle_cache_error(
                         cache_error=e,
                         build_cache_client=build_cache_client,
                         project=project,
                         block=block,
                         files_to_use=files_to_use,
                         force_serial=force_serial,
                         worker_semaphore=worker_semaphore,
                         logger=extract_logger,
                         logger_stream=extract_logger_stream)
                else:
                    # This branch gets hit only if cache was
                    # successfully extracted.
                    build_cache_client.clear_error_files(project.metadata)
                finally:
                    inner_elapsed_time = time() - inner_start_time
                    build_cache_client.write_timing_log(
                        project.metadata,
                        block,
                        "Elapsed time in extract_vernac_commands:"
                        f" {inner_elapsed_time} s")
            try:
                file_dependencies = project.get_file_dependencies()
            except (MissingMetadataError, CalledProcessError):
                extract_logger.exception(
                    "Failed to get file dependencies. Are the IQR flags set/correct?"
                )
                file_dependencies = None
            data = ProjectCommitData(
                project.metadata,
                command_data,
                commit_message,
                comment_data,
                file_dependencies,
                ProjectBuildEnvironment(project.opam_switch.export()),
                ProjectBuildResult(*build_result))
            build_cache_client.write(data, block)
        except ExtractVernacCommandsError:
            # Don't re-log extract_vernac_commands errors
            project_metadata = project.metadata
        except DefaultProcessProjectFallbackError:
            # Also don't re-log the not-implemented error from build
            # errors
            project_metadata = project.metadata
        except Exception as e:
            project_metadata = project.metadata
            if isinstance(e, UnsatisfiableConstraints):
                project_metadata = copy.copy(project_metadata)
                project_metadata.coq_version = coq_version
                project_metadata.serapi_version = version_info.get_serapi_version(
                    coq_version)
            _handle_misc_error(
                misc_error=e,
                build_cache_client=build_cache_client,
                project_metadata=project_metadata,
                block=block,
                logger=extract_logger,
                logger_stream=extract_logger_stream)
        else:
            project_metadata = project.metadata
        finally:
            try:
                assert commit_message is None or isinstance(commit_message, str)
                fallback_data = ProjectCommitData(
                    project_metadata,
                    {},
                    commit_message,
                    comment_data,
                    file_dependencies,
                    ProjectBuildEnvironment(project.opam_switch.export()),
                    ProjectBuildResult(*build_result))
                build_cache_client.write_metadata_file(fallback_data, False)
            finally:
                # Nested `finally` because this **must** happen
                # Release the switch
                switch_manager.release_switch(project.opam_switch)
                project.opam_switch = original_switch
                logged_text = build_logger_stream.getvalue()
                build_cache_client.write_worker_log(
                    pname,
                    sha,
                    coq,
                    block,
                    logged_text)


# Abbreviation defined to satisfy conflicting autoformatting and style
# requirements in cache_extract_commit_iterator.
CTS: TypeAlias = CommitTraversalStrategy


def cache_extract_commit_iterator(
        project: ProjectRepo,
        starting_commit_sha: str,
        max_num_commits: Optional[int],
        march_strategy: CTS = CTS.CURLICUE_NEW,
        date_limit: bool = False) -> Generator[str,
                                               None,
                                               None]:
    """
    Provide default commit iterator for cache extraction.

    Commits are limited to those that occur on or after January 1, 2019,
    which roughly coincides with the release of Coq 8.9.1.
    """
    iterator = ChangedCoqCommitIterator(
        project,
        starting_commit_sha,
        march_strategy)
    i = 0
    for item in iterator:
        # get commit object
        item = project.commit(item)
        # Define the minimum date; convert it to seconds since epoch
        limit_date = datetime(2019, 1, 1, 0, 0, 0)
        limit_epoch = calendar.timegm(limit_date.timetuple())
        # committed_date is in seconds since epoch
        if not date_limit or (item.committed_date is not None
                              and item.committed_date >= limit_epoch):
            i += 1
            yield item.hexsha
        if max_num_commits is not None and i >= max_num_commits:
            break


class CacheExtractor:
    """
    Class for managing a broad Coq project cache extraction process.
    """

    def __init__(
        self,
        cache_dir: str,
        metadata_storage_file: str,
        swim: SwitchManager,
        default_commits_path: str,
        commit_iterator_factory: Callable[[ProjectRepo,
                                           str],
                                          Iterable[str]],
        coq_version_iterator: Optional[Callable[[ProjectRepo,
                                                 str],
                                                Iterable[Union[
                                                    str,
                                                    Version]]]] = None,
        process_project_fallback: Optional[Callable[[ProjectRepo],
                                                    Tuple[VernacDict,
                                                          CommentDict]]] = None,
        recache: Optional[Callable[
            [CoqProjectBuildCacheProtocol,
             ProjectRepo,
             str,
             str],
            bool]] = None,
        files_to_use: Optional[Dict[str,
                                    Iterable[str]]] = None,
        cache_fmt_ext: Optional[str] = None,
        mds_fmt: Optional[str] = None,
        coq_version_stop_callback: Callable[
            [CoqProjectBuildCacheProtocol,
             str,
             str,
             Sequence[str | Version]],
            bool] | None = None,
    ):
        self.cache_kwargs = {
            "fmt_ext": cache_fmt_ext
        } if cache_fmt_ext else {}
        """
        Keyword arguments for constructing the project cache build
        server
        """
        self.mds_kwargs = {
            "fmt": mds_fmt
        } if mds_fmt else {}
        """
        Keyword arguments for constructing the metadata storage
        """
        self.cache_dir = cache_dir
        """
        Directory the cache will be read from and written to
        """
        self.swim = swim
        """
        The switch manager used for extraction
        """
        self.md_storage = MetadataStorage.load(
            metadata_storage_file,
            **self.mds_kwargs)
        """
        The project metadata storage object
        """
        self.md_storage_file = metadata_storage_file
        """
        The project metadata storage file
        """
        self.commit_iterator_factory = commit_iterator_factory
        """
        The factory function that produces a commit iterator given a
        project and a starting commmit SHA
        """
        self.default_commits_path = default_commits_path
        """
        Path to a file containing default commits for each project.
        """
        self.default_commits: Dict[str,
                                   List[str]] = typing.cast(
                                       Dict[str,
                                            List[str]],
                                       io.load(
                                           str(self.default_commits_path),
                                           clz=dict))
        """
        The default commits for each project.
        """

        if coq_version_iterator is None:
            coq_version_iterator = self.default_coq_version_iterator
        self.coq_version_iterator = coq_version_iterator
        """
        An iterator over coq versions
        """

        if process_project_fallback is None:
            process_project_fallback = self.default_process_project_fallback
        self.process_project_fallback = process_project_fallback
        """
        Function to process commits for cache extraction if they do not
        build
        """

        self.files_to_use_map = files_to_use
        """
        A mapping from project name to files to use from that project;
        or None. If None, all files are used. By default, None.
        This argument is especially useful for profiling.
        """

        if recache is None:
            recache = self.default_recache
        self.recache = recache
        """
        Function that determines when a project commit's cached
        artifacts should be recomputed.
        """

        if coq_version_stop_callback is None:
            coq_version_stop_callback = self.default_coq_version_stop_callback
        self.coq_version_stop_callback = coq_version_stop_callback
        """
        Call this function on the cache, project name, commit hash,
        and sequence of Coq versions encountered so far to determine
        whether or not to stop iterating over Coq versions.
        """

    def get_commit_iterator_func(
            self) -> Callable[[ProjectRepo],
                              Iterable[str]]:
        """
        Return a commit iterator function.

        Returns
        -------
        Callable[[ProjectRepo], Iterator[str]]
            The chosen commit iterator function
        """
        return partial(
            CacheExtractor._commit_iterator_func,
            default_commits=self.default_commits,
            commit_iterator_factory=self.commit_iterator_factory)

    def get_extract_cache_func(
        self,
        force_serial: bool = False,
        worker_semaphore: Optional[BoundedSemaphore] = None,
        max_memory: Optional[int] = None,
        max_runtime: Optional[int] = None,
    ) -> Callable[[ProjectRepo,
                   str,
                   None],
                  None]:
        """
        Return the cache extraction function for the commit mapper.

        Parameters
        ----------
        force_serial : bool, optional
            If this argument is true, disable parallel execution. Useful
            for debugging. By default False.
        worker_semaphore : Semaphore or None, optional
            Semaphore used to control the number of file workers than
            can run at once, by default None. If None, ignore.
        max_memory : Optional[int], optional
            Maximum memory (bytes) allowed to build project, by default
            None
        max_runtime : Optional[int], optional
            Maximum cpu time (seconds) allowed to build project, by
            default None

        Returns
        -------
        Callable[[ProjectRepo, str, None], None]
            The extraction function to be mapped
        """
        return partial(
            CacheExtractor.extract_cache_func,
            build_cache_client=self.cache_client,
            switch_manager=self.swim,
            process_project_fallback=self.process_project_fallback,
            recache=self.recache,
            coq_version_iterator=self.coq_version_iterator,
            files_to_use_map=self.files_to_use_map,
            force_serial=force_serial,
            worker_semaphore=worker_semaphore,
            max_memory=max_memory,
            max_runtime=max_runtime,
            coq_version_stop_callback=self.coq_version_stop_callback)

    def run(
        self,
        root_path: PathLike,
        log_dir: Optional[PathLike] = None,
        updated_md_storage_file: Optional[PathLike] = None,
        extract_nprocs: int = 8,
        force_serial: bool = False,
        n_build_workers: int = 1,
        project_names: Optional[List[str]] = None,
        max_procs_file_level: int = 0,
        max_memory: Optional[int] = None,
        max_runtime: Optional[int] = None,
    ) -> None:
        """
        Build all projects at `root_path` and save updated metadata.

        Parameters
        ----------
        root_path : PathLike
            The root directory containing each project's directory.
            The project directories do not need to already exist.
        log_dir : PathLike or None, optional
            Directory to store log file(s) in, by default the directory
            that the metadata storage file is loaded from
        updated_md_storage_file : PathLike or None, optional
            File to save the updated metadata storage file to, by
            default the original file's parent directory /
            "updated_metadata.yml"
        extract_nprocs : int, optional
            Number of workers to allow for cache extraction, by default
            8
        force_serial : bool, optional
            If this argument is true, disable parallel execution all
            along the cache extraction pipeline. Useful for debugging.
            By default False.
        n_build_workers : int, optional
            The number of workers to allow per project when executing
            the `build` function, by default 1.
        project_names : list of str or None, optional
            If a list is provided, select only projects with names on
            the list for extraction. If projects on the given list
            aren't found, a warning is given. By default None.
        max_procs_file_level : int, optional
            Maximum number of active workers to allow at once on the
            file-level of extraction, by default 0. If 0, allow
            unlimited processes at this level.
        max_memory : Optional[int], optional
            Maximum memory (bytes) allowed to build project, by default
            None
        max_runtime : Optional[int], optional
            Maximum cpu time (seconds) allowed to build project, by
            default None
        """
        if log_dir is None:
            log_dir = Path(self.md_storage_file).parent
        # Generate list of projects
        project_list = self.md_storage.projects
        if project_names is not None:
            project_list = [p for p in project_list if p in project_names]
        projects = list(
            tqdm.tqdm(
                Pool(20).imap(
                    get_project_func(
                        root_path,
                        self.md_storage,
                        n_build_workers),
                    project_list),
                desc="Initializing project instances",
                total=len(project_list)))
        # Issue a warning if any requested projects are not present in
        # metadata.
        if project_names is not None:
            actual_project_set = {p.name for p in projects}
            requested_project_set = set(project_names)
            diff = requested_project_set.difference(actual_project_set)
            if diff:
                logging.warn(
                    "The following projects were requested but were not "
                    f"found: {', '.join(diff)}")
        if force_serial:
            manager = None
        else:
            manager = mp.Manager()
        # The following CoqProjectBuildCacheServer is created whether or
        # not force_serial is True, even though the server is not used
        # if force_serial is True. The overhead of starting a server is
        # not so great that it would be worth complicating the control
        # flow to avoid it in the force_serial=True case.
        with CoqProjectBuildCacheServer() as cache_server:
            if force_serial:
                factory = CoqProjectBuildCache
            else:
                factory = cache_server.Client
            self.cache_client = factory(self.cache_dir, **self.cache_kwargs)
            # Create semaphore for controlling file-level workers
            if manager is not None:
                nprocs = os.cpu_count(
                ) if not max_procs_file_level else max_procs_file_level
                worker_semaphore = manager.BoundedSemaphore(nprocs)
            else:
                worker_semaphore = None
            # Create commit mapper
            project_looper = ProjectCommitUpdateMapper[None](
                projects,
                self.get_commit_iterator_func(),
                self.get_extract_cache_func(
                    force_serial,
                    worker_semaphore,
                    max_memory=max_memory,
                    max_runtime=max_runtime),
                "Extracting cache",
                terminate_on_except=False)
            # Extract cache in parallel
            results, metadata_storage = project_looper.update_map(
                extract_nprocs,
                force_serial)
            # report errors
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
            with open(os.path.join(log_dir, "extract_cache.log"), "wt") as f:
                for p, result in results.items():
                    if isinstance(result, Except):
                        print(
                            f"{type(result.exception)} encountered in project {p}:"
                        )
                        print(result.trace)
                        f.write(
                            '\n'.join(
                                [
                                    "##########################################"
                                    "#########",
                                    f"{type(result.exception)} encountered in"
                                    f" project {p}:",
                                    result.trace
                                ]))
            # update metadata
            if updated_md_storage_file:
                metadata_storage.dump(metadata_storage, updated_md_storage_file)
            print("Done")

    @staticmethod
    def _commit_iterator_func(
        project: ProjectRepo,
        default_commits: Dict[str,
                              List[str]],
        commit_iterator_factory: Callable[[ProjectRepo,
                                           str],
                                          Iterable[str]]
    ) -> Iterable[str]:
        # Just in case the local repo is out of date
        for remote in project.remotes:
            remote.fetch()
        try:
            starting_commit_sha = default_commits[
                project.metadata.project_name][0]
        except IndexError:
            # There's at least one project in the default commits file
            # without a default commit; skip that one and any others
            # like it.
            return []
        return commit_iterator_factory(project, starting_commit_sha)

    @classmethod
    def default_coq_version_iterator(cls,
                                     _project: ProjectRepo,
                                     _commit: str) -> List[str]:
        """
        Extract build caches for all Coq versions we consider.
        """
        return [
            "8.9.1",
            "8.10.2",
            "8.11.2",
            "8.12.2",
            "8.13.2",
            "8.14.1",
            "8.15.2"
        ]

    @classmethod
    def default_coq_version_stop_callback(
            cls,
            cache: CoqProjectBuildCacheProtocol,
            project_name: str,
            commit_sha: str,
            coq_versions_observed_so_far: Sequence[str | Version]) -> bool:
        """
        Stop Coq version iteration if the last version was successful.

        Parameters
        ----------
        cache : CoqProjectBuildCacheProtocol
            Cache to check for successful extraction
        project_name : str
            The name of the current project being extracted
        commit_sha : str
            The commit hash currently being extracted
        coq_versions_observed_so_far : Sequence[str  |  Version]
            A sequence of Coq versions that have been observed so far.

        Returns
        -------
        bool
            True if Coq version iterator should stop, False otherwise.
        """
        if cache.get_status(
                project_name,
                commit_sha,
                str(coq_versions_observed_so_far[-1])) == CacheStatus.SUCCESS:
            # just build the newest version and call it a day.
            return True
        return False

    @classmethod
    def default_process_project_fallback(cls,
                                         _project: ProjectRepo
                                         ) -> Tuple[VernacDict,
                                                    CommentDict]:
        """
        By default, do nothing on project build failure.
        """
        raise DefaultProcessProjectFallbackError(FALLBACK_EXCEPTION_MSG)

    @classmethod
    def default_recache(
            cls,
            _build_cache: CoqProjectBuildCacheProtocol,
            _project: ProjectRepo,
            _commit_sha: str,
            _coq_version: str) -> bool:
        """
        By default, do not recache anything.
        """
        return False

    @classmethod
    def extract_cache_func(
        cls,
        project: ProjectRepo,
        commit_sha: str,
        _result: None,
        build_cache_client: CoqProjectBuildCacheProtocol,
        switch_manager: SwitchManager,
        process_project_fallback: Callable[[ProjectRepo],
                                           Tuple[VernacDict,
                                                 CommentDict]],
        recache: Callable[[CoqProjectBuildCacheProtocol,
                           ProjectRepo,
                           str,
                           str],
                          bool],
        coq_version_iterator: Callable[[ProjectRepo,
                                        str],
                                       Iterable[str | Version]],
        files_to_use_map: Optional[Dict[str,
                                        Iterable[str]]],
        force_serial: bool,
        worker_semaphore: Optional[BoundedSemaphore],
        max_memory: Optional[int],
        max_runtime: Optional[int],
        coq_version_stop_callback: Callable[
            [CoqProjectBuildCacheProtocol,
             str,
             str,
             Sequence[str | Version]],
            bool]):
        r"""
        Extract cache.

        Parameters
        ----------
        project : ProjectRepo
            The project to extract cache from
        commit_sha : str
            The commit to extract cache from
        _result : None
            Left empty for compatibility with `ProjectCommitMapper`
        build_cache_client : CoqProjectbuildCacheProtocol
            A mapping from project name to build cache client, used to
            write extracted cache to disk
        switch_manager : SwitchManager
            A switch manager to use during extraction
        process_project_fallback : Callable[[ProjectRepo], \
                                            Tuple[VernacDict, \
                                                  CommentDict]]
            A function that does a best-effort cache extraction when the
            project does not build
        recache : Callable[[CoqProjectBuildCache, ProjectRepo, str, \
                            str], \
                           bool]
            A function that for an existing entry in the cache returns
            whether it should be reprocessed or not.
        coq_version_iterator : Callable[[ProjectRepo, str],
                                        Iterable[Union[str, Version]]]
            A function that returns an iterable over allowable coq
            versions
        files_to_use_map : Dict[str, Iterable[str]] | None
            A mapping from project name to files to use from that
            project; or None. If None, all files are used. By default,
            None. This argument is especially useful for profiling.
        force_serial : bool
            If this argument is true, disable parallel execution. Useful
            for debugging.
        worker_semaphore : Semaphore or None
            Semaphore used to control the number of file workers than
            can run at once. If None, ignore.
        max_memory : Optional[int]
            Maximum memory (bytes) allowed to build project
        max_runtime : Optional[int]
            Maximum cpu time (seconds) allowed to build project
        coq_version_stop_callback : Callable[ \
                [CoqProjectBuildCacheProtocol, \
                 str, \
                 str, \
                 Sequence[str | Version]], \
                bool]
            Call this function on the cache, project name, commit hash,
            and sequence of Coq versions encountered so far to determine
            whether or not to stop iterating over Coq versions.
        """
        # newest first
        sorted_coq_version_iterator = sorted(
            coq_version_iterator(project,
                                 commit_sha),
            key=lambda x: OpamVersion.parse(x) if isinstance(x,
                                                             str) else x,
            reverse=True)
        pbar = tqdm.tqdm(sorted_coq_version_iterator, desc="Coq version")
        files_to_use = None
        if files_to_use_map is not None:
            try:
                files_to_use = files_to_use_map[f"{project.name}@{commit_sha}"]
            except KeyError:
                try:
                    files_to_use = files_to_use_map[project.name]
                except KeyError:
                    files_to_use = None
        coq_versions_observed_so_far: list[str | Version] = []
        for coq_version in pbar:
            coq_versions_observed_so_far.append(coq_version)
            pbar.set_description(
                f"Coq version ({project.name}@{commit_sha[: 8]}): {coq_version}"
            )
            extract_cache(
                build_cache_client,
                switch_manager,
                project,
                commit_sha,
                process_project_fallback,
                str(coq_version),
                recache,
                files_to_use=files_to_use,
                force_serial=force_serial,
                worker_semaphore=worker_semaphore,
                max_memory=max_memory,
                max_runtime=max_runtime,
            )
            if coq_version_stop_callback(build_cache_client,
                                         project.name,
                                         commit_sha,
                                         coq_versions_observed_so_far):
                break
