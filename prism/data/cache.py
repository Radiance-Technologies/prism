"""
Tools for handling repair mining cache.
"""
import hashlib
import os
import queue
from dataclasses import dataclass
from multiprocessing import Process, Queue
from pathlib import Path
from typing import List

import seutil as su

from prism.project.metadata import ProjectMetadata


@dataclass(frozen=True)
class RepairMiningCache:
    """
    Dataclass representing repair mining cache objects.
    """

    identifier: str
    """
    Unique (relative to the containing file) identifier for the Coq
    object being cached
    """
    object_type: str
    """The type of Coq entity represented by this cache object"""
    file_path: Path
    """Path to the file from which this cached block was created"""
    line_numbers: List[int]
    """Line numbers from which this cached block was created"""
    sertop_success: bool
    """
    True if this code segment successfully runs under sertop; False
    if this code segment fails to run under sertop
    """
    project_metadata: ProjectMetadata
    """
    Metadata associated with the project this cache object was
    extracted from
    """

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
            fmt: su.io.Fmt = su.io.Fmt.yaml) -> 'RepairMiningCache':
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
        RepairMiningCache
            Loaded repair mining cache
        """
        data = su.io.load(filepath, fmt)
        cache = su.io.deserialize(data, cls)
        return cache


class RepairMiningCacheStorage:
    """
    Object regulating access to repair mining cache on disk.

    On-disk structure:

    Root/
    ├── Project 1/
    |   ├── Commit hash 1/
    |   |   ├── cache file 1.yml
    |   |   ├── cache file 2.yml
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
    op_queue : Queue
        Multiprocessing queue for operations on on-disk cache
    status_pipe
    """

    def __init__(self, root: os.PathLike):
        """
        Instantiate object.

        Parameters
        ----------
        root : Path
            Root folder of repair mining cache structure
        """
        self.root = root
        if not Path(self.root).exists():
            os.makedirs(self.root)
        self.writer_queue: Queue = Queue()
        self.worker_process = Process(target=self._writer_worker)
        self.worker_process.start()

    def _check_existence(
            self,
            project: str,
            commit: str,
            cache_object: RepairMiningCache):
        filename = self._get_file_name(
            project,
            commit,
            cache_object.file_path,
            cache_object.identifier)
        if (Path(self.root) / project / commit / filename).exists():
            return True

    def _get_file_name(
            self,
            project: str,
            commit: str,
            file_path: str,
            identifier: str) -> str:
        m = hashlib.sha256()
        m.update(project.encode('utf-8'))
        m.update(commit.encode('utf-8'))
        m.update(file_path.encode('utf-8'))
        m.update(identifier.encode('utf-8'))
        return m.hexdigest()

    def _insert(
            self,
            project: str,
            commit: str,
            cache_object: RepairMiningCache):
        filename = self._get_file_name(
            project,
            commit,
            cache_object.file_path,
            cache_object.identifier)
        parent = Path(self.root) / project / commit
        if not parent.exists():
            os.makedirs(str(parent))
        fullpath = parent / filename
        cache_object.dump(fullpath)

    def _writer_worker(self):
        while True:
            try:
                obj = self.writer_queue.get_nowait()
            except queue.Empty:
                continue
            project, commit, cache_object = obj
            self._insert(project, commit, cache_object)

    def insert(
            self,
            project: str,
            commit: str,
            cache_object: RepairMiningCache):
        """
        Insert cache object into cache folder structure on disk.

        Parameters
        ----------
        project : str
            The name of the project
        commit : str
            The commit hash
        cache_object : RepairMiningCache
            The cache object to be inserted

        Raises
        ------
        RuntimeError
            If the cache file already exists. In this case, `update`
            should be called instead.
        """
        if self._check_existence(project, commit, cache_object):
            raise RuntimeError(
                "Cache file already exists. Call `update` instead.")
        else:
            self.writer_queue.put((project, commit, cache_object))

    def get(
            self,
            project: str,
            commit: str,
            file_path: str,
            identifier: str) -> RepairMiningCache:
        """
        Fetch a cache object from the on-disk folder structure.

        Parameters
        ----------
        project : str
            The name of the project
        commit : str
            The commit hash to fetch from
        file_path : str
            The original Coq file path for the cache to be fetched
        identifier : str
            The Coq object identifier to be fetched

        Returns
        -------
        RepairMiningCache
            The fetched cache object

        Raises
        ------
        ValueError
            If the specified cache object does not exist on disk
        """
        filename = self._get_file_name(project, commit, file_path, identifier)
        fullpath = Path(self.root) / project / commit / filename
        if not fullpath.exists():
            raise ValueError(f"No cache file exists at {fullpath}.")
        else:
            cache = RepairMiningCache.load(fullpath)
            return cache

    def update(
            self,
            project: str,
            commit: str,
            cache_object: RepairMiningCache):
        """
        Update an existing cache file on disk.

        Parameters
        ----------
        project : str
            The name of the project
        commit : str
            The commit hash to be updated
        cache_object : RepairMiningCache
            The cache object to be updated

        Raises
        ------
        RuntimeError
            If the cache file does not exist, `insert` should be called
            instead
        """
        if not self._check_existence(project, commit, cache_object):
            raise RuntimeError(
                "Cache file does not exist. Call `insert` instead.")
        else:
            self.writer_queue.put((project, commit, cache_object))
