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
from multiprocessing.managers import SyncManager
from pathlib import Path
from typing import Any, ClassVar, Dict, Iterable, List, Optional, Tuple, Union

import setuptools_scm
import seutil as su

from prism.language.gallina.analyze import SexpInfo
from prism.language.sexp.node import SexpNode
from prism.project.metadata import ProjectMetadata
from prism.util.opam.switch import OpamSwitch
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
    environment: ProjectBuildEnvironment
    """
    The environment in which the commit was processed.
    """
    build_result: Optional[ProjectBuildResult] = None
    """
    The result of building the project commit in the `opam_switch` or
    None if building was not required to process the commit.
    """


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

    def write(self, data: ProjectCommitData, block: bool = False) -> None:
        """
        Cache the data to disk regardless of whether it already exists.

        Parameters
        ----------
        data : ProjectCommitData
            The object to be cached.
        block : bool, optional
            Whether to wait for the write operation to complete, by
            default False.

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

    def write_error_log(
            self,
            metadata: ProjectMetadata,
            block: bool = False,
            cache_error_log: str = "") -> None:
        """
        Write a caching error log to disk.

        Parameters
        ----------
        metadata : ProjectMetadata
            The project metadata for the project that had an error.
        block : bool, optional
            Whether to wait for the write operation to complete, by
            default False.
        cache_error_log : str
            Caching error log to write to file.

        Raises
        ------
        ValueError
            If response from server has unexpected contents
        """
        msg = BuildCacheMsg(
            self.client_id,
            "write_error_log",
            args=(metadata,
                  block,
                  cache_error_log))
        self.client_to_server.put(msg)
        if block:
            response: BuildCacheMsg = self.server_to_client.get()
            if response.response != "write complete":
                raise ValueError(f"Unexpected response {response.response}.")

    def write_timing_log(
            self,
            metadata: ProjectMetadata,
            block: bool = False,
            timing_log: str = "") -> None:
        """
        Write a timing log file.

        Parameters
        ----------
        metadata : ProjectMetadata
            The project metadata for the project that had an error.
        block : bool, optional
            Whether to wait for the write operation to complete, by
            default False.
        timing_log : str
            Timing log to write to file.

        Raises
        ------
        ValueError
            If response from server has unexpected contents
        """
        msg = BuildCacheMsg(
            self.client_id,
            "write_timing_log",
            args=(metadata,
                  block,
                  timing_log))
        self.client_to_server.put(msg)
        if block:
            response: BuildCacheMsg = self.server_to_client.get()
            if response.response != "write complete":
                raise ValueError(f"Unexpected response {response.response}.")

    # Aliases
    insert = write
    update = write


def create_cpbcs_qs(manager: SyncManager,
                    client_keys: List[str]) -> Tuple[Queue,
                                                     Dict[str,
                                                          Queue]]:
    """
    Create queues for CoqProjectBuildCacheServer objects.

    Parameters
    ----------
    manager : SyncManager
        A sync manager that supplies queues that can be shared among
        non-inherited processes
    client_keys : List[str]
        A list of client keys for the cache server
    """
    client_to_server_q = manager.Queue()
    server_to_client_q_dict = {k: manager.Queue() for k in client_keys}
    return client_to_server_q, server_to_client_q_dict


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
            client_keys: Optional[List[str]] = None,
            client_to_server_q: Optional[Queue] = None,
            server_to_client_q_dict: Optional[Dict[str,
                                                   Queue]] = None,
            fmt_ext: str = "yml"):
        self.root = Path(root)
        """
        Root folder of repair mining cache structure
        """
        self.fmt_ext = fmt_ext
        """
        The extension for the cache files that defines their format.
        """
        self.client_keys = client_keys if client_keys else []
        """
        Keys corresponding to each client. If these keys are not
        provided, the server loop process does not start, and it is
        expected that this object will be used by a single producer OR
        in a read-only context.
        """
        self.client_to_server = client_to_server_q
        """
        Queue for clients to send cache messages to write to this object
        acting as a cache-writing server.
        """
        self.server_to_client_dict = server_to_client_q_dict
        """
        Dictionary of queues for sending messages from server to client
        """
        self._worker_proc: Process = Process(target=self._server_loop)
        """
        Consumer process that writes to disk from queue.
        """
        self._dispatch_table = {
            "write": self._write,
            "write_error_log": self._write_error_log,
            "write_timing_log": self._write_timing_log,
            "contains": self.contains,
            "get": self.get
        }
        """
        Dictionary mapping incoming function calls from the
        client-to-server queue.
        """
        if client_keys and (self.client_to_server is None
                            or self.server_to_client_dict is None):
            raise RuntimeError(
                "If client keys are provided, queues must be provided as well.")

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
        if self.client_keys:
            self._worker_proc.start()
        return self

    def __exit__(self, _exc_type, _exc_value, _exc_traceback):
        """
        Stop the worker process.
        """
        if self.client_keys:
            # Send poison pill
            try:
                self.client_to_server.put(BuildCacheMsg(None, "poison pill"))
            except AttributeError:
                # We shouldn't ever get here, but just in case...
                self._worker_proc.kill()
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

    def _contains_fields(self, *fields: Tuple[str]) -> bool:
        return self.get_path_from_fields(*fields).exists()

    def _contains_metadata(self, metadata: ProjectMetadata) -> bool:
        return self.get_path_from_metadata(metadata).exists()

    def _server_loop(self) -> None:
        """
        Provide consumer loop for build cache server.
        """
        while True:
            msg: BuildCacheMsg = self.client_to_server.get()
            try:
                response = self._dispatch_table[msg.type](*msg.args)
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
            If true, return a ``"write complete"`` message.

        Returns
        -------
        str or None
            If `block`, return ``"write complete"``; otherwise, return
            nothing
        """
        self._write_kernel(data, False, data)
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

    def _write_error_log(
            self,
            metadata: ProjectMetadata,
            block: bool,
            cache_error_log: str) -> Optional[str]:
        """
        Write caching error log to build cache directory.

        This is a private function. Invoking it outside of the
        client -> queue -> server route will result in undefined
        behavior.

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

    def _write_timing_log(
            self,
            metadata: ProjectMetadata,
            block: bool,
            timing_log: str) -> Optional[str]:
        """
        Write timing log to build cache directory.

        This is a private function. Invoking it outside of the
        client -> queue -> server route will result in undefined
        behavior.

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

    def write(self, data: ProjectCommitData, block: bool = True) -> None:
        """
        Cache the data to disk regardless of whether it already exists.

        This method cannot be safely used in a multi-producer
        context. It is meant for use in a single-producer context to
        remove the need for a `CoqProjectBuildCacheClient` object.

        Parameters
        ----------
        data : ProjectCommitData
            The object to be cached.
        block : bool, optional
            Whether to wait for the write operation to complete.
            This argument currently has no effect; the method always
            blocks.
            The argument is allowed to maintain a uniform signature
            with `CoqProjectBuildCacheClient.write`.

        Raises
        ------
        RuntimeError
            If clients can potentially send data to the server,
            indicating that using this method is not guaranteed to be
            safe.
        """
        if self.client_keys:
            raise RuntimeError(
                "It is not safe to use the `write`"
                " method when clients are connected to the server.")
        else:
            self._write(data, block)

    def write_error_log(
            self,
            metadata: ProjectMetadata,
            block: bool,
            cache_error_log: str) -> Optional[str]:
        """
        Write caching error log to build cache directory.

        This method cannot be safely used in a multi-producer
        context. It is meant for use in a single-producer context to
        remove the need for a `CoqProjectBuildCacheClient` object.

        Parameters
        ----------
        metadata : ProjectCommitData
            Metadata for the project that had a caching error. Used by
            this method to get the correct path to write to.
        block : bool
            Whether to wait for the operation to complete.
        cache_error_log : str
            Caching error log string to write to file.

        Returns
        -------
        str or None
            If `block`, return "write complete"; otherwise, return
            nothing
        """
        if self.client_keys:
            raise RuntimeError(
                "It is not safe to use the `write_error_log`"
                " method when clients are connected to the server.")
        else:
            self._write_error_log(metadata, block, cache_error_log)

    def write_timing_log(
            self,
            metadata: ProjectMetadata,
            block: bool,
            timing_log: str) -> Optional[str]:
        """
        Write timing log to build cache directory.

        This method cannot be safely used in a multi-producer
        context. It is meant for use in a single-producer context to
        remove the need for a `CoqProjectBuildCacheClient` object.

        Parameters
        ----------
        metadata : ProjectCommitData
            Metadata for the project that had a caching error. Used by
            this method to get the correct path to write to.
        block : bool
            Whether to wait for the operation to complete.
        timing_log : str
            Timing log string to write to file.

        Returns
        -------
        str or None
            If `block`, return "write complete"; otherwise, return
            nothing
        """
        if self.client_keys:
            raise RuntimeError(
                "It is not safe to use the `write_timing_log`"
                " method when clients are connected to the server.")
        else:
            self._write_timing_log(metadata, block, timing_log)

    insert = write
    apply = write
