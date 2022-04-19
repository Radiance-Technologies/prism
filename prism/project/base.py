"""
Module providing CoqGym project class representations.
"""
import logging
import pathlib
import random
import re
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple, Union
from warnings import warn

from seutil import BashUtils

from prism.data.document import CoqDocument
from prism.util.logging import default_log_level

logger: logging.Logger = logging.getLogger(__name__)
logger.setLevel(default_log_level())


class Project(ABC):
    """
    Abstract base class for representing a Coq project.

    Parameters
    ----------
    dir_abspath : str
        The absolute path to the project's root directory.
    build_cmd : str or None
        The terminal command used to build the project, by default None.
    clean_cmd : str or None
        The terminal command used to clean the project, by default None.
    install_cmd : str or None
        The terminal command used to install the project, by default
        None.

    Attributes
    ----------
    name : str
        The stem of the working directory, used as the project name
    size_bytes : int
        The total space on disk occupied by the files in the dir in
        bytes
    build_cmd : str or None
        The terminal command used to build the project.
    clean_cmd : str or None
        The terminal command used to clean the project.
    install_cmd : str or None
        The terminal command used to install the project..
    """

    proof_enders = ["Qed.", "Save.", "Defined.", "Admitted.", "Abort."]

    def __init__(
            self,
            dir_abspath: str,
            build_cmd: Optional[str] = None,
            clean_cmd: Optional[str] = None,
            install_cmd: Optional[str] = None):
        """
        Initialize Project object.
        """
        self.name = pathlib.Path(dir_abspath).stem
        self.size_bytes = self._get_size_bytes()
        self.build_cmd: Optional[str] = build_cmd
        self.clean_cmd: Optional[str] = clean_cmd
        self.install_cmd: Optional[str] = install_cmd

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

    def _get_size_bytes(self) -> int:
        """
        Get size in bytes of working directory.
        """
        return sum(
            f.stat().st_size
            for f in pathlib.Path(self.path).glob('**/*')
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
        r = BashUtils.run(self.build_cmd)
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
        r = BashUtils.run(self.clean_cmd)
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
        if filename is None:
            obj = self.get_random_file(**kwargs)
        else:
            obj = self.get_file(filename, **kwargs)
        sentences = self.split_by_sentence(obj, 'utf-8', glom_proofs)
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
            if filename is None:
                obj = self.get_random_file(**kwargs)
            else:
                obj = self.get_file(filename, **kwargs)
            sentences = self.split_by_sentence(obj, 'utf-8', glom_proofs)
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
        r = BashUtils.run(self.install_cmd)
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
    def _decode_byte_stream(
            data: Union[bytes,
                        str],
            encoding: str = 'utf-8') -> str:
        """
        Decode the incoming data if it's a byte string.

        Parameters
        ----------
        data : Union[bytes, str]
            Byte-string or string data to be decoded if byte-string
        encoding : str, optional
            Encoding to use in decoding, by default 'utf-8'

        Returns
        -------
        str
            String representation of input data
        """
        return data.decode(encoding) if isinstance(data, bytes) else data

    @staticmethod
    def _strip_comments(
            file_contents: Union[str,
                                 bytes],
            encoding: str = 'utf-8') -> str:
        comment_pattern = r"[(]+\*(.|\n|\r)*?\*[)]+"
        if isinstance(file_contents, bytes):
            file_contents = Project._decode_byte_stream(file_contents, encoding)
        str_no_comments = re.sub(comment_pattern, '', file_contents)
        return str_no_comments

    @staticmethod
    def split_by_sentence(
            document: CoqDocument,
            encoding: str = 'utf-8',
            glom_proofs: bool = True) -> List[str]:
        """
        Split the Coq file text by sentences.

        By default, proofs are then re-glommed into their own entries.
        This behavior can be switched off.

        Parameters
        ----------
        file_contents : Union[str, bytes]
            Complete contents of the Coq source file, either in
            bytestring or string form.
        encoding : str, optional
            The encoding to use for decoding if a bytestring is
            provided, by default 'utf-8'
        glom_proofs : bool, optional
            A flag indicating whether or not proofs should be re-glommed
            after sentences are split, by default `True`

        Returns
        -------
        List[str]
            A list of strings corresponding to Coq source file
            sentences, with proofs glommed (or not) depending on input
            flag.
        """
        file_contents = document.source_code
        if isinstance(file_contents, bytes):
            file_contents = Project._decode_byte_stream(file_contents, encoding)
        file_contents_no_comments = Project._strip_comments(
            file_contents,
            encoding)
        # Split sentences by instances of single periods followed by
        # whitespace. Double (or more) periods are specifically
        # excluded.
        sentences = re.split(r"(?<!\.)\.\s", file_contents_no_comments)
        for i in range(len(sentences)):
            # Replace any whitespace or group of whitespace with a
            # single space.
            sentences[i] = re.sub(r"(\s)+", " ", sentences[i])
            sentences[i] = sentences[i].strip()
            sentences[i] += "."
        if glom_proofs:
            # Reconstruct proofs onto one line.
            result = []
            idx = 0
            while idx < len(sentences):
                try:
                    # Proofs can start with "Proof." or "Proof <other
                    # words>."
                    if sentences[idx] == "Proof." or sentences[idx].startswith(
                            "Proof "):
                        intermediate_list = []
                        while sentences[idx] not in Project.proof_enders:
                            intermediate_list.append(sentences[idx])
                            idx += 1
                        intermediate_list.append(sentences[idx])
                        result.append(" ".join(intermediate_list))
                    else:
                        result.append(sentences[idx])
                    idx += 1
                except IndexError:
                    # If we've gotten here, there's a proof-related
                    # syntax error, and we should stop trying to glom
                    # proofs that are possibly incorrectly formed.
                    warn(
                        "Found an unterminated proof environment in "
                        f"{document.index}. "
                        "Abandoning proof glomming.")
                    return sentences
            # Lop off the final line if it's just a period, i.e., blank.
            if result[-1] == ".":
                result.pop()
        else:
            result = sentences
        return result
