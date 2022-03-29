"""
Module providing CoqGym project class representations.
"""
import os
import pathlib
import random
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Union
from warnings import warn

from git import Commit, Repo


@dataclass
class FileObject:
    """
    Class for file objects.

    Attributes
    ----------
    abspath : str
        Absolute path to the file
    file_contents : str or bytes
        Contents of the file, either in string or byte-string form
    """

    abspath: str
    file_contents: Union[str, bytes]


class DirHasNoCoqFiles(Exception):
    """
    Exception indicating that the current directory has no Coq files.

    Sub-directories should be checked as well before raising this
    exception.
    """

    pass


class ProjectBase(ABC):
    """
    Abstract base class for representing a Coq project.

    Attributes
    ----------
    name : str
        The stem of the working directory, used as the project name
    size_bytes : int
        The total space on disk occupied by the files in the dir in
        bytes
    """

    proof_enders = ["Qed.", "Save.", "Defined.", "Admitted.", "Abort."]

    def __init__(self, dir_abspath: str, ignore_decode_errors: bool = False):
        """
        Initialize Project object.
        """
        self.name = self._get_dir_stem(dir_abspath)
        self.size_bytes = self._get_size_bytes(dir_abspath)
        self.ignore_decode_errors = ignore_decode_errors

    @abstractmethod
    def _get_dir_stem(self, dir_abspath: str) -> str:
        """
        Extract directory stem from working directory.
        """
        pass

    @abstractmethod
    def _get_size_bytes(self, dir_abspath: str) -> int:
        """
        Get size in bytes of working directory.
        """
        pass

    @abstractmethod
    def _pre_get_random(self, **kwargs):
        """
        Handle tasks needed before getting a random file (or pair, etc).
        """
        pass

    @abstractmethod
    def _traverse_file_tree(self) -> List[FileObject]:
        """
        Traverse the file tree and return a list of Coq file objects.
        """
        pass

    @abstractmethod
    def get_file(self, filename: str, **kwargs) -> FileObject:
        """
        Return a specific Coq source file.

        Parameters
        ----------
        filename : str
            The absolute path to the file to return.

        Returns
        -------
        FileObject
            A FileObject corresponding to the selected Coq source file

        Raises
        ------
        ValueError
            If given `filename` does not end in ".v"
        """
        if not filename.endswith(".v"):
            raise ValueError("filename must end in .v")

    @abstractmethod
    def get_file_list(self, **kwargs) -> List[FileObject]:
        """
        Return a list of all Coq files associated with this project.

        Returns
        -------
        List[str]
            The list of absolute paths to all Coq files in the project
        """
        pass

    def get_random_file(self, **kwargs) -> FileObject:
        """
        Return a random Coq source file.

        Returns
        -------
        FileObject
            A random Coq source file in the form of a FileObject
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
        contents = obj.file_contents
        sentences = ProjectBase.split_by_sentence(
            contents,
            'utf-8',
            glom_proofs)
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
            contents = obj.file_contents
            sentences = ProjectBase.split_by_sentence(
                contents,
                'utf-8',
                glom_proofs)
            counter += 1
        first_sentence_idx = random.randint(0, len(sentences) - 2)
        return sentences[first_sentence_idx : first_sentence_idx + 2]

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
            file_contents = ProjectBase._decode_byte_stream(
                file_contents,
                encoding)
        str_no_comments = re.sub(comment_pattern, '', file_contents)
        return str_no_comments

    @staticmethod
    def split_by_sentence(
            file_contents: Union[str,
                                 bytes],
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
        if isinstance(file_contents, bytes):
            file_contents = ProjectBase._decode_byte_stream(
                file_contents,
                encoding)
        file_contents_no_comments = ProjectBase._strip_comments(
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
                        while sentences[idx] not in ProjectBase.proof_enders:
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
                        "Found an unterminated proof environment. "
                        "Abandoning proof glomming.")
                    return sentences
            # Lop off the final line if it's just a period, i.e., blank.
            if result[-1] == ".":
                result.pop()
        else:
            result = sentences
        return result


class ProjectRepo(Repo, ProjectBase):
    """
    Class for representing a Coq project.

    Based on GitPython's `Repo` class.

    Attributes
    ----------
    name : str
        The stem of the repo working directory, used as the project name
    size_bytes : int
        The total space on disk occupied by the files in the master
        branch in bytes.
    """

    def __init__(self, dir_abspath: str, ignore_decode_errors: bool = True):
        """
        Initialize Project object.
        """
        Repo.__init__(self, dir_abspath)
        ProjectBase.__init__(self, dir_abspath, ignore_decode_errors)

    def _get_dir_stem(self, *args, **kwargs) -> str:
        """
        Extract directory stem from working directory.
        """
        return pathlib.Path(self.working_dir).stem

    def _get_size_bytes(self, *args, **kwargs) -> int:
        """
        Get size in bytes of working directory.
        """
        return sum(
            f.stat().st_size
            for f in pathlib.Path(self.working_dir).glob('**/*')
            if f.is_file())

    def _pre_get_file(self, **kwargs):
        """
        Set the current commit; use master if none given.
        """
        if "commit_name" in kwargs.keys():
            if kwargs["commit_name"] is None:
                self.current_commit_name = "master"
            else:
                self.current_commit_name = kwargs["commit_name"]
        else:
            self.current_commit_name = "master"

    def _pre_get_random(self, **kwargs):
        """
        Set the current commit; use random if none given.
        """
        if "commit_name" in kwargs.keys():
            if kwargs["commit_name"] is None:
                self.current_commit_name = self.get_random_commit()
            else:
                self.current_commit_name = kwargs["commit_name"]
        else:
            self.current_commit_name = self.get_random_commit()

    def _traverse_file_tree(self) -> List[FileObject]:
        """
        Traverse the file tree and return a full list of file objects.
        """
        commit = self.commit(self.current_commit_name)
        files = [f for f in commit.tree.traverse() if f.abspath.endswith(".v")]
        return [FileObject(f.abspath, f.data_stream.read()) for f in files]

    def get_file(
            self,
            filename: str,
            commit_name: str = 'master') -> FileObject:
        """
        Return a specific Coq source file from a specific commit.

        Parameters
        ----------
        filename : str
            The absolute path to the file to return.
        commit_name : str
            A commit hash, branch name, or tag name from which to fetch
            the file. This is 'master' by default.

        Returns
        -------
        FileObject
            A FileObject corresponding to the selected Coq source file

        Raises
        ------
        ValueError
            If given `filename` does not end in ".v"
        """
        super().get_file(filename)
        commit = self.commit(commit_name)
        # Compute relative path
        rel_filename = filename.replace(commit.tree.abspath, "")[1 :]
        return FileObject(
            filename,
            (commit.tree / rel_filename).data_stream.read())

    def get_file_list(self, commit_name: str = 'master') -> List[FileObject]:
        """
        Return a list of all Coq files associated with this project.

        Parameters
        ----------
        commit_name : str
            A commit hash, branch name, or tag name from which to get
            the file list. This is 'master' by default.

        Returns
        -------
        List[str]
            The list of absolute paths to all Coq files in the project
        """
        commit = self.commit(commit_name)
        files = [
            str(f.abspath)
            for f in commit.tree.traverse()
            if f.abspath.endswith(".v")
        ]
        return sorted(files)

    def get_random_commit(self) -> Commit:
        """
        Return a random `Commit` object from the project repo.

        Returns
        -------
        Commit
            A random `Commit` object from the project repo
        """

        def _get_hash(commit: Commit) -> str:
            return commit.hexsha

        commit_hashes = list(map(_get_hash, self.iter_commits('--all')))
        chosen_hash = random.choice(commit_hashes)
        result = self.commit(chosen_hash)
        return result

    def get_random_file(self, commit_name: Optional[str] = None) -> FileObject:
        """
        Return a random Coq source file from the repo.

        The commit may be specified or left to be chosen at radnom.

        Parameters
        ----------
        commit_name : str or None
            A commit hash, branch name, or tag name indicating where
            the file should be selected from. If None, commit is chosen
            at random.

        Returns
        -------
        FileObject
            A random Coq source file in the form of a FileObject
        """
        return super().get_random_file(commit_name=commit_name)

    def get_random_sentence(
            self,
            filename: Optional[str] = None,
            glom_proofs: bool = True,
            commit_name: Optional[str] = None) -> str:
        """
        Return a random sentence from the project.

        Filename and commit are random unless they are provided.

        Parameters
        ----------
        filename : Optional[str], optional
            Absolute path to file to load sentence from, by default None
        glom_proofs : bool, optional
            Boolean flag indicating whether proofs should form their own
            pseudo-sentences, by default True
        commit_name : Optional[str], optional
            Commit name (hash, branch name, tag name) to load sentence
            from, by default None

        Returns
        -------
        str
            A random sentence from the project
        """
        return super().get_random_sentence(
            filename,
            glom_proofs,
            commit_name=commit_name)

    def get_random_sentence_pair_adjacent(
            self,
            filename: Optional[str] = None,
            glom_proofs: bool = True,
            commit_name: Optional[str] = None) -> List[str]:
        """
        Return a random adjacent sentence pair from the project.

        Filename and commit are random unless they are provided.

        Parameters
        ----------
        filename : Optional[str], optional
            Absolute path to file to load sentences from, by default
            None
        glom_proofs : bool, optional
            Boolean flag indicating whether proofs should form their own
            pseudo-sentences, by default True
        commit_name : Optional[str], optional
            Commit name (hash, branch name, tag name) to load sentences
            from, by default None

        Returns
        -------
        List of str
            A list of two adjacent sentences from the project, with the
            first sentence chosen at random
        """
        return super().get_random_sentence_pair_adjacent(
            filename,
            glom_proofs,
            commit_name=commit_name)


class ProjectDir(ProjectBase):
    """
    Class for representing a Coq project.

    This class makes no assumptions about whether the project directory
    is a git repository or not.

    Attributes
    ----------
    name : str
        The stem of the repo working directory, used as the project name
    size_bytes : int
        The total space on disk occupied by the files in the master
        branch in bytes.
    working_dir : str
        Absolute path to the working directory
    ignore_decode_errors : bool
        Skip files with UnicodeDecodeError and ignore the exception
        if True, otherwise raise the exception.
    """

    def __init__(self, dir_abspath: str, *args, **kwargs):
        """
        Initialize Project object.
        """
        self.working_dir = dir_abspath
        self.ignore_decode_errors: bool = kwargs.get(
            'ignore_decode_errors',
            False)
        if not self._traverse_file_tree():
            raise DirHasNoCoqFiles(f"{dir_abspath} has no Coq files.")
        super().__init__(dir_abspath, *args, **kwargs)

    def _get_dir_stem(self, *args, **kwargs) -> str:
        """
        Extract directory stem from working directory.
        """
        return pathlib.Path(self.working_dir).stem

    def _get_size_bytes(self, *args, **kwargs) -> int:
        """
        Get size in bytes of working directory.
        """
        return sum(
            f.stat().st_size
            for f in pathlib.Path(self.working_dir).glob('**/*')
            if f.is_file())

    def _pre_get_file(self, **kwargs):
        """
        Do nothing.
        """
        pass

    def _pre_get_random(self, **kwargs):
        """
        Do nothing.
        """
        pass

    def _traverse_file_tree(self) -> List[FileObject]:
        """
        Traverse the file tree and return a list of Coq file objects.
        """
        files = pathlib.Path(self.working_dir).rglob("*.v")
        out_files = []
        for file in files:
            try:
                with open(file, "rt") as f:
                    contents = f.read()
                    out_files.append(
                        FileObject(
                            os.path.join(self.working_dir,
                                         file),
                            contents))
            except UnicodeDecodeError as e:
                if not self.ignore_decode_errors:
                    raise e
        return out_files

    def get_file(self, filename: str, *args, **kwargs) -> FileObject:
        """
        Get a specific Coq file and return the corresponding FileObject.

        Parameters
        ----------
        filename : str
            The absolute path to the file

        Returns
        -------
        FileObject
            The corresponding FileObject

        Raises
        ------
        ValueError
            If given `filename` does not end in ".v"
        """
        super().get_file(filename)
        with open(filename, "rt") as f:
            contents = f.read()
        return FileObject(filename, contents)

    def get_file_list(self, **kwargs) -> List[FileObject]:
        """
        Return a list of all Coq files associated with this project.

        Returns
        -------
        List[str]
            The list of absolute paths to all Coq files in the project
        """
        files = [
            str(i.resolve())
            for i in pathlib.Path(self.working_dir).rglob("*.v")
        ]
        return sorted(files)
