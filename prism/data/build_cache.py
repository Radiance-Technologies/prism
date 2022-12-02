"""
Tools for handling repair mining cache.
"""
import glob
import os
import re
import subprocess
import tempfile
import warnings
from dataclasses import dataclass, field, fields
from multiprocessing.managers import BaseManager
from pathlib import Path
from typing import (
    Any,
    ClassVar,
    Dict,
    Iterable,
    List,
    Optional,
    Protocol,
    Set,
    Tuple,
    Union,
    runtime_checkable,
)

import networkx as nx
import setuptools_scm
import seutil as su

from prism.language.gallina.analyze import SexpInfo
from prism.language.sexp.node import SexpNode
from prism.project.metadata import ProjectMetadata
from prism.util.opam.switch import OpamSwitch
from prism.util.opam.version import Version, VersionString
from prism.util.radpytools.dataclasses import default_field
from prism.util.serialize import Serializable

from ..interface.coq.goals import Goals, GoalsDiff

CommandType = str


@dataclass
class VernacSentence:
    """
    A parsed sentence from a document.
    """

    text: str
    """
    Text of a sentence from a proof.
    """
    ast: str
    """
    The serialized AST derived from this sentence.

    Note that locations within this AST are not accurate with respect to
    the source document.
    """
    location: SexpInfo.Loc
    """
    The location of this sentence within the source document.
    """
    command_type: CommandType
    """
    The Vernacular type of command, e.g., VernacInductive.
    """
    goals: Optional[Union[Goals, GoalsDiff]] = None
    """
    Open goals, if any, prior to the execution of this sentence.

    This is especially useful for capturing the context of commands
    nested within proofs.
    """

    def __post_init__(self) -> None:
        """
        Ensure the AST is serialized.
        """
        if isinstance(self.ast, SexpNode):
            self.ast = str(self.ast)

    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> 'VernacSentence':
        """
        Deserialize the `VernacSentence` from a dictionary.

        Parameters
        ----------
        data : Dict[str, Any]
            The serialized storage as yielded from `su.io.serialize`.

        Returns
        -------
        VernacSentence
            The deserialized sentence.
        """
        field_values = {}
        for f in fields(cls):
            if f.name in data:
                value = data[f.name]
                if f.name == "goals":
                    if "added_goals" in data:
                        tp = GoalsDiff
                    else:
                        tp = Goals
                else:
                    tp = f.type
                value = su.io.deserialize(value, tp)
                field_values[f.name] = value
        return cls(**field_values)

    @staticmethod
    def sort_sentences(sentences: List['VernacSentence']) -> List[str]:
        """
        Sort the given sentences by their location.

        Parameters
        ----------
        located_sentences : List[VernacSentence]
            A list of sentences presumed to come from the same document.


        Returns
        -------
        List[str]
            The sentences sorted by their location in the document in
            ascending order.

        Notes
        -----
        Sorting is done purely based on character numbers, so sentences
        from different documents can still be sorted together (although
        the significance of the results may be suspect).
        """
        return [s for _, s in sorted([(s.location, s) for s in sentences])]


@dataclass
class ProofSentence(VernacSentence):
    """
    Type associating individual proof sentences to ASTs and open goals.
    """

    pass


Proof = List[ProofSentence]


@dataclass
class VernacCommandData:
    """
    The evaluated result for a single Vernacular command.
    """

    identifier: List[str]
    """
    Identifier(s) for the command being cached, e.g., the name of the
    corresponding theorem, lemma, or definition.
    If no identifier exists (for example, if it is an import statement)
    or can be meaningfully defined, then an empty list.
    """
    command_error: Optional[str]
    """
    The error, if any, that results when trying to execute the command
    (e.g., within ``sertop``). If there is no error, then None.
    """
    command: VernacSentence
    """
    The Vernacular command.
    """
    proofs: List[Proof] = default_field(list())
    """
    Associated proofs, if any.
    Proofs are considered to be a list of proof blocks, each dealing
    with a separate obligation of the conjecture stated in `command`.
    Tactics and goals are captured here.
    """

    def __hash__(self) -> int:  # noqa: D105
        # do not include the error
        return hash((self.identifier, self.command_type, self.location))

    @property
    def command_type(self) -> str:
        """
        Get the type of the Vernacular command.
        """
        return self.command.command_type

    @property
    def location(self) -> SexpInfo.Loc:
        """
        Get the location of the command in the original source document.
        """
        return self.command.location

    def sorted_sentences(self) -> List[VernacSentence]:
        """
        Get the sentences in this command sorted by their locations.

        A command may possess multiple sentences if it has any
        associated proofs.
        """
        sentences = [self.command]
        for proof in self.proofs:
            for sentence in proof:
                sentences.append(sentence)
        if len(sentences) > 1:
            return VernacSentence.sort_sentences(sentences)
        else:
            return sentences


VernacDict = Dict[str, List[VernacCommandData]]


@dataclass
class ProjectBuildResult:
    """
    The result of building a project commit.

    The project environment and metadata are implicit.
    """

    exit_code: int
    """
    The exit code of the project's build command with
    implicit project metadata.
    """
    stdout: str
    """
    The standard output of the commit's build command with
    implicit project metadata.
    """
    stderr: str
    """
    The standard error of the commit's build command with
    implicit project metadata.
    """


@dataclass
class ProjectBuildEnvironment:
    """
    The environment in which a project's commit data was captured.
    """

    switch_config: OpamSwitch.Configuration
    """
    The configuration of the switch in which the commit's build command
    was invoked.
    """
    current_version: str = field(init=False)
    """
    The current version of this package.
    """
    SHA_regex: ClassVar[re.Pattern] = re.compile(r"\+g[0-9a-f]{5,40}")
    """
    A regular expression that matches Git commit SHAs.
    """
    describe_cmd: ClassVar[
        List[str]] = 'git describe --match="" --always --abbrev=40'.split()
    """
    A command that can retrieve the hash of the checked out commit.

    Note that this will fail if the package is installed.
    """

    def __post_init__(self):
        """
        Cache the commit of the coq-pearls repository.
        """
        self.current_version = setuptools_scm.get_version()
        match = self.SHA_regex.search(self.current_version)
        self.switch_config = self.switch_config
        if match is not None:
            # replace abbreviated hash with full hash to guarantee
            # the hash remains unambiguous in the future
            try:
                current_commit = subprocess.check_output(
                    self.describe_cmd).strip().decode("utf-8")
                self.current_version = ''.join(
                    [
                        self.current_version[: match.start()],
                        current_commit,
                        self.current_version[match.end():]
                    ])
            except subprocess.CalledProcessError:
                warnings.warn(
                    "Unable to expand Git hash in version string. "
                    "Try installing `coq-pearls` in editable mode.")


@dataclass
class ProjectCommitData(Serializable):
    """
    Data associated with a project commit.

    The data is expected to be precomputed and cached to assist with
    subsequent repair mining.
    """

    project_metadata: ProjectMetadata
    """
    Metadata that identifies the project name, commit, Coq version, and
    other relevant data for reproduction and of the cache.
    """
    command_data: VernacDict
    """
    A map from file names relative to the root of the project to the set
    of command results.
    Iterating over the map's keys should follow dependency order of the
    files, i.e., if file ``B`` depends on file ``A``, then ``A`` will
    appear in the iteration before ``B``.
    """
    file_dependencies: Optional[Dict[str, List[str]]] = None
    """
    An adjacency list containing the intraproject dependencies of each
    file listed in `command_data`.
    If file ``B`` depends on file ``A``, then ``A`` will appear in
    ``file_dependencies[B]``.
    """
    environment: Optional[ProjectBuildEnvironment] = None
    """
    The environment in which the commit was processed.
    """
    build_result: Optional[ProjectBuildResult] = None
    """
    The result of building the project commit in the `opam_switch` or
    None if building was not required to process the commit.
    """

    @property
    def files(self) -> List[str]:
        """
        Return the list of Coq files in the project.

        If `file_dependencies` is set, then the files will be listed in
        dependency order. Otherwise, they will match the order of
        iteration of `command_data`.
        """
        if self.file_dependencies is not None:
            G = nx.DiGraph()
            for f, deps in self.file_dependencies:
                for dep in deps:
                    G.add_edge(f, dep)
            files = list(reversed(nx.topological_sort(G)))
        else:
            files = [k for k in self.command_data.keys()]
        return files


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
    status: str
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
    |   |   ├── cache_file_1.yml
    |   |   ├── cache_file_2.yml
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
    _default_coq_versions: Set[str] = {
        '8_9_1',
        '8_10_2',
        '8_11_2',
        '8_12_2',
        '8_13_2',
        '8_14_1',
        '8_15_2'
    }
    """
    Default coq versions to look for when getting cache status.
    """

    def __contains__(  # noqa: D105
            self,
            obj: Union[ProjectCommitData,
                       ProjectMetadata,
                       Tuple[str]]) -> bool:
        return self.contains(obj)

    @property
    def fmt(self) -> su.io.Fmt:
        """
        Get the serialization format with which to cache data.
        """
        return su.io.infer_fmt_from_ext(self.fmt_ext)

    def _contains_data(self, data: ProjectCommitData) -> bool:
        return self.get_path_from_data(data).exists()

    def _contains_fields(self, *fields: Tuple[str]) -> bool:
        return self.get_path_from_fields(*fields).exists()

    def _contains_metadata(self, metadata: ProjectMetadata) -> bool:
        return self.get_path_from_metadata(metadata).exists()

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

        Raises
        ------
        TypeError
            If `file_contents` is not a string or `Serializable`.
        """
        if not isinstance(file_contents, (str, Serializable)):
            raise TypeError(
                f"Cannot write object of type {type(file_contents)} to file")
        # standardize inputs to get_path
        if not isinstance(cache_id, tuple):
            cache_id = (cache_id,)
        data_path = self.get_path(*cache_id)
        cache_dir = data_path.parent
        if not cache_dir.exists():
            os.makedirs(str(cache_dir))
        # Ensure that we write atomically.
        # First, we write to a temporary file so that if we get
        # interrupted, we aren't left with a corrupted file.
        if suffix is None and isinstance(file_contents, Serializable):
            suffix = f".{self.fmt_ext}"
        data_path: Path = data_path.parent / (data_path.stem + suffix)
        with tempfile.NamedTemporaryFile("w",
                                         delete=False,
                                         dir=self.root,
                                         encoding='utf-8') as f:
            if isinstance(file_contents, str):
                f.write(file_contents)
        if isinstance(file_contents, Serializable):
            file_contents.dump(f.name, self.fmt)
        # Then, we atomically move the file to the correct, final
        # path.
        os.replace(f.name, data_path)
        if block:
            return "write complete"

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
            coq_versions = self._default_coq_versions
        else:
            coq_versions = [str(v).replace(".", "_") for v in coq_versions]
        coq_versions: Iterable[str]
        status_list = []
        for project in projects:
            for commit in commits[project]:
                folder: Path = (self.root / project) / commit
                for coq_version in coq_versions:
                    if (folder / (coq_version + "_cache_error.txt")).exists():
                        status_msg = "cache error"
                    elif (folder / (coq_version + "_build_error.txt")).exists():
                        status_msg = "build error"
                    elif (folder / (coq_version + "_misc_error.txt")).exists():
                        status_msg = "other error"
                    elif (folder / (coq_version + "." + self.fmt_ext)).exists():
                        status_msg = "success"
                    else:
                        status_msg = None
                    if status_msg is not None:
                        status_list.append(
                            CacheObjectStatus(
                                project,
                                commit,
                                coq_version,
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
                lambda x: x.status != "success",
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
                lambda x: x.status == "success",
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
        self._write_kernel(data, block, data)
        # If there was an error in cache extraction, write an additional
        # text file containing the output.
        if data.build_result.exit_code != 0:
            str_to_write = "\n".join(
                [
                    f"@@Exit code@@\n{data.build_result.exit_code}",
                    f"@@stdout@@\n{data.build_result.stdout}",
                    f"@@stderr@@\n{data.build_result.stderr}"
                ])
            self._write_kernel(data, block, str_to_write, "_build_error.txt")
        if block:
            return "write complete"

    def write_error_log(
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
        return self._write_kernel(
            metadata,
            block,
            cache_error_log,
            "_cache_error.txt")

    def write_misc_log(
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
        return self._write_kernel(metadata, block, misc_log, "_misc_error.txt")

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


class CoqProjectBuildCache(CoqProjectBuildCacheProtocol):
    """
    Implementation of CoqProjectBuildCacheProtocol with added __init__.
    """

    def __init__(self, root: Path, fmt_ext: str = "yml"):
        self.root = Path(root)
        self.fmt_ext = fmt_ext
        if not self.root.exists():
            os.makedirs(self.root)


class CoqProjectBuildCacheServer(BaseManager):
    """
    A BaseManager-derived server for managing build cache.
    """


CoqProjectBuildCacheServer.register(
    "CoqProjectBuildCache",
    CoqProjectBuildCache)


def CoqProjectBuildCacheClient(
        server: CoqProjectBuildCacheServer,
        *args,
        **kwargs):
    """
    Return client object for writing build cache.
    """
    return server.CoqProjectBuildCache(*args, **kwargs)
