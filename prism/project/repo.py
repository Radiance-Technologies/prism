"""
Module providing CoqGym project repository class representations.
"""
import random
from enum import Enum
from typing import List, Optional

from git import Commit, Repo

from prism.data.document import CoqDocument
from prism.language.gallina.parser import CoqParser
from prism.project.base import Project


class CommitTraversalStrategy(Enum):
    """
    Enum used for describing iteration algorithm.
    """
    # Progress through newer and newer commits
    # until all have been finished
    NEW_MARCH_FIRST = 1
    # Progress through older and older commits
    # until all have been finished
    OLD_MARCH_FIRST = 2
    # Alternate newer and older steps progressively
    # from the center, assuming the center is a newer
    # step
    CURLICUE_NEW = 3
    # Alternate newer and older steps progressively
    # from the center, assuming the center is an older
    # step
    CURLICUE_OLD = 4


class CommitIterator:
    """
    Class for handling iteration over a range of commits.
    """

    def __init__(
        self,
        repo: Repo,
        commit_sha: str,
        march_strategy: Optional[
            CommitTraversalStrategy] = CommitTraversalStrategy.NEW_MARCH_FIRST):
        """
        Initialize CommitIterator.

        Parameters
        ----------
        repo : git.Repo
            Repo, the commits of which we wish to iterate through.

        commit_sha : str
            Initial commit which we wish to treat as the starting point
            for the iteration

        march_strategy : CommitTraversalStrategy
            The particular method of iterating over the repo which
            we wish to use.
        """
        self._repo = repo
        self._commits = list(repo.commit().iter_parents())
        self._commit_sha = commit_sha
        self._commit_sha_list = [x.hexsha for x in self._commits]
        self._commit_idx = self._commit_sha_list.index(self._commit_sha)
        if self._commit_sha not in self._commit_sha_list:
            raise KeyError("Commit sha supplied to CommitIterator not in repo")

        self._march_strategy = march_strategy
        nmf = CommitTraversalStrategy.NEW_MARCH_FIRST
        omf = CommitTraversalStrategy.OLD_MARCH_FIRST
        crn = CommitTraversalStrategy.CURLICUE_NEW
        cro = CommitTraversalStrategy.CURLICUE_OLD
        self._next_func_dict = {
            nmf: self.new_march_first,
            omf: self.old_march_first,
            crn: self.curlicue,
            cro: self.curlicue
        }
        self._next_func = self._next_func_dict[self._march_strategy]

        self._last_ret = ""
        self._newest_commit = None
        self._oldest_commit = None
        self.init_commit_indices()

    def init_commit_indices(self):
        """
        Initialize commit indices.

        Initialize the newest and oldest commit indices, according to
        where the starting commit is.
        """
        if self._commit_idx > 0:
            self._newest_commit = self._commit_idx - 1
        else:
            self._newest_commit = None
        if self._commit_idx < len(self._commits) - 1:
            self._oldest_commit = self._commit_idx + 1
        else:
            self._oldest_commit = None

    def set_center_commit(self, sha):
        """
        Reset center commit.
        """
        if sha not in self._commit_sha_list:
            raise KeyError("Commit sha supplied to CommitIterator not in repo")
        self._commit_sha = sha
        self._commit_idx = self._commit_sha_list.index(self._commit_sha)
        self.init_commit_indices()

    def new_march_first(self):
        """
        Return newer commits until none remain, then older.

        The commit traversal strategy which follows all progressively
        newer commits before it returns older commits.
        """
        if self._newest_commit > 0:
            tmp_idx = self._newest_commit
            self._newest_commit = self._newest_commit - 1
            return self._commits[tmp_idx]
        elif self._oldest_commit < len(self._commits):
            tmp_idx = self._oldest_commit
            self._oldest_commit = self._oldest_commit + 1
            return self._commits[tmp_idx]
        else:
            raise StopIteration

    def old_march_first(self):
        """
        Return older commits until none remain, then newer.

        The commit traversal strategy which follows all progressively
        older commits before it returns newer commits.
        """
        if self._oldest_commit < len(self._commits):
            tmp_idx = self._oldest_commit
            self._oldest_commit = self._oldest_commit + 1
            return self._commits[tmp_idx]
        elif self._newest_commit > 0:
            tmp_idx = self._newest_commit
            self._newest_commit = self._newest_commit - 1
            return self._commits[tmp_idx]
        else:
            raise StopIteration

    def curlicue(self):
        """
        Return commits in a progressively widened area about the center.

        The commit traversal strategy which alternates between newer and
        older commits, progressively widening the distance from the
        central commit.
        """
        if self._newest_commit == 0:
            self._last_ret = "new"
        if self._oldest_commit == len(self._commits):
            self._last_ret = "old"
        if self._last_ret == "old" and self._newest_commit > 0:
            self._last_ret = "new"
            tmp_idx = self._newest_commit
            self._newest_commit = self._newest_commit - 1
            return self._commits[tmp_idx]
        elif (self._last_ret == "new"
              and self._oldest_commit < len(self._commits) - 1):
            self._last_ret = "old"
            tmp_idx = self._oldest_commit
            self._oldest_commit = self._oldest_commit + 1
            return self._commits[tmp_idx]
        else:
            if self._last_ret != "new" and self._last_ret != "old":
                raise Exception("Malformed")
            else:
                raise StopIteration

    def __next__(self):
        """
        Iterator continuation method.
        """
        return self._next_func()

    def __iter__(self):
        """
        Iterator initiation method.
        """
        self.init_commit_indices()
        if self._march_strategy == CommitTraversalStrategy.CURLICUE_NEW \
           or self._march_strategy == CommitTraversalStrategy.NEW_MARCH_FIRST:
            self._last_ret = "old"
            self._newest_commit = self._commit_idx
        elif (self._march_strategy == CommitTraversalStrategy.CURLICUE_OLD or
              self._march_strategy == CommitTraversalStrategy.OLD_MARCH_FIRST):
            self._last_ret = "new"
            self._oldest_commit = self._commit_idx
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
