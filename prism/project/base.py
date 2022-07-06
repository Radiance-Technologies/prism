"""
Module providing CoqGym project class representations.
"""
import logging
import pathlib
import random
from abc import ABC, abstractmethod
from enum import Enum, auto
from functools import partialmethod
from typing import List, Optional, Tuple, Union

from seutil import BashUtils, bash

from prism.data.document import CoqDocument
from prism.language.heuristic.parser import HeuristicParser, SerAPIParser
from prism.project.exception import ProjectBuildError
from prism.project.metadata import ProjectMetadata
from prism.project.metadata.storage import MetadataStorage
from prism.project.strace import IQR, CoqContext, strace_build
from prism.util.logging import default_log_level
from prism.util.opam import OpamSwitch
from prism.util.opam.api import OpamAPI

logger: logging.Logger = logging.getLogger(__name__)
logger.setLevel(default_log_level())


class SentenceExtractionMethod(Enum):
    """
    Enum for available sentence extraction methods.

    Attributes
    ----------
    SERAPI
        Use serapi to extract sentences
    HEURISTIC
        Use custom heuristic method to extract sentences
    """

    SERAPI = auto()
    HEURISTIC = auto()

    def parser(self) -> Union[HeuristicParser, SerAPIParser]:
        """
        Return the appropriate parser for the SEM.
        """
        method_enum = SentenceExtractionMethod(self.value)
        if method_enum is SentenceExtractionMethod.SERAPI:
            return SerAPIParser
        elif method_enum is SentenceExtractionMethod.HEURISTIC:
            return HeuristicParser
        else:
            raise ValueError(
                f"Extraction method {method_enum} doesn't have specified parser"
            )


SEM = SentenceExtractionMethod


class Project(ABC):
    """
    Abstract base class for representing a Coq project.

    Parameters
    ----------
    dir_abspath : str
        The absolute path to the project's root directory.
    metadata_storage : MetadataStorage
        MetadataStorage for referencing all possible metadata
        configurations for the project.
    opam_switch : OpamSwitch
        Object for tracking OpamSwitch relevant for this project
    sentence_extraction_method : SentenceExtractionMethod
        The method by which sentences are extracted.

    Attributes
    ----------
    dir_abspath : str
        The absolute path to the project's root directory.
    metadata: ProjectMetadata
        Project metadata containing information such as project name
        and commands.
    size_bytes : int
        The total space on disk occupied by the files in the dir in
        bytes
    sentence_extraction_method : SentenceExtractionMethod
        The method by which sentences are extracted.
    """

    def __init__(
            self,
            dir_abspath: str,
            metadata_storage: MetadataStorage,
            opam_switch: Optional[OpamSwitch] = None,
            sentence_extraction_method: SEM = SentenceExtractionMethod.SERAPI,
            num_cores: Optional[int] = None):
        """
        Initialize Project object.
        """
        self.dir_abspath = dir_abspath
        self.metadata_storage = metadata_storage
        self.size_bytes = self._get_size_bytes()
        self.sentence_extraction_method = sentence_extraction_method
        if opam_switch is not None:
            self.opam_switch = opam_switch
        else:
            self.opam_switch = OpamSwitch()
        self.num_cores = num_cores

    @property
    def build_cmd(self) -> List[str]:
        """
        Return the list of commands that build the project.
        """
        cmd_list = self.metadata.build_cmd
        for i in range(len(cmd_list)):
            if 'make' in cmd_list[i] and self.num_cores is not None:
                cmd_list[i] = cmd_list[i] + " -j{0}".format(self.num_cores)
        return cmd_list

    @property
    def clean_cmd(self) -> List[str]:
        """
        Return the list of commands that clean project build artifacts.
        """
        return self.metadata.clean_cmd

    @property
    def install_cmd(self) -> List[str]:
        """
        Return the list of commands that install the project.
        """
        return self.metadata.install_cmd

    @property
    def metadata(self) -> ProjectMetadata:
        """
        Get up-to-date metadata for the project.
        """
        return self.metadata_storage.get(
            self.name,
            self.opam_switch.get_installed_version("coq"),
            self.opam_switch.get_installed_version("ocaml"))

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Return the name of the project.
        """
        ...

    @property
    @abstractmethod
    def path(self) -> str:
        """
        Get the path to the project's root directory.
        """
        pass

    @property
    def serapi_options(self) -> str:
        """
        Get the SerAPI options for parsing this project's files.

        Returns
        -------
        str
            The command-line options for invoking SerAPI tools, e.g.,
            ``f"sercomp {serapi_options} file.v"``.
        """
        return self.metadata.serapi_options

    @abstractmethod
    def _get_file(self, filename: str, *args, **kwargs) -> CoqDocument:
        """
        Return a specific Coq source file.

        See Also
        --------
        Project.get_file : For public API.
        """
        pass

    def _get_random_sentence_internal(
            self,
            filename: Optional[str],
            glom_proofs: bool,
            **kwargs):
        if filename is None:
            obj = self.get_random_file(**kwargs)
        else:
            obj = self.get_file(filename, **kwargs)
        sentences = self.extract_sentences(
            obj,
            'utf-8',
            glom_proofs,
            self.sentence_extraction_method)
        return sentences

    def _get_size_bytes(self) -> int:
        """
        Get size in bytes of working directory.

        This size should exclude the contents of any .git directories.
        """
        return sum(
            f.stat().st_size
            for f in pathlib.Path(self.path).glob('**/*')
            if f.is_file()) - sum(
                f.stat().st_size
                for f in pathlib.Path(self.path).glob('**/.git/**/*')
                if f.is_file())

    def _make(self, target: str, action: str) -> Tuple[int, str, str]:
        """
        Make a build target (one of build, clean, or install).

        Parameters
        ----------
        target : str
            One of ``"build"``, ``"clean"``, or ``"install"``.
        action : str
            A more descriptive term for the action represented by the
            build target, e.g., ``"compilation"``.

        Returns
        -------
        return_code : int
            The return code, expected to be 0.
        stdout : str
            The standard output of the command.
        stderr : str
            The standard error output of the command.

        Raises
        ------
        RuntimeError
            If no commands for this target are specified.
        ProjectBuildError
            If commands are specified but fail with nonzero exit code.
        """
        # wrap in parentheses to preserve operator precedence when
        # joining commands with &&
        commands = [f"({cmd})" for cmd in getattr(self, f"{target}_cmd")]
        if not commands:
            raise RuntimeError(
                f"{target.capitalize()} command not set for {self.name}.")
        r = BashUtils.run(" && ".join(commands))
        status = "failed" if r.return_code != 0 else "finished"
        msg = (
            f"{action} {status}! Return code is {r.return_code}! "
            f"stdout:\n{r.stdout}\n; stderr:\n{r.stderr}")
        if r.return_code != 0:
            raise ProjectBuildError(msg)
        else:
            logger.debug(msg)
        return (r.return_code, r.stdout, r.stderr)

    @abstractmethod
    def _pre_get_random(self, **kwargs):
        """
        Handle tasks needed before getting a random file (or pair, etc).
        """
        pass

    @abstractmethod
    def _traverse_file_tree(self) -> List[CoqDocument]:
        """
        Traverse the file tree and return a list of Coq file objects.
        """
        pass

    def build(self) -> Tuple[int, str, str]:
        """
        Build the project.
        """
        if self.serapi_options is None:
            self.build_and_get_iqr()
            return 0, "", ""
            # <TODO>: Need to figure out some mechanism to save
            # the new metadata (serapi_options) back to the main storage
            # Problem is, the project has no awareness of the storage
            # so it needs to be a callback or something. Not sure.
        else:
            return self._make("build", "Compilation")

    def build_and_get_iqr(self) -> str:
        """
        Build project and get IQR options, simultaneously.

        Invoking this function will replace any serapi_options already
        present in the metadata.

        Returns
        -------
        str
            The IQR flags string that should be stored in serapi_options
        """
        # Set self.num_cores to 1 for the duration of this function
        # old_num_cores = self.num_cores
        # self.num_cores = 1
        contexts: List[CoqContext] = []
        for cmd in self.build_cmd:
            if "make" in cmd.lower() or "dune" in cmd.lower():
                contexts += strace_build(cmd, workdir=self.path)
            else:
                r = bash.run(cmd, cwd=self.path, env=OpamAPI._environ())
                logging.debug(
                    f"Command {cmd} finished with return code {r.returncode}.")
        self.metadata.serapi_options = str(
            sum([c.iqr for c in contexts],
                IQR(set(),
                    set(),
                    set(),
                    self.path)))
        # self.num_cores = old_num_cores
        return self.serapi_options

    clean = partialmethod(_make, "clean", "Cleaning")
    """
    Clean the build status of the project.
    """

    def get_file(self, filename: str, *args, **kwargs) -> CoqDocument:
        """
        Return a specific Coq source file.

        Parameters
        ----------
        filename : str
            The absolute path to the file to return.

        Returns
        -------
        CoqDocument
            A CoqDocument corresponding to the selected Coq source file

        Raises
        ------
        ValueError
            If given `filename` does not end in ".v"
        """
        if not filename.endswith(".v"):
            raise ValueError("filename must end in .v")
        return self._get_file(filename, *args, **kwargs)

    @abstractmethod
    def get_file_list(self, **kwargs) -> List[str]:
        """
        Return a list of all Coq files associated with this project.

        Returns
        -------
        List[str]
            The list of absolute paths to all Coq files in the project
        """
        pass

    def get_random_file(self, **kwargs) -> CoqDocument:
        """
        Return a random Coq source file.

        Returns
        -------
        CoqDocument
            A random Coq source file in the form of a CoqDocument
        """
        self._pre_get_random(**kwargs)
        files = self._traverse_file_tree()
        result = random.choice(files)
        return result

    def get_random_sentence(
            self,
            filename: Optional[str] = None,
            glom_proofs: bool = True,
            **kwargs) -> str:
        """
        Return a random sentence from the project.

        Filename is random unless it is provided.

        Parameters
        ----------
        filename : Optional[str], optional
            Absolute path to file to load sentence from, by default None
        glom_proofs : bool, optional
            Boolean flag indicating whether proofs should form their own
            pseudo-sentences, by default True

        Returns
        -------
        str
            A random sentence from the project
        """
        sentences = self._get_random_sentence_internal(
            filename,
            glom_proofs,
            **kwargs)
        sentence = random.choice(sentences)
        return sentence

    def get_random_sentence_pair_adjacent(
            self,
            filename: Optional[str] = None,
            glom_proofs: bool = True,
            **kwargs) -> List[str]:
        """
        Return a random adjacent sentence pair from the project.

        Filename is random unless it is provided.

        Parameters
        ----------
        filename : Optional[str], optional
            Absolute path to file to load sentences from, by default
            None
        glom_proofs : bool, optional
            Boolean flag indicating whether proofs should form their own
            pseudo-sentences, by default True

        Returns
        -------
        List of str
            A list of two adjacent sentences from the project, with the
            first sentence chosen at random
        """
        sentences: List[str] = []
        counter = 0
        THRESHOLD = 100
        while len(sentences) < 2:
            if counter > THRESHOLD:
                raise RuntimeError(
                    "Can't find file with more than 1 sentence after",
                    THRESHOLD,
                    "attempts. Try different inputs.")
            sentences = self._get_random_sentence_internal(
                filename,
                glom_proofs,
                **kwargs)
            counter += 1
        first_sentence_idx = random.randint(0, len(sentences) - 2)
        return sentences[first_sentence_idx : first_sentence_idx + 2]

    install = partialmethod(_make, "install", "Installation")
    """
    Install the project system-wide in "coq-contrib".
    """

    @staticmethod
    def extract_sentences(
            document: CoqDocument,
            encoding: str = 'utf-8',
            glom_proofs: bool = True,
            sentence_extraction_method: SEM = SEM.SERAPI) -> List[str]:
        """
        Split the Coq file text by sentences.

        By default, proofs are then re-glommed into their own entries.
        This behavior can be switched off.

        Parameters
        ----------
        document : CoqDocument
            A Coq document.
        encoding : str, optional
            The encoding to use for decoding if a bytestring is
            provided, by default 'utf-8'
        glom_proofs : bool, optional
            A flag indicating whether or not proofs should be re-glommed
            after sentences are split, by default `True`
        sentence_extraction_method : SentenceExtractionMethod
            Method by which sentences should be extracted

        Returns
        -------
        List[str]
            A list of strings corresponding to Coq source file
            sentences, with proofs glommed (or not) depending on input
            flag.
        """
        return sentence_extraction_method.parser().parse_sentences_from_source(
            document,
            encoding,
            glom_proofs)
