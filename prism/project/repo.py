"""
Module providing CoqGym project repository class representations.
"""
import os
import random
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Union

from git import Commit, Repo

from prism.data.document import CoqDocument
from prism.language.gallina.parser import CoqParser
from prism.project.base import Project


class CommitNode:
    """
    Class used to store a Commit with parent and child information.
    """
    def __init__(self, git_commit: Commit, parent: Commit, child: Commit):
        self._git_commit = git_commit
        self._parent = parent
        self._child = child

    @property
    def parent(self):
        return self._parent

    @property
    def child(self):
        return self._child

    @property
    def commit(self):
        return self._git_commit


def commit_dict_factory(
        repo: Union[Repo,
                    str,
                    os.PathLike]) -> Dict[str,
                                          CommitNode]:
    """
    Function for creating a dictionary of CommitNodes from a GitPython
    repo, or a repo on disk.

    Parameters
    ----------
    repo: Union[Repo, str, os.PathLike]
    Either a GitPython Repo, or a path to a local instance
    of a git repo

    Returns
    -------
    Dict[str, CommitNode]
    """
    if isinstance(repo, str) or isinstance(repo, os.PathLike):
        repo = Repo(repo)

    commits = list(repo.commit().iter_parents())

    if len(commits) <= 0:
        return {}

    commit_dict = {}

    commit_node_first = CommitNode(commits[0], commits[1], None)
    commit_dict[commits[0].hexsha] = commit_node_first

    for i in range(1, len(commits) - 1):
        child = commits[i - 1]
        tmp_commit = commits[i]
        parent = commits[i + 1]
        commit_node = CommitNode(tmp_commit, parent, child)
        commit_dict[tmp_commit.hexsha] = commit_node

    commit_node_last = CommitNode(commits[-1], None, commits[-2])
    commit_dict[commits[-1].hexsha] = commit_node_last

    return commit_dict


class CommitMarchStrategy(Enum):
    # Progress through newer and newer commits
    # until all have been finished
    NEW_MARCH_FIRST = 1
    # Progress through older and older commits
    # until all have been finished
    OLD_MARCH_FIRST = 2
    # Alternate newer and older steps progressively
    # from the center
    CURLICUE = 3


class CommitIterator:
    """
    Class for handling iteration over a range of commits.
    """
    def __init__(
        self,
        repo: Repo,
        commit_sha: str,
        march_strategy: Optional[CommitMarchStrategy] = CommitMarchStrategy(1)):
        """
        Initialize CommitIterator

        """
        self._repo = repo
        self._commit_dict = commit_dict_factory(self._repo)
        self._commit_sha = commit_sha

        self._march_strategy = march_strategy
        nmf = CommitMarchStrategy.NEW_MARCH_FIRST
        omf = CommitMarchStrategy.OLD_MARCH_FIRST
        crl = CommitMarchStrategy.CURLICUE
        self._next_func_dict = {nmf: self.new_march_first,
                                omf: self.old_march_first,
                                crl: self.curlicue}
        self._next_func = self._next_func_dict[self._march_strategy]

        if self._commit_sha not in self._commit_dict.keys():
            raise KeyError("Commit sha supplied to CommitIterator not in repo")
        self._last_ret = "old"
        self._newest_commit = self._commit_dict[self._commit_sha]
        self._oldest_commit = self._commit_dict[self._commit_sha]

    def set_commit(self, sha):
        """
        Reset center commit.
        """
        if sha not in self._commit_dict.keys():
            raise KeyError("Commit sha supplied to CommitIterator not in repo")
        self._commit_sha = sha
        self._newest_commit = self._commit_dict[self._commit_sha]
        self._oldest_commit = self._commit_dict[self._commit_sha]

    def new_march_first(self):
        if self._newest_commit.child is not None:
            self._newest_commit = self._newest_commit.child
            return self._newest_commit
        elif self._oldest_commit.parent is not None:
            self._oldest_commit = self._oldest_commit.parent
            return self._oldest_commit
        else:
            raise StopIteration


    def old_march_first(self):
        if self._oldest_commit.parent is not None:
            self._oldest_commit = self._oldest_commit.parent
            return self._oldest_commit
        elif self._newest_commit.child is not None:
            self._newest_commit = self._newest_commit.child
            return self._newest_commit
        else:
            raise StopIteration

    def curlicue(self):
        if self._last_ret == "old" and self._newest_commit.child is not None:
            self._last_ret = "new"
            self._newest_commit = self._newest_commit.child
            return self._newest_commit
        elif self._last_ret == "new" and self._oldest_commit.parent is not None:
            self._last_ret = "old"
            self._oldest_commit = self._oldest_commit.parent
            return self._oldest_commit
        else:
            if self._last_ret != "new" and self._last_ret != "old":
                raise Exception("Malformed")
            else:
                raise StopIteration

    def __next__(self):
        return self._next_func()

    def __iter__(self):
        self._last_ret = "old"
        self._newest_commit = self._commit_dict[self._commit_sha]
        self._oldest_commit = self._commit_dict[self._commit_sha]
        return self





class ProjectRepo(Repo, Project):
    """
    Class for representing a Coq project.

    Based on GitPython's `Repo` class.
    """

    def __init__(self, dir_abspath: str, *args, **kwargs):
        """
        Initialize Project object.
        """
        Repo.__init__(self, dir_abspath)
        Project.__init__(self, dir_abspath, *args, **kwargs)
        self.current_commit_name = None  # i.e., HEAD

    @property
    def path(self) -> str:  # noqa: D102
        return self.working_dir

    def _get_file(
            self,
            filename: str,
            commit_name: Optional[str] = None) -> CoqDocument:
        """
        Return a specific Coq source file from a specific commit.

        This function may change the git repo HEAD on disk.

        Parameters
        ----------
        filename : str
            The absolute path to the file to return.
        commit_name : str or None, optional
            A commit hash, branch name, or tag name from which to fetch
            the file. Defaults to HEAD.

        Returns
        -------
        CoqDocument
            A CoqDocument corresponding to the selected Coq source file

        Raises
        ------
        ValueError
            If given `filename` does not end in ".v"
        """
        commit = self.commit(commit_name)
        self.git.checkout(commit_name)
        # Compute relative path
        rel_filename = filename.replace(commit.tree.abspath, "")[1 :]
        return CoqDocument(
            rel_filename,
            project_path=self.path,
            source_code=CoqParser.parse_source(
                (commit.tree / rel_filename).abspath))

    def _pre_get_file(self, **kwargs):
        """
        Set the current commit; use HEAD if none given.
        """
        self.current_commit_name = kwargs.get("commit_name", None)

    def _pre_get_random(self, **kwargs):
        """
        Set the current commit; use random if none given.
        """
        commit_name = kwargs.get("commit_name", None)
        if commit_name is None:
            kwargs['commit_name'] = self.get_random_commit()
        self._pre_get_file(**kwargs)

    def _traverse_file_tree(self) -> List[CoqDocument]:
        """
        Traverse the file tree and return a full list of file objects.

        This function may change the git repo HEAD on disk.
        """
        commit = self.commit(self.current_commit_name)
        self.git.checkout(self.current_commit_name)
        files = [f for f in commit.tree.traverse() if f.abspath.endswith(".v")]
        return [
            CoqDocument(
                f.path,
                project_path=self.path,
                source_code=CoqParser.parse_source(f.abspath)) for f in files
        ]

    def get_file_list(self, commit_name: Optional[str] = None) -> List[str]:
        """
        Return a list of all Coq files associated with this project.

        Parameters
        ----------
        commit_name : str or None, optional
            A commit hash, branch name, or tag name from which to get
            the file list. This is HEAD by default.

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

    def get_random_file(self, commit_name: Optional[str] = None) -> CoqDocument:
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
        CoqDocument
            A random Coq source file in the form of a CoqDocument
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
