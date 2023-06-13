"""
Tools for handling repair mining cache.
"""
import glob
import os
from dataclasses import dataclass
from enum import IntEnum, auto
from pathlib import Path
from time import time
from typing import (
    Dict,
    Iterable,
    List,
    Optional,
    Protocol,
    Set,
    Tuple,
    Union,
    cast,
    runtime_checkable,
)

from prism.data.cache.types import ProjectBuildResult, ProjectCommitData
from prism.project.metadata import ProjectMetadata
from prism.util.io import Fmt, atomic_write, infer_fmt_from_ext
from prism.util.manager import ManagedServer
from prism.util.opam.version import Version, VersionString
from prism.util.radpytools import PathLike
from prism.util.serialize import Serializable


class CacheStatus(IntEnum):
    """
    Enum indicating status of cache object.
    """

    SUCCESS = auto()
    """
    Full command data was successfully extracted for this cache tuple.
    """
    BUILD_ERROR = auto()
    """
    A build error was encountered for this cache tuple, and no command
    data was extracted.
    """
    CACHE_ERROR = auto()
    """
    An error was encountered during command data extraction, so no
    command data was saved for this cache tuple.
    """
    OTHER_ERROR = auto()
    """
    An uncategorized error occurred that caused command data extraction
    for this cache tuple to fail.
    """


@dataclass
class CacheObjectStatus:
    """
    Dataclass storing status information for (project, commit, version).
    """

    project: str
    """
    Project that partially identifies this cache object
    """
    commit_hash: str
    """
    Commit hash that partially identifies this cache object
    """
    coq_version: str
    """
    Coq version that partially identifies this cache object
    """
    status: CacheStatus
    """
    Status of the (project, commit_hash, coq_version) cache object. This
    string can take one of the following values:
        * success
        * build error
        * cache error
        * other error
    """


@runtime_checkable
class CoqProjectBuildCacheProtocol(Protocol):
    """
    Object regulating access to repair mining cache on disk.

    On-disk structure:

    Root/
    ├── Project 1/
    |   ├── Commit hash 1/
    |   |   ├── cache_file_1.json
    |   |   ├── cache_file_2.json
    |   |   └── ...
    |   ├── Commit hash 2/
    |   └── ...
    ├── Project 2/
    |   └── ...
    └── ...
    """

    root: Path = Path("")
    """
    Root folder of repair mining cache structure
    """
    fmt_ext: str = ""
    """
    The extension for the cache files that defines their format.
    """
    start_time: float
    """
    The time in seconds since the Unix epoch that the current cache
    extraction process or script started.
    """
    _default_coq_versions: Set[str] = {
        '8.9.1',
        '8.10.2',
        '8.11.2',
        '8.12.2',
        '8.13.2',
        '8.14.1',
        '8.15.2'
    }
    """
    Default coq versions to look for when getting cache status.
    """
    # yapf: disable
    _error_suffixes: dict[str,
                          str] = {
                              'build_error': "_build_error.txt",
                              'cache_error': "_cache_error.txt",
                              'misc_error': "_misc_error.txt"}
    """
    Map from error type to suffix that is applied to error log files for
    that type.
    """
    _error_timestamp_suffixes: dict[str,
                                    str] = {
        k: v + ".timestamp" for k, v in _error_suffixes.items()}
    """
    Mapping form error type to suffix that is applied to error log file
    timestamp files of that type.
    """
    # yapf: enable

    def __contains__(  # noqa: D105
            self,
            obj: Union[ProjectCommitData,
                       ProjectMetadata,
                       Tuple[str, str, str]]) -> bool:
        return self.contains(obj)

    @property
    def fmt(self) -> Fmt:
        """
        Get the serialization format with which to cache data.
        """
        return infer_fmt_from_ext(self.fmt_ext)

    def _write_kernel(
            self,
            cache_id: Union[ProjectCommitData,
                            ProjectMetadata,
                            Tuple[str,
                                  str,
                                  str]],
            block: bool,
            file_contents: Union[str,
                                 Serializable],
            suffix: Optional[str] = None) -> Optional[str]:
        r"""
        Write a message or object to a text file.

        Any existing file contents are overwritten.

        Parameters
        ----------
        cache_id : Union[ProjectCommitData, \
                         ProjectMetadata, \
                         Tuple[str, str, str]]
            An object that identifies the cache to which the
            `file_contents` should be written.
        block : bool
            If true, return a ``"write complete"`` message.
        file_contents : Union[str, Serializable]
            The contents to write or serialized to the file.
        suffix : Optional[str], optional
            An optional suffix (including file extension) that uniquely
            identifies the written file, by default None, which
            corresponds to the cached build data itself.

        Returns
        -------
        str or None
            If `block`, return ``"write complete"``; otherwise, return
            nothing
        """
        # standardize inputs to get_path
        if isinstance(cache_id, tuple):
            file_path = self.get_path(*cache_id)
        else:
            file_path = self.get_path(cache_id)

        if suffix is not None:
            file_path = Path(str(file_path.with_suffix("")) + suffix)
        atomic_write(file_path, file_contents)
        # Write timestamp file
        timestamp_file_path = Path(str(file_path) + ".timestamp")
        timestamp = str(self.start_time)
        atomic_write(timestamp_file_path, timestamp)
        if block:
            return "write complete"
        else:
            return None

    def clear_error_files(self, metadata: ProjectMetadata) -> List[Path]:
        """
        Clear any existing error files for the provided data.

        Parameters
        ----------
        metadata : ProjectMetadata
            Metadata object for which old error logs are to be removed.

        Returns
        -------
        List[Path]
            A list of error log files removed, if any.

        Notes
        -----
        This method is necessary for situations where caches files have
        been extracted in a previous run, and now a new extraction run
        is being attempted. In case a cache object is successfully
        extracted on the subsequent run when it failed previously, it is
        important that the old irrelevant error files are removed so
        that the successful cache item is not shadowed.
        """
        file_path = self.get_path_from_metadata(metadata)
        files_to_remove: List[Path] = []
        files_removed: List[Path] = []
        for suffix_key in self._error_suffixes.keys():
            error_file = Path(
                str(file_path.with_suffix(""))
                + self._error_suffixes[suffix_key])
            timestamp_file = Path(
                str(file_path.with_suffix(""))
                + self._error_timestamp_suffixes[suffix_key])
            if timestamp_file.exists():
                with open(timestamp_file, "rt") as f:
                    timestamp = float(f.read())
                if timestamp < self.start_time:
                    files_to_remove.append(timestamp_file)
                    if error_file.exists():
                        files_to_remove.append(error_file)
        for file_to_remove in files_to_remove:
            os.remove(file_to_remove)
            files_removed.append(file_to_remove)
        return files_removed

    def contains(
        self,
        obj: Union[ProjectCommitData,
                   ProjectMetadata,
                   Tuple[str,
                         str,
                         str],
                   Tuple[str,
                         str,
                         str,
                         str]]
    ) -> bool:
        """
        Return whether an entry on disk exists for the given data.

        Parameters
        ----------
        obj : Union[ProjectCommitData, ProjectMetadata, Tuple[str]]
            An object that identifies a project commit's cache.
            When a tuple is given the different strings correspond to
            project name, commit hash, and coq version. When a fourth
            string is given in the tuple, it corresponds to specific
            file extension.  If only three strings are given, the
            file extension is assumed to be `.yml` corresponding
            to output cache file.

        Returns
        -------
        bool
            Whether data for the given object is already cached on disk.

        Raises
        ------
        TypeError
            If the object is not a `ProjectCommitData`,
            `ProjeceMetadata`, or iterable of fields.
        """
        if isinstance(obj,
                      ProjectCommitData) or isinstance(obj,
                                                       ProjectMetadata):
            status = self.get_status(obj)
        elif isinstance(obj, Iterable):
            status = self.get_status(*obj)
        else:
            raise TypeError(f"Arguments of type {type(obj)} not supported.")
        return status == CacheStatus.SUCCESS

    def get(
            self,
            project: str,
            commit: str,
            coq_version: str) -> ProjectCommitData:
        """
        Fetch a data object from the on-disk folder structure.

        Parameters
        ----------
        project : str
            The name of the project
        commit : str
            The commit hash to fetch from
        coq_version : str
            The Coq version

        Returns
        -------
        ProjectCommitData
            The fetched cache object

        Raises
        ------
        ValueError
            If the specified cache object does not exist on disk
        """
        data_path = self.get_path_from_fields(project, commit, coq_version)
        if not data_path.exists():
            raise ValueError(f"No cache file exists at {data_path}.")
        else:
            data = cast(ProjectCommitData, ProjectCommitData.load(data_path))
            return data

    def get_path(self, *args, **kwargs):
        """
        Get the file path for arguments identifying a cache.

        This function serves as an alias for each of
        `get_path_from_data`, `get_path_from_metadata`, and
        `get_path_from_fields`.
        """
        if len(args) == 1:
            data = args[0]
            if isinstance(data, ProjectCommitData):
                path = self.get_path_from_data(data, **kwargs)
            elif isinstance(data, ProjectMetadata):
                path = self.get_path_from_metadata(data, **kwargs)
            else:
                path = self.get_path_from_fields(*args, **kwargs)
        elif 'data' in kwargs:
            path = self.get_path_from_data(**kwargs)
        elif 'metadata' in kwargs:
            path = self.get_path_from_metadata(**kwargs)
        else:
            path = self.get_path_from_fields(*args, **kwargs)
        return path

    def get_path_from_data(self, data: ProjectCommitData) -> Path:
        """
        Get the file path for a given project commit cache.
        """
        return self.get_path_from_metadata(data.project_metadata)

    def get_path_from_fields(
            self,
            project: str,
            commit: str,
            coq_version: str,
            ext: Optional[str] = None) -> Path:
        """
        Get the file path for identifying fields of a cache.
        """
        if ext is None:
            ext = self.fmt_ext
        return self.root / project / commit / '.'.join(
            [self.format_coq_version(coq_version),
             ext])

    def get_path_from_metadata(self, metadata: ProjectMetadata) -> Path:
        """
        Get the file path for a given metadata.
        """
        assert metadata.commit_sha is not None
        assert metadata.coq_version is not None
        return self.get_path_from_fields(
            metadata.project_name,
            metadata.commit_sha,
            metadata.coq_version)

    def get_status(self, *args, **kwargs) -> Optional[CacheStatus]:
        """
        Get the status of an indicated cache object.

        Parameters
        ----------
        args
            Positional arguments to `get_path`.
        kwargs
            Keyword arguments to `get_path`.

        Returns
        -------
        Optional[str]
            A string describing the status of the cached object or None
            if the arguments do not describe an object in the cache.
        """
        path = self.get_path(*args, **kwargs)
        prefix = str(path.with_suffix(''))
        timestamps: Dict[CacheStatus,
                         float] = {}
        if path.exists():
            return CacheStatus.SUCCESS
        if Path(prefix + "_cache_error.txt").exists():
            with open(prefix + "_cache_error.txt.timestamp", "rt") as f:
                timestamps[CacheStatus.CACHE_ERROR] = float(f.read())
        if Path(prefix + "_build_error.txt").exists():
            with open(prefix + "_build_error.txt.timestamp", "rt") as f:
                timestamps[CacheStatus.BUILD_ERROR] = float(f.read())
        if Path(prefix + "_misc_error.txt").exists():
            with open(prefix + "_misc_error.txt.timestamp", "rt") as f:
                timestamps[CacheStatus.OTHER_ERROR] = float(f.read())
        if not timestamps:
            # No files were found
            return None
        # Return the status with the latest timestamp. If two match
        # somehow (shouldn't be possible) return the first.
        latest_timestamp = max(timestamps.values())
        for key in timestamps.keys():
            if timestamps[key] == latest_timestamp:
                return key
        raise RuntimeError(
            "Unable to get a max timestamp value. This shouldn't happen.")

    def get_status_counts(self) -> dict[CacheStatus, int]:
        """
        Get count of each cache status in the cache.

        Returns
        -------
        dict[CacheStatus, int]
            Dictionary of each cache status and the number of
            occurances of that status in the cache.
        """
        statuses = self.list_status()
        counts = {status: 0 for status in CacheStatus}
        for status_obj in statuses:
            counts[status_obj.status] += 1
        return counts

    def get_status_message(self) -> str:
        """
        Get status message to display.

        Returns
        -------
        str
            Message with a header, footer, and a line
            for each `CacheObjectStatus` value and the
            number of times they appear in the cache.
        """
        message = ""
        counts = self.get_status_counts()
        header = "".join(["-"] * 10)
        footer = "".join(["-"] * 10)
        body_parts = []
        for k, v in counts.items():
            body_parts.append(f"{k.name}: {v}")
        message_parts = [header] + body_parts + [footer]
        message = '\n'.join(message_parts)
        return message

    def list_projects(self) -> List[str]:
        """
        Generate a list of projects in cache.

        Returns
        -------
        List[str]
            A list of project names currently present in the cache
        """
        projects: List[str] = []
        for item in glob.glob(f"{str(self.root)}/*"):
            if Path(item).is_dir():
                projects.append(Path(item).stem)
        return projects

    def list_commits(
            self,
            projects: Optional[Iterable[str]] = None) -> Dict[str,
                                                              List[str]]:
        """
        Generate a list of commits for a given project or all projects.

        Parameters
        ----------
        projects : Optional[Iterable[str]], optional
            The projects to get commit hashes for. If None, return
            commit hashes for all projects, by default None.

        Returns
        -------
        Dict[str, List[str]]
            Mapping from project name to commit hash list
        """
        if projects is None:
            projects = self.list_projects()
        elif not isinstance(projects, Iterable):
            projects = [projects]
        output_dict = dict()
        for project in projects:
            commit_list: List[str] = []
            for item in glob.glob(f"{self.root / project}/*"):
                if Path(item).is_dir():
                    commit_list.append(Path(item).stem)
            output_dict[project] = commit_list
        return output_dict

    def list_status(
        self,
        projects: Optional[Iterable[str]] = None,
        commits: Optional[Dict[str,
                               List[str]]] = None,
        coq_versions: Optional[Iterable[Union[Version,
                                              VersionString]]] = None
    ) -> List[CacheObjectStatus]:
        """
        Generate a list of objects detailing cache status.

        Parameters
        ----------
        project : Optional[Iterable[str]], optional
            If given, return status for these projects only, by default
            None
        commit : Optional[Dict[str, List[str]]], optional
            If given, return status for these commit hashes only, by
            default None
        coq_versions : Optional[Iterable[Version]], optional
            If given, return status for these coq versions only, by
            default None

        Returns
        -------
        List[CoqVersionStatus]
            List of objects detailing cache status
        """
        if projects is None:
            projects = self.list_projects()
        if commits is None:
            commits = self.list_commits(projects)
        if coq_versions is None:
            coq_version_strs = self._default_coq_versions
        else:
            coq_version_strs = {str(v) for v in coq_versions}
        status_list = []
        for coq_version_str in coq_version_strs:
            coq_version = coq_version_str.replace(".", "_")
            for project in projects:
                for commit in commits[project]:
                    status_msg = self.get_status(project, commit, coq_version)
                    if status_msg is not None:
                        status_list.append(
                            CacheObjectStatus(
                                project,
                                commit,
                                coq_version_str,
                                status_msg))
        return status_list

    def list_status_failed_only(self,
                                *args,
                                **kwargs) -> List[CacheObjectStatus]:
        """
        Generate a list of objects detailing cache status, errors only.

        Returns
        -------
        List[CoqVersionStatus]
            List of objects detailing cache status
        """
        return list(
            filter(
                lambda x: x.status != CacheStatus.SUCCESS,
                self.list_status(*args,
                                 **kwargs)))

    def list_status_success_only(self,
                                 *args,
                                 **kwargs) -> List[CacheObjectStatus]:
        """
        Generate a list of objects detailing cache status, success only.

        Returns
        -------
        List[CoqVersionStatus]
            List of objects detailing cache status
        """
        return list(
            filter(
                lambda x: x.status == CacheStatus.SUCCESS,
                self.list_status(*args,
                                 **kwargs)))

    def write(self,
              data: ProjectCommitData,
              block: bool = True,
              _=None) -> Optional[str]:
        """
        Write to build cache.

        Parameters
        ----------
        data : ProjectCommitData
            Data to write to build cache
        block : bool
            If true, return a ``"write complete"`` message.

        Returns
        -------
        str or None
            If `block`, return ``"write complete"``; otherwise, return
            nothing

        Notes
        -----
        The final `_` parameter in the definition is provided for
        compatibility with the other write methods.
        """
        return self._write_kernel(data, block, data)

    def write_build_error_log(
            self,
            metadata: ProjectMetadata,
            block: bool,
            build_result: ProjectBuildResult) -> Optional[str]:
        """
        Write build error log to build cache directory.

        Parameters
        ----------
        metadata : ProjectMetadata
            Metadata for the project that had an error. Used by this
            method to get the correct path to write to.
        block : bool
            If true, return a ``"write complete"`` message.
        build_result : str
            A triple containing a presumed nonzero exit code, stdout,
            and stderr, in that order.

        Returns
        -------
        str or None
            If `block`, return ``"write complete"``; otherwise, return
            nothing
        """
        self.clear_error_files(metadata)
        str_to_write = "\n".join(
            [
                f"@@Exit code@@\n{build_result.exit_code}",
                f"@@stdout@@\n{build_result.stdout}",
                f"@@stderr@@\n{build_result.stderr}"
            ])
        return self._write_kernel(
            metadata,
            block,
            str_to_write,
            self._error_suffixes['build_error'])

    def write_cache_error_log(
            self,
            metadata: ProjectMetadata,
            block: bool,
            cache_error_log: str) -> Optional[str]:
        """
        Write caching error log to build cache directory.

        Parameters
        ----------
        metadata : ProjectMetadata
            Metadata for the project that had an error. Used by this
            method to get the correct path to write to.
        block : bool
            If true, return a ``"write complete"`` message.
        cache_error_log : str
            Caching error log string to write to file.

        Returns
        -------
        str or None
            If `block`, return ``"write complete"``; otherwise, return
            nothing
        """
        self.clear_error_files(metadata)
        return self._write_kernel(
            metadata,
            block,
            cache_error_log,
            self._error_suffixes['cache_error'])

    def write_metadata_file(self,
                            data: ProjectCommitData,
                            block: bool,
                            _=None) -> Optional[str]:
        """
        Write metadata-focused file to build cache directory.

        Parameters
        ----------
        data : ProjectCommitData
            Data to write to metadata file. Any data in `command_data`
            field is removed first
        block : bool
            If True, return a ``"write complete"`` message
        _ : _type_, optional
            Unused. Present only to maintain a uniform signature across
            write methods, by default None

        Returns
        -------
        str or None
            If `block`, return ``"write complete"``; otherwise, return
            nothing
        """
        data.command_data = dict()
        suffix = ".".join(["_extraction_info", self.fmt_ext])
        return self._write_kernel(data, block, data, suffix)

    def write_misc_error_log(
            self,
            metadata: ProjectMetadata,
            block: bool,
            misc_log: str) -> Optional[str]:
        """
        Write miscellaneous error log to build cache directory.

        Parameters
        ----------
        metadata : ProjectMetadata
            Metadata for the project that had an error. Used by this
            method to get the correct path to write to.
        block : bool
            If true, return a "write complete" message
        misc_log : str
            Miscellaneous error message to write to file.

        Returns
        -------
        str or None
            If `block`, return "write complete"; otherwise, return
            nothing
        """
        self.clear_error_files(metadata)
        return self._write_kernel(
            metadata,
            block,
            misc_log,
            self._error_suffixes['misc_error'])

    def write_timing_log(
            self,
            metadata: ProjectMetadata,
            block: bool,
            timing_log: str) -> Optional[str]:
        """
        Write timing log to build cache directory.

        Parameters
        ----------
        metadata : ProjectMetadata
            Metadata for the project that had an error. Used by this
            method to get the correct path to write to.
        block : bool
            If true, return a "write complete" message
        timing_log : str
            Timing log string to write to file.

        Returns
        -------
        str or None
            If `block`, return "write complete"; otherwise, return
            nothing
        """
        return self._write_kernel(metadata, block, timing_log, "_timing.txt")

    def write_worker_log(
            self,
            project_name: str,
            commit_sha: str,
            coq_version: str,
            block: bool,
            log: str) -> Optional[str]:
        """
        Write worker log to build cache directory.

        Parameters
        ----------
        project_name : str
            Name of the project built by worker.
        commit_sha : str
            Name of the project commit built by worker.
        coq_version : str
            Name of the coq version initially targeted during building.
        block : bool
            If true, return a "write complete" message
        log : str
            log string to write to file.

        Returns
        -------
        str or None
            If `block`, return "write complete"; otherwise, return
            nothing
        """
        return self._write_kernel(
            (project_name,
             commit_sha,
             coq_version),
            block,
            log,
            ".txt")

    @classmethod
    def format_coq_version(cls, coq_version: str) -> str:
        """
        Format a Coq version for use in a filename.
        """
        return coq_version.replace('.', '_')


class CoqProjectBuildCache(CoqProjectBuildCacheProtocol):
    """
    Implementation of CoqProjectBuildCacheProtocol with added __init__.
    """

    def __init__(
            self,
            root: PathLike,
            fmt_ext: str = "json",
            start_time: Optional[float] = None):
        self.root = Path(root)
        self.fmt_ext = fmt_ext
        if start_time is None:
            start_time = time()
        self.start_time = start_time
        if not self.root.exists():
            os.makedirs(self.root)


class CoqProjectBuildCacheServer(ManagedServer[CoqProjectBuildCache]):
    """
    A BaseManager-derived server for managing build cache.
    """
