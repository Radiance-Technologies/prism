"""
Tools for handling repair mining cache.
"""
import os
import re
import subprocess
import tempfile
import warnings
from dataclasses import dataclass, field
from multiprocessing import Process, Queue
from pathlib import Path
from typing import Any, ClassVar, Dict, Iterable, List, Optional, Tuple, Union

import setuptools_scm
import seutil as su

from prism.language.gallina.analyze import SexpInfo
from prism.project.metadata import ProjectMetadata
from prism.util.opam.switch import OpamSwitch
from prism.util.radpytools.dataclasses import default_field

from ..interface.coq.goals import Goals
from ..interface.coq.serapi import AbstractSyntaxTree


@dataclass
class ProofSentence:
    """
    Type associating individual proof sentences to ASTs and open goals.
    """

    sentence: str
    """
    Text of a sentence from a proof.
    """
    ast: AbstractSyntaxTree
    """
    The AST derived from the proof sentence.
    """
    goals: Optional[Goals] = None
    """
    Open goals, if any, associated with this proof sentence.
    """


Proof = List[ProofSentence]


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
    command_error: Optional[str]
    """
    The error, if any, that results when trying to execute the command
    (e.g., within the ``sertop``). If there is no error, then None.
    """
    sentence: str
    """
    The whitespace-normalized sentence text.
    """
    sexp: AbstractSyntaxTree
    """
    The serialized s-expression of this sentence.
    """
    location: SexpInfo.Loc
    """
    The location of this vernacular command.
    """
    proofs: List[Proof] = default_field(list())
    """
    Associated proofs, if any. Proofs are considered to be a list of
    strings. Each contained `ProofSentence` object contains a proof
    sentence, a proof sentence AST, and any open goals associated with
    the proof.
    """

    def __hash__(self) -> int:  # noqa: D105
        # do not include the error
        return hash((self.identifier, self.command_type, self.location))


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
class ProjectCommitData:
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
    """
    environment: ProjectBuildEnvironment
    """
    The environment in which the commit was processed.
    """
    build_result: Optional[ProjectBuildResult] = None
    """
    The result of building the project commit in the `opam_switch` or
    None if building was not required to process the commit.
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
class BuildCacheMsg:
    """
    Data class for messages passed between cache server and client.
    """

    client_id: str
    """
    Identifier for client object
    """
    type: str
    """
    The type of this message. If the message is meant to invoke a
    function, this should match a key in the receiving object's
    dispatch table.
    """
    args: tuple = field(default_factory=tuple)
    """
    Arbitrary tuple of args to be passed to a function on the receiving
    end
    """
    response: Any = None
    """
    Response, if any, from any functions that were previously called
    """


class CoqProjectBuildCacheClient:
    """
    Client object for writing build cache.
    """

    def __init__(
            self,
            client_to_server: Queue,
            server_to_client: Queue,
            client_id: str):
        self.client_to_server = client_to_server
        """
        This queue is used to send messages and commands from the client
        to the server. This queue is shared among all clients.
        """
        self.server_to_client = server_to_client
        """
        This queue is used to receive messages from the server. Each
        client instance has a unique instance of this queue.
        """
        self.client_id = client_id
        """
        Identifier for client object.
        """

    def __contains__(  # noqa: D105
            self,
            obj: Union[ProjectCommitData,
                       ProjectMetadata,
                       Tuple[str]]) -> bool:
        msg = BuildCacheMsg(self.client_id, "contains", args=(obj,))
        self.client_to_server.put(msg)
        response: BuildCacheMsg = self.server_to_client.get()
        if not isinstance(response.response, bool):
            raise TypeError(f"Unexpected response {response.response}")
        return response.response

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
        TypeError
            If response from the server is not of the expected type
        """
        msg = BuildCacheMsg(
            self.client_id,
            "get",
            args=(project,
                  commit,
                  coq_version))
        self.client_to_server.put(msg)
        response: BuildCacheMsg = self.server_to_client.get()
        if not isinstance(response.response, ProjectCommitData):
            raise TypeError(f"Unexpected response {response.response}")
        return response.response

    def write(self, data: ProjectMetadata, block: bool = True) -> None:
        """
        Cache the data to disk regardless of whether it already exists.

        Parameters
        ----------
        data : ProjectMetadata
            The object to be cached.

        Raises
        ------
        ValueError
            If response from server has unexpected contents
        """
        msg = BuildCacheMsg(self.client_id, "write", args=(data, block))
        self.client_to_server.put(msg)
        if block:
            response: BuildCacheMsg = self.server_to_client.get()
            if response.response != "write complete":
                raise ValueError(f"Unexpected response {response.response}.")

    # Aliases
    insert = write
    update = write


class CoqProjectBuildCacheServer:
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

    def __init__(
            self,
            root: Path,
            client_keys: List[str],
            fmt_ext: str = "yml"):
        self.root = Path(root)
        """
        Root folder of repair mining cache structure
        """
        self.fmt_ext = fmt_ext
        """
        The extension for the cache files that defines their format.
        """
        self.client_keys = client_keys
        """
        Keys corresponding to each client.
        """
        self.client_to_server = Queue()
        """
        Queue for clients to send cache messages to write to this object
        acting as a cache-writing server.
        """
        self.server_to_client_dict = {k: Queue() for k in self.client_keys}
        """
        Dictionary of queues for sending messages from server to client
        """
        self._worker_proc: Process = Process(target=self._server_loop)
        """
        Consumer process that writes to disk from queue.
        """
        self.dispatch_table = {
            "write": self._write,
            "contains": self.contains,
            "get": self.get
        }
        """
        Dictionary mapping incoming function calls from the
        client-to-server queue.
        """

    def __contains__(  # noqa: D105
            self,
            obj: Union[ProjectCommitData,
                       ProjectMetadata,
                       Tuple[str]]) -> bool:
        return self.contains(obj)

    def __enter__(self):
        """
        Enter the context manager.
        """
        if not self.root.exists():
            os.makedirs(self.root)
        self._worker_proc.start()
        return self

    def __exit__(self, _exc_type, _exc_value, _exc_traceback):
        """
        Stop the worker process.
        """
        # Send poison pill
        self.client_to_server.put(BuildCacheMsg(None, "poison pill"))
        # Allow any remaining writes to complete
        # Note: if this ends up being buggy, maybe try setting a
        # timeout for join and then calling self._worker_proc.kill()
        # after timeout.
        self._worker_proc.join()
        # Termination has already happened at this point, so we
        # don't need to do it manually.

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

    def _write(self, data: ProjectCommitData, block: bool) -> Optional[str]:
        """
        Write to build cache.

        This is a private function. Invoking it outside of the
        client -> queue -> server route will result in undefined
        behavior.

        Parameters
        ----------
        data : ProjectCommitData
            Data to write to build cache
        block : bool
            If true, return a "write complete" message

        Returns
        -------
        str or None
            If `block`, return "write complete"; otherwise, return
            nothing
        """
        data_path = self.get_path_from_data(data)
        cache_dir = data_path.parent
        if not cache_dir.exists():
            os.makedirs(str(cache_dir))
        # Ensure that we write the cache atomically.
        # First, we write to a temporary file so that if we get
        # interrupted, we aren't left with a corrupted cache.
        with tempfile.NamedTemporaryFile("w", delete=False, dir=self.root) as f:
            pass
        data.dump(f.name, su.io.infer_fmt_from_ext(self.fmt_ext))
        # Then, we atomically move the file to the correct, final
        # path.
        os.replace(f.name, data_path)
        if block:
            return "write complete"

    def _server_loop(self) -> None:
        """
        Provide consumer loop for build cache server.
        """
        while True:
            msg: BuildCacheMsg = self.client_to_server.get()
            try:
                response = self.dispatch_table[msg.type](*msg.args)
            except (KeyError, AttributeError):
                if msg.type == "poison pill":
                    # Break the infinite loop if we get the poison pill
                    break
                else:
                    raise
            else:
                response_msg = BuildCacheMsg(
                    msg.client_id,
                    "response",
                    response=response)
                # Don't put a response in the queue if the client called
                # "write" with block=False.
                if msg.type != "write" or (msg.type == "write" and msg.args[1]):
                    self.server_to_client_dict[msg.client_id].put(response_msg)
