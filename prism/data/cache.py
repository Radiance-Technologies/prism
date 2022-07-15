"""
Tools for handling repair mining cache.
"""
import os
import queue
import tempfile
from dataclasses import dataclass, field
from multiprocessing import Process, Queue
from pathlib import Path
from typing import Dict, Iterable, Optional, Set, Tuple, Union

import seutil as su

from prism.language.gallina.analyze import SexpInfo
from prism.project.metadata import ProjectMetadata
from prism.util.radpytools.dataclasses import immutable_dataclass


@dataclass
class VernacCommandData:
    """
    The evaluated result for a single Vernacular command.
    """

    identifier: Optional[str]
    """
    Identifier for the command being cached, e.g., the name of the
    corresponding theorem, lemma, or definition.
    If no identifier exists (for example, if it is an import statement)
    or can be meaningfully defined, then None.
    """
    command_type: str
    """
    The type of command, e.g., Theorem, Inductive, etc.
    """
    location: SexpInfo.Loc
    """
    The location of the command within a project.
    """
    command_error: Optional[str]
    """
    The error, if any, that results when trying to execute the command
    (e.g., within the ``sertop``). If there is no error, then None.
    """

    def __hash__(self) -> int:  # noqa: D105
        # do not include the error
        return hash(self.location)

    def dump(
            self,
            output_filepath: os.PathLike,
            fmt: su.io.Fmt = su.io.Fmt.yaml) -> None:
        """
        Serialize repair mining cache and writes to .yml file.

        Parameters
        ----------
        output_filepath : os.PathLike
            Filepath to which cache should be dumped.
        fmt : su.io.Fmt, optional
            Designated format of the output file,
            by default `su.io.Fmt.yaml`.
        """
        su.io.dump(output_filepath, self, fmt=fmt)

    @classmethod
    def load(
            cls,
            filepath: os.PathLike,
            fmt: su.io.Fmt = su.io.Fmt.yaml) -> 'VernacCommandData':
        """
        Load repair mining cache from file.

        Parameters
        ----------
        filepath : os.PathLike
            Filepath containing repair mining cache.
        fmt : su.io.Fmt, optional
            Designated format of the input file,
            by default `su.io.Fmt.yaml`.

        Returns
        -------
        ProjectCommitData
            Loaded repair mining cache
        """
        return su.io.load(filepath, fmt, clz=cls)


@dataclass
class ProjectCommitData:
    """
    Object that reflects the contents of a repair mining cache file.
    """

    project_metadata: ProjectMetadata
    """
    Metadata that identifies the project name, commit, Coq version, and
    other relevant data for reproduction and of the cache.
    """
    cache_entries: Dict[str, Set[VernacCommandData]]
    """
    A map from file names relative to the root of the project to the set
    of cached command results.
    """


@immutable_dataclass
class CoqProjectBuildCache:
    """
    Object regulating access to repair mining cache on disk.

    On-disk structure:

    Root/
    ├── Project 1/
    |   ├── Commit hash 1/
    |   |   ├── cache_file_1.yml
    |   |   ├── cache_file_2.yml
    |   |   └── ...
    |   ├── Commit hash 2/
    |   └── ...
    ├── Project 2/
    |   └── ...
    └── ...

    Attributes
    ----------
    root : Path
        Root folder of repair mining cache structure
    fmt : su.io.Fmt
        The serialization format with which to cache data.
    """

    root: Path
    """
    Root folder of repair mining cache structure
    """
    fmt: su.io.Fmt = su.io.Fmt.yaml
    """
    The serialization format with which to cache data.
    """
    _writer_queue: Queue = field(init=False)
    """
    Multiprocessing queue for operations on on-disk cache
    """
    _worker_process: Process = field(init=False)
    """
    The job that commits cache files to disk.
    """

    def __init__(self):
        """
        Instantiate object.

        Parameters
        ----------
        root : Path
            Root folder of repair mining cache structure
        """
        self.root = Path(self.root)
        if not self.root.exists():
            os.makedirs(self.root)
        self._writer_queue: Queue = Queue()
        self._worker_process = Process(target=self._writer_worker)
        self._worker_process.start()

    def __contains__(  # noqa: D105
            self,
            obj: Union[ProjectCommitData,
                       ProjectMetadata,
                       Tuple[str]]) -> bool:
        return self.contains(obj)

    def _contains_data(self, data: ProjectCommitData) -> bool:
        return self.get_path_from_data(data).exists()

    def _contains_metadata(self, metadata: ProjectMetadata) -> bool:
        return self.get_path_from_metadata(metadata).exists()

    def _contains_fields(self, fields: Tuple[str]) -> bool:
        return self.get_path_from_fields(*fields).exists()

    def _write(self, data: ProjectCommitData) -> None:
        """
        Write the project commit's data to disk.

        This should not in normal circumstances be called directly.

        Parameters
        ----------
        data : ProjectCommitData
            The data to be written to disk.
        """
        data_path = self.get_path_from_data(data)
        cache_dir = data_path.parent
        if not cache_dir.exists():
            os.makedirs(str(cache_dir))
        # Ensure that we write the cache atomically.
        # First, we write to a temporary file so that if we get
        # interrupted, we aren't left with a corrupted cache.
        with tempfile.mkstemp() as (f, tmpfile):
            f.write(su.io.serialize(data, fmt=self.fmt))
        # Then, we atomically move the file to the correct, final path.
        os.replace(tmpfile, data_path)

    def _writer_worker(self):
        """
        Wait for and serve requests to write data to file.
        """
        while True:
            try:
                data = self._writer_queue.get_nowait()
            except queue.Empty:
                continue
            self._write(data)

    def contains(
            self,
            obj: Union[ProjectCommitData,
                       ProjectMetadata,
                       Tuple[str]]) -> bool:
        """
        Return whether an entry on disk exists for the given data.

        Parameters
        ----------
        obj : Union[ProjectCommitData, ProjectMetadata, Tuple[str]]
            An object that identifies a project commit's cache.

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
        if isinstance(obj, ProjectCommitData):
            return self._contains_data(obj)
        elif isinstance(obj, ProjectMetadata):
            return self._contains_metadata(obj)
        elif isinstance(obj, Iterable):
            return self._contains_fields(*obj)
        else:
            raise TypeError(f"Arguments of type {type(obj)} not supported.")

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
            data = ProjectCommitData.load(data_path)
            return data

    def get_path_from_data(self, data: ProjectCommitData) -> Path:
        """
        Get the file path for a given project commit cache.
        """
        return self.get_path_from_metadata(data.project_metadata)

    def get_path_from_fields(
            self,
            project: str,
            commit: str,
            coq_version: str) -> str:
        """
        Get the file path for identifying fields of a cache.
        """
        return self.root / project / commit / (
            coq_version.replace(".",
                                "_") + ".yml")

    def get_path_from_metadata(self, metadata: ProjectMetadata) -> str:
        """
        Get the file path for a given metadata.
        """
        return self.get_path_from_fields(
            metadata.project_name,
            metadata.commit_sha,
            metadata.coq_version)

    def insert(self, data: ProjectCommitData):
        """
        Cache a new element of data on disk.

        Parameters
        ----------
        data : ProjectCommitData
            The data to be cached.

        Raises
        ------
        RuntimeError
            If the cache file already exists. In this case, `update`
            should be called instead.
        """
        if self._contains_data(data):
            raise RuntimeError(
                "Cache file already exists. Call `update` instead.")
        else:
            self.write(data)

    def update(self, data: ProjectCommitData) -> None:
        """
        Update an existing cache file on disk.

        Parameters
        ----------
        data : ProjectCommitData
            The object to be re-cached.

        Raises
        ------
        RuntimeError
            If the cache file does not exist, `insert` should be called
            instead
        """
        if not self._contains_data(data):
            raise RuntimeError(
                "Cache file does not exist. Call `insert` instead.")
        else:
            self.write(data)

    def write(self, data: ProjectMetadata) -> None:
        """
        Cache the data to disk regardless of whether it already exists.

        Parameters
        ----------
        data : ProjectMetadata
            The object to be cached.
        """
        self._writer_queue.put(data)
