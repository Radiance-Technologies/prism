"""
Tools for handling repair mining cache.
"""
import os
import tempfile
from dataclasses import InitVar, dataclass, field
from multiprocessing.pool import Pool
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple, Union

import seutil as su

from prism.language.gallina.analyze import SexpInfo
from prism.language.sexp.node import SexpNode
from prism.project.metadata import ProjectMetadata
from prism.util.radpytools.dataclasses import default_field

from ..interface.coq.goals import Goals

ProofSentence = str
Proof = List[ProofSentence]


@dataclass
class ProofSentenceGoals:
    """
    Type associating proof sentences to open goals.
    """

    sentence: ProofSentence
    """
    A sentence from a proof.
    """
    goals: Optional[Goals] = None
    """
    Open goals, if any, associated with this proof sentence.
    """


ProofGoals = List[ProofSentenceGoals]


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
    sentence_text: str
    """
    The raw sentence text.
    """
    sexp: SexpNode
    """
    The serialized s-expression.
    """
    proofs: List[Proof] = default_field(list())
    """
    Associated proofs, if any. Proofs are considered to be a list of
    strings.
    """
    proof_goals: List[ProofGoals] = default_field(list())
    """
    A list of open goals per proof. Each index in this list corresponds
    to an index in `proofs`. Each item in the `proof_goals` list is a
    list of `ProofSentenceGoals` objects. Each of these objects maps a
    proof sentence to the proof goal context associated with it.
    """

    def __hash__(self) -> int:  # noqa: D105
        # do not include the error
        return hash((self.identifier, self.command_type, self.location))


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
    command_data: Dict[str, Set[VernacCommandData]]
    """
    A map from file names relative to the root of the project to the set
    of command results.
    """

    def dump(
            self,
            output_filepath: os.PathLike,
            fmt: su.io.Fmt = su.io.Fmt.yaml) -> None:
        """
        Serialize data to text file.

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
            fmt: Optional[su.io.Fmt] = None) -> 'ProjectCommitData':
        """
        Load repair mining cache from file.

        Parameters
        ----------
        filepath : os.PathLike
            Filepath containing repair mining cache.
        fmt : Optional[su.io.Fmt], optional
            Designated format of the input file, by default None.
            If None, then the format is inferred from the extension.

        Returns
        -------
        ProjectCommitData
            Loaded repair mining cache
        """
        return su.io.load(filepath, fmt, clz=cls)


@dataclass
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
    """

    root: Path
    """
    Root folder of repair mining cache structure
    """
    fmt_ext: str = "yml"
    """
    The extension for the cache files that defines their format.
    """
    num_workers: InitVar[int] = 1
    """
    The number of workers available for asynchronously writing cache
    files.
    """
    _worker_pool: Pool = field(init=False)
    """
    Multiprocessing pool for writing cache files to disk on demand.
    """

    def __post_init__(self, num_workers: int):
        """
        Instantiate object.
        """
        self.root = Path(self.root)
        if not self.root.exists():
            os.makedirs(self.root)
        self._worker_pool = Pool(processes=num_workers)

    def __contains__(  # noqa: D105
            self,
            obj: Union[ProjectCommitData,
                       ProjectMetadata,
                       Tuple[str]]) -> bool:
        return self.contains(obj)

    def __del__(self) -> None:  # noqa: D105
        # close the multiprocessing pool
        self._worker_pool.close()
        self._worker_pool.terminate()

    @property
    def fmt(self) -> su.io.Fmt:
        """
        Get the serialization format with which to cache data.
        """
        return su.io.infer_fmt_from_ext(self.fmt_ext)

    def _contains_data(self, data: ProjectCommitData) -> bool:
        return self.get_path_from_data(data).exists()

    def _contains_metadata(self, metadata: ProjectMetadata) -> bool:
        return self.get_path_from_metadata(metadata).exists()

    def _contains_fields(self, *fields: Tuple[str]) -> bool:
        return self.get_path_from_fields(*fields).exists()

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
            coq_version: str) -> Path:
        """
        Get the file path for identifying fields of a cache.
        """
        return self.root / project / commit / '.'.join(
            [coq_version.replace(".",
                                 "_"),
             self.fmt_ext])

    def get_path_from_metadata(self, metadata: ProjectMetadata) -> Path:
        """
        Get the file path for a given metadata.
        """
        return self.get_path_from_fields(
            metadata.project_name,
            metadata.commit_sha,
            metadata.coq_version)

    def insert(self, data: ProjectCommitData, block: bool = True) -> None:
        """
        Cache a new element of data on disk.

        Parameters
        ----------
        data : ProjectCommitData
            The data to be cached.
        block : bool, optional
            Whether to wait for the operation to complete or not, by
            default True.

        Raises
        ------
        RuntimeError
            If the cache file already exists. In this case, `update`
            should be called instead.
        """
        if data in self:
            raise RuntimeError(
                "Cache file already exists. Call `update` instead.")
        else:
            self.write(data, block)

    def update(self, data: ProjectCommitData, block: bool = True) -> None:
        """
        Update an existing cache file on disk.

        Parameters
        ----------
        data : ProjectCommitData
            The object to be re-cached.
        block : bool, optional
            Whether to wait for the operation to complete or not, by
            default True.

        Raises
        ------
        RuntimeError
            If the cache file does not exist, `insert` should be called
            instead
        """
        if data not in self:
            raise RuntimeError(
                "Cache file does not exist. Call `insert` instead.")
        else:
            self.write(data, block)

    def write(self, data: ProjectMetadata, block: bool = False) -> None:
        """
        Cache the data to disk regardless of whether it already exists.

        Parameters
        ----------
        data : ProjectMetadata
            The object to be cached.
        """
        kwargs = {
            'data_path': self.get_path_from_data(data),
            'data': data,
            'tmpdir': self.root,
            'ext': self.fmt_ext
        }
        if block:
            self._worker_pool.apply(self._write, kwds=kwargs)
        else:
            self._worker_pool.apply_async(self._write, kwds=kwargs)

    @staticmethod
    def _write(
            data: ProjectCommitData,
            data_path: Path,
            tmpdir: str,
            ext: str) -> None:
        """
        Write the project commit's data to disk.

        This should not in normal circumstances be called directly.

        Parameters
        ----------
        data : ProjectCommitData
            The data to be written to disk.
        """
        cache_dir = data_path.parent
        if not cache_dir.exists():
            os.makedirs(str(cache_dir))
        # Ensure that we write the cache atomically.
        # First, we write to a temporary file so that if we get
        # interrupted, we aren't left with a corrupted cache.
        with tempfile.NamedTemporaryFile("w", delete=False, dir=tmpdir) as f:
            pass
        data.dump(f.name, su.io.infer_fmt_from_ext(ext))
        # Then, we atomically move the file to the correct, final path.
        os.replace(f.name, data_path)
