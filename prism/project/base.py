"""
Module providing CoqGym project class representations.
"""
import logging
import pathlib
import random
from abc import ABC, abstractmethod
from enum import Enum, auto
from os import PathLike
from typing import List, Optional, Tuple, Union

from seutil import BashUtils

from prism.data.document import CoqDocument
from prism.language.heuristic.parser import HeuristicParser, SerAPIParser
from prism.project.metadata import ProjectMetadata
from prism.util.logging import default_log_level

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
    metadata : Union[PathLike, ProjectMetadata]
        Intialized ProjectMetaData
    sentence_extraction_method : SentenceExtractionMethod
        The method by which sentences are extracted.

    Attributes
    ----------
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
            metadata: Union[PathLike,
                            ProjectMetadata],
            sentence_extraction_method: SEM = SentenceExtractionMethod.SERAPI):
        """
        Initialize Project object.
        """
        if isinstance(metadata, str):
            formatter = ProjectMetadata.infer_formatter(metadata)
            data = ProjectMetadata.load(metadata, fmt=formatter)
            if len(data) > 1:
                raise ValueError(
                    f"{len(data)} metadata instances found in ({metadata})."
                    f"Manually pass a single ProjectMetadata instance instead.")
            metadata = data[0]
        self.size_bytes = self._get_size_bytes()
        self.sentence_extraction_method = sentence_extraction_method
        self.metadata = metadata

    @property
    def build_cmd(self):
        """
        Return ``self.metadata.build_cmd``.

        Returns
        -------
        Optional[str]
            The build command located in project metadata.
        """
        return self.metadata.build_cmd

    @property
    def clean_cmd(self):
        """
        Return ``self.metadata.clean_cmd``.

        Returns
        -------
        Optional[str]
            The clean command located in project metadata.
        """
        return self.metadata.clean_cmd

    @property
    def install_cmd(self):
        """
        Return ``self.metadata.install_cmd``.

        Returns
        -------
        Optional[str]
            The install command located in project metadata.
        """
        return self.metadata.install_cmd

    @property
    def name(self):
        """
        Return ``self.metadata.project_name``.

        Returns
        -------
        str
            Project name located in project metadata.
        """
        return self.metadata.project_name

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
        # TODO: Get from project metadata.
        return ""

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
        if self.build_cmd is None:
            raise RuntimeError(f"Build command not set for {self.name}.")
        r = BashUtils.run(" && ".join(self.build_cmd))
        if r.return_code != 0:
            raise Exception(
                f"Compilation failed! Return code is {r.return_code}! "
                f"stdout:\n{r.stdout}\n; stderr:\n{r.stderr}")
        else:
            logger.debug(
                f"Compilation finished. Return code is {r.return_code}. "
                f"stdout:\n{r.stdout}\n; stderr:\n{r.stderr}")
        return (r.return_code, r.stdout, r.stderr)

    def clean(self) -> Tuple[int, str, str]:
        """
        Clean the build status of the project.
        """
        if self.clean_cmd is None:
            raise RuntimeError(f"Clean command not set for {self.name}.")
        r = BashUtils.run(" && ".join(self.clean_cmd))
        if r.return_code != 0:
            raise Exception(
                f"Cleaning failed! Return code is {r.return_code}! "
                f"stdout:\n{r.stdout}\n; stderr:\n{r.stderr}")
        else:
            logger.debug(
                f"Cleaning finished. Return code is {r.return_code}. "
                f"stdout:\n{r.stdout}\n; stderr:\n{r.stderr}")
        return (r.return_code, r.stdout, r.stderr)

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

    def install(self) -> Tuple[int, str, str]:
        """
        Install the project system-wide in "coq-contrib".
        """
        if self.install_cmd is None:
            raise RuntimeError(f"Install command not set for {self.name}.")
        self.build()
        r = BashUtils.run(" && ".join(self.install_cmd))
        if r.return_code != 0:
            raise Exception(
                f"Installation failed! Return code is {r.return_code}! "
                f"stdout:\n{r.stdout}\n; stderr:\n{r.stderr}")
        else:
            logger.debug(
                f"Installation finished. Return code is {r.return_code}. "
                f"stdout:\n{r.stdout}\n; stderr:\n{r.stderr}")
        return (r.return_code, r.stdout, r.stderr)

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
