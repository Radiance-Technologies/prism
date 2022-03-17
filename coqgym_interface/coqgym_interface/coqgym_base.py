"""
Utilities module for CoqGym interface.
"""
import os
import pathlib
import random
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from io import TextIOWrapper
from typing import Dict, Generator, List, Optional, Type, Union
from warnings import warn

from git import Commit, InvalidGitRepositoryError, Repo


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

    def __init__(self, dir_abspath: str):
        """
        Initialize Project object.
        """
        self.name = self._get_dir_stem(dir_abspath)
        self.size_bytes = self._get_size_bytes(dir_abspath)

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
        # Split sentences by instances of periods followed by
        # whitespace.
        sentences = re.split(r"\.\s", file_contents_no_comments)
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

    def __init__(self, dir_abspath: str):
        """
        Initialize Project object.
        """
        Repo.__init__(self, dir_abspath)
        ProjectBase.__init__(self, dir_abspath)

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
    """

    def __init__(self, dir_abspath: str, *args, **kwargs):
        """
        Initialize Project object.
        """
        self.working_dir = dir_abspath
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
            with open(file, "rt") as f:
                contents = f.read()
                out_files.append(
                    FileObject(os.path.join(self.working_dir,
                                            file),
                               contents))
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


# Custom types
ProjectDict = Dict[str, Union[ProjectRepo, ProjectDir]]


class CoqGymBaseDataset:
    """
    Base dataset for CoqGym data.

    Attributes
    ----------
    projects : ProjectDict
        The dictionary of Coq projects to draw data from
    weights : Dict[str, float]
        Weights for each project for sampling
    """

    projects: ProjectDict = {}

    def __init__(
            self,
            *,
            project_class: Optional[Type[ProjectBase]] = None,
            projects: Optional[ProjectDict] = None,
            base_dir: Optional[str] = None,
            dir_list: Optional[List[str]] = None):
        """
        Initialize the CoqGymDataset object.

        Provide exactly one of `projects`, `base_dir`, or `dir_list`.

        Parameters
        ----------
        project_class : Optional[Type[ProjectBase]], optional
            Class name for Project objects. Either ProjectRepo or
            ProjectDir. Must be given if `base_dir` or `dir_list` is
            given. Ignored if `projects` is given.
        projects : Optional[ProjectDict], optional
            If provided, use these already-created `Project` objects to
            build the dataset, by default None
        base_dir : Optional[str], optional
            If provided, build `Project` objects from the subdirectories
            in this directory. Any subdirectories that are not
            repositories are ignored, by default None
        dir_list : Optional[List[str]], optional
            If provided, build a `Project` from each of these
            directories. If any of these directories are not
            repositories, an exception is raised, by default None

        Raises
        ------
        ValueError
            If != 1 of the input arguments are provided
        ValueError
            If one or more of the directories in `dir_list` is not a
            repository
        ValueError
            If `project_class` is not provided and either `base_dir` or
            `dir_list` is provided.
        """

        def _three_way_xor(a: bool, b: bool, c: bool) -> bool:
            return (a ^ b ^ c) & ~(a & b & c)

        projects_not_none = projects is not None
        base_dir_not_none = base_dir is not None
        dir_list_not_none = dir_list is not None
        if not _three_way_xor(projects_not_none,
                              base_dir_not_none,
                              dir_list_not_none):
            raise ValueError(
                "Provide exactly one of the input arguments"
                " `projects`, `base_dir`, or `dir_list`.")
        if projects_not_none:
            self.projects = projects
        elif base_dir_not_none:
            if project_class is None:
                raise ValueError(
                    "If `base_dir` is given, `project_class` must be "
                    "given as well.")
            for proj_dir in os.listdir(base_dir):
                if os.path.isdir(os.path.join(base_dir, proj_dir)):
                    try:
                        project = project_class(
                            os.path.join(base_dir,
                                         proj_dir))
                        self.projects[project.name] = project
                    except (InvalidGitRepositoryError, DirHasNoCoqFiles):
                        # If we're using ProjectRepo and a directory is
                        # not a repo, or if we're using ProjectDir and
                        # the directory has no Coq files, just ignore it
                        pass
        else:
            if project_class is None:
                raise ValueError(
                    "If `dir_list` is given, `project_class` must be "
                    "given as well.")
            for directory in dir_list:
                try:
                    project = project_class(directory)
                    self.projects[project.name] = project
                except InvalidGitRepositoryError as e:
                    raise ValueError(
                        f"{directory} in `dir_list` is not a valid repository."
                    ) from e
                except DirHasNoCoqFiles as e:
                    raise ValueError(
                        f"{directory} in `dir_list` has no Coq files.") from e
        # Store project weights for sampling later.
        self.weights = {pn: p.size_bytes for pn,
                        p in self.projects.items()}

    def files(
        self,
        commit_names: Optional[Dict[str,
                                    str]] = None
    ) -> Generator[str,
                   None,
                   None]:
        """
        Yield Coq files from CoqGymBaseDataset.

        Parameters
        ----------
        commit_names : Optional[Dict[str, str]], optional
            The commit (named by branch, hash, or tag) to load from, if
            relevant, for each project, by default None

        Yields
        ------
        str
            Contents of a Coq file in the group of projects
        """
        project_names = sorted(list(self.projects.keys()))
        if commit_names is None:
            commit_names = {pn: 'master' for pn in project_names}
        for project in project_names:
            file_list = self.projects[project].get_file_list(
                commit_name=commit_names[project])
            for file in file_list:
                with open(file, "r") as f:
                    f: TextIOWrapper
                    contents = f.read()
                    yield FileObject(file, contents)

    def get_random_file(
            self,
            project_name: Optional[str] = None,
            commit_name: Optional[str] = None) -> FileObject:
        """
        Return a random Coq source file from one of the projects.

        The commit and project may be specified or left to be chosen at
        random.

        Parameters
        ----------
        project_name : Optional[str], optional
            Project name to draw random file from, by default None
        commit_name : Optional[str], optional
            Commit hash, branch name, or tag name to draw random file
            from, if used by `project_class`, by default None

        Returns
        -------
        FileObject
            A random Coq source file in the form of a FileObject
        """
        if project_name is None:
            project_name = self._get_random_project()
        return self.projects[project_name].get_random_file(
            commit_name=commit_name)

    def get_file(
            self,
            filename: str,
            project_name: str,
            commit_name: str = 'master') -> FileObject:
        """
        Return specific Coq source file from specific project & commit.

        Parameters
        ----------
        filename : str
            The absolute path to the file to return
        project_name : str
            Project name from which to load the file
        commit_name : str, optional
            A commit hash, branch name, or tag name from which to fetch
            the file, if used by `project_class`, by default 'master'

        Returns
        -------
        FileObject
            A FileObject corresponding to the selected Coq source file
        """
        return self.projects[project_name].get_file(
            filename,
            commit_name=commit_name)

    def get_random_sentence(
            self,
            filename: Optional[str] = None,
            project_name: Optional[str] = None,
            glom_proofs: bool = True,
            commit_name: Optional[str] = None) -> str:
        """
        Return a random sentence from the group of projects.

        Filename, project name, and commit are random unless they are
        provided.

        Parameters
        ----------
        filename : Optional[str], optional
            Absolute path to file to load sentence from, by default None
        project_name : Optional[str], optional
            Project name from which to load the file, by default None
        glom_proofs : bool, optional
            Boolean flag indicating whether proofs should form their own
            pseudo-sentences, by default True
        commit_name : Optional[str], optional
            A commit hash, branch name, or tag name from which to fetch
            the file, if used by `project_class`, by default None

        Returns
        -------
        str
            A random sentence from the group of projects
        """
        if project_name is None:
            project_name = self._get_random_project()
        return self.projects[project_name].get_random_sentence(
            filename,
            glom_proofs,
            commit_name=commit_name)

    def get_random_sentence_pair_adjacent(
            self,
            filename: Optional[str] = None,
            project_name: Optional[str] = None,
            glom_proofs: bool = True,
            commit_name: Optional[str] = None) -> List[str]:
        """
        Return a random adjacent sentence pair from the projects.

        Parameters
        ----------
        filename : Optional[str], optional
            Absolute path to file to load sentences from, by default
            None
        project_name : Optional[str], optional
            Project naem from which to load the sentence pair, by
            default None
        glom_proofs : bool, optional
            Boolean flag indicating whether proofs should form their own
            pseduo-sentences, by default True
        commit_name : Optional[str], optional
            Commit hash, branch name, or tag name from which to fetch
            the sentence pair, by default None

        Returns
        -------
        List[str]
            A list of two adjacent sentences from the projects, with the
            first sentence chosen at random
        """
        if project_name is None:
            project_name = self._get_random_project()
        return self.projects[project_name].get_random_sentence_pair_adjacent(
            filename,
            glom_proofs,
            commit_name=commit_name)

    def sentences(
            self,
            commit_names: Optional[Dict[str,
                                        str]] = None,
            glom_proofs: bool = True) -> Generator[str,
                                                   None,
                                                   None]:
        """
        Yield Coq sentences from CoqGymBaseDataset.

        Parameters
        ----------
        commit_names : Optional[Dict[str, str]], optional
            The commit (named by branch, hash, or tag) to load from, if
            relevant, for each project, by default None

        Yields
        ------
        str
            A single sentence, which might be a glommed proof if
            `glom_proofs` is True, from a Coq file within the group of
            projects in the dataset
        """
        coq_file_generator = self.files(commit_names)
        for file_obj in coq_file_generator:
            sentence_list = ProjectBase.split_by_sentence(
                file_obj.file_contents,
                glom_proofs=glom_proofs)
            for sentence in sentence_list:
                yield sentence

    def _get_random_project(self) -> str:
        weights = []
        project_names = list(self.projects.keys())
        for proj in project_names:
            weights.append(self.weights[proj])
        chosen_proj = random.choices(project_names, weights, k=1)[0]
        return chosen_proj


def main():
    """
    Test module functionality.
    """
    repo_folder = "../data/CompCert"
    dataset = CoqGymBaseDataset(
        project_class=ProjectRepo,
        dir_list=[repo_folder])
    csg = dataset.sentences()
    for _i, _ in enumerate(csg):
        pass
    print(_i)


if __name__ == "__main__":
    main()
