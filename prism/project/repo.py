"""
Module providing Coq project repository class representations.
"""
from __future__ import annotations

import os
import pathlib
import random
import warnings
from collections import deque
from enum import Enum
from typing import List, Optional

import git
from git import Commit, Repo

from prism.data.document import CoqDocument
from prism.project.base import MetadataArgs, Project
from prism.project.metadata.storage import MetadataStorage


class CommitTraversalStrategy(Enum):
    """
    Enum used for describing iteration algorithm.
    """

    NEW_FIRST = 1
    """
    Progress through newer and newer commits
    until all have been finished.
    """
    OLD_FIRST = 2
    """
    Progress through older and older commits
    until all have been finished.
    """
    CURLICUE_NEW = 3
    """
    Alternate newer and older steps progressively
    from the center, assuming the center is a newer
    step.
    """
    CURLICUE_OLD = 4
    """
    Alternate newer and older steps progressively
    from the center, assuming the center is an older
    step.
    """


class CommitIterator:
    """
    Class for handling iteration over a range of commits.
    """

    def __init__(
            self,
            repo: ProjectRepo,
            starting_hash: Optional[str] = None,
            march_strategy: Optional[
                CommitTraversalStrategy] = CommitTraversalStrategy.NEW_FIRST,
            oldest_hash_limit: Optional[str] = None,
            newest_hash_limit: Optional[str] = None):
        """
        Initialize CommitIterator.

        Parameters
        ----------
        repo : ProjectRepo
            Repo, the commits of which we wish to iterate through.
        starting_hash : str or None, optional
            If this is provided, this hash is used as the starting
            point, by default None.
        march_strategy : CommitTraversalStrategy
            The particular method of iterating over the repo which
            we wish to use.
        oldest_hash_limit : str or None, optional
            If provided, iterator will not return any commits before the
            one with this hash, by default None.
        newest_hash_limit : str or None, optional
            If provided, iterator will not return any commits after the
            one with this hash, by default None.

        Raises
        ------
        ValueError
            If `starting_hash`, `oldest_hash_limit`, or
            `newest_hash_limit` are not valid commits of the given
            `repo`,
            or
            if `starting_hash` is not within the range of commits
            implied by the oldest and newest hash limits.
        """
        self._repo = repo
        # Get every commit from repo regardless of branch, parents, etc.
        commit_generator = self._repo.iter_commits("--all")
        self.dated_hashes = [
            (c.committed_date,
             c.hexsha) for c in commit_generator
        ]
        # Sort in ascending order by date
        self.dated_hashes = sorted(self.dated_hashes, key=lambda x: x[0])
        self.hashes = [i[1] for i in self.dated_hashes]

        # Apply limits if given
        def get_hash_index(
                sha: Optional[str],
                desc: str,
                default: Optional[int]) -> Optional[int]:
            try:
                return self.hashes.index(sha) if sha is not None else default
            except ValueError as e:
                raise ValueError(
                    f"No commit found in repo {repo.name} for {desc} {sha}"
                ) from e

        oldest_idx = get_hash_index(oldest_hash_limit, "oldest_hash_limit", 0)
        newest_idx = get_hash_index(
            newest_hash_limit,
            "newest_hash_limit",
            len(self.hashes) - 1) + 1
        starting_idx = get_hash_index(starting_hash, "starting_hash", None)
        self.hashes = self.hashes[oldest_idx : newest_idx]
        # Validate starting_hash after limits are applied
        if starting_idx is not None:
            if starting_idx < oldest_idx or starting_idx > newest_idx:
                raise ValueError(
                    f"starting_hash {starting_hash} not in range of hashes from"
                    f" repo {repo.name} after applying oldest/newest limits.")
            starting_idx = starting_idx - oldest_idx
        # Apply march_strategy
        if march_strategy == CommitTraversalStrategy.NEW_FIRST:
            self._hash_iterator = reversed(self.hashes[: starting_idx + 1])
        elif march_strategy == CommitTraversalStrategy.OLD_FIRST:
            self._hash_iterator = iter(self.hashes[starting_idx :])
        else:
            # Get the center index, then figure out which curlicue we're
            # doing.
            if starting_idx is not None:
                center_idx = starting_idx
            else:
                center_idx = int(len(self.hashes) / 2)
            temp_list = deque()
            if march_strategy == CommitTraversalStrategy.CURLICUE_NEW:
                old_list = deque(self.hashes[: center_idx + 1])
                new_list = deque(self.hashes[center_idx + 1 :])
                while old_list and new_list:
                    temp_list.append(old_list.pop())
                    temp_list.append(new_list.popleft())
            elif march_strategy == CommitTraversalStrategy.CURLICUE_OLD:
                old_list = deque(self.hashes[: center_idx])
                new_list = deque(self.hashes[center_idx :])
                while old_list and new_list:
                    temp_list.append(new_list.popleft())
                    temp_list.append(old_list.pop())
            else:
                raise ValueError(
                    f"{march_strategy} is not a valid march strategy.")
            # Deal with list remainders if center is not actually the
            # center.
            if old_list:
                temp_list.extend(list(reversed(old_list)))
            elif new_list:
                temp_list.extend(new_list)
            self._hash_iterator = iter(temp_list)

    def __iter__(self):
        """
        Initialize iterator.
        """
        return self

    def __next__(self):
        """
        Return next value in container.
        """
        return next(self._hash_iterator)


class ChangedCoqCommitIterator(CommitIterator):
    """
    Subclass of CommitIterator only yielding changed .v files.
    """

    def __next__(self):
        """
        Yield each commit in the specified order.

        Excludes commits that did not change a .v file.
        """
        if not hasattr(self, "_last"):
            self._last = None
        while True:
            hash = super().__next__()
            commit = self._repo.commit(hash)
            if self._last is None:
                break
            else:
                changed_files = self._repo.git.diff(
                    "--name-only",
                    commit,
                    self._last).split("\n")
                if any(filename.endswith(".v") for filename in changed_files):
                    break
        self._last = commit
        return commit.hexsha


class ProjectRepo(Repo, Project):
    """
    Class for representing a Coq project.

    Based on GitPython's `Repo` class.
    """

    def __init__(
            self,
            dir_abspath: os.PathLike,
            *args,
            commit_sha: Optional[str] = None,
            **kwargs):
        """
        Initialize Project object.
        """
        try:
            Repo.__init__(self, dir_abspath)
        except git.exc.NoSuchPathError:
            dir_abspath = pathlib.Path(dir_abspath)
            storage = [a for a in args if isinstance(a, MetadataStorage)]
            if not storage:
                storage = kwargs.get('metadata_storage')
            else:
                storage = storage[0]
            try:
                # try to infer project name from stem
                project_urls = storage.get_project_sources(dir_abspath.stem)
            except KeyError:
                project_urls = set()
            if project_urls:
                # clone from first viable URL
                for project_url in project_urls:
                    try:
                        Repo.clone_from(project_url, dir_abspath)
                    except git.exc.GitCommandError:
                        continue
                    else:
                        break
            else:
                # no viable sources to clone from
                # re-raise original error
                raise
            Repo.__init__(self, dir_abspath)
        Project.__init__(self, dir_abspath, *args, **kwargs)
        self.current_commit_name: Optional[str] = None  # i.e., HEAD
        """
        The name/SHA of the current virtual commit.

        By default None, which serves as an alias for the current index
        HEAD, this attribute controls access to commit files without
        requiring one to actually change the working tree.
        """
        # NOTE (AG): I question the value of this attribute and its
        # current usage and wonder if it could be refactored to
        # something simpler.

        storage = self.metadata_storage

        self.reset_head = self.commit_sha
        """
        The SHA for a commit that serves as a restore point.

        By default, this is defined as the SHA of the checked out commit
        at the time that the `ProjectRepo` is instantiated.
        """

        if commit_sha is not None:
            self.git.checkout(commit_sha)

        self._last_metadata_commit: str = ""

    @property
    def commit_sha(self) -> str:  # noqa: D102
        return self.commit().hexsha

    @property
    def metadata_args(self) -> MetadataArgs:  # noqa: D102
        return MetadataArgs(
            self.remote_url,
            self.commit_sha,
            self.coq_version,
            self.ocaml_version)

    @property
    def name(self) -> str:  # noqa: D102
        # get last non-empty segment of URL
        return pathlib.Path(self.remote_url).stem

    @property
    def path(self) -> os.PathLike:  # noqa: D102
        return self.working_dir

    @property
    def remote_url(self) -> str:  # noqa: D102
        return self.remote().url

    @property
    def short_sha(self) -> str:
        """
        Get an abbreviated commit SHA.
        """
        return self.commit_sha[: 8]

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
        if self.current_commit_name is not None:
            warnings.warn(
                "Querying files of a non-checked out commit is deprecated",
                DeprecationWarning)
        self.git.checkout(self.current_commit_name)
        return super()._traverse_file_tree()

    def get_file(
            self,
            filename: os.PathLike,
            commit_name: Optional[str] = None) -> CoqDocument:
        """
        Return a specific Coq source file from a specific commit.

        This function may change the git repo HEAD on disk.

        Parameters
        ----------
        filename : os.PathLike
            The path to a file within the project.
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
        if commit_name is not None:
            warnings.warn(
                "Querying files of a non-checked out commit is deprecated",
                DeprecationWarning)
            self.git.checkout(commit_name)
        return super().get_file(filename)

    def get_file_list(
            self,
            relative: bool = False,
            dependency_order: bool = False,
            commit_name: Optional[str] = None) -> List[str]:
        """
        Return a list of all Coq files associated with this project.

        Parameters
        ----------
        relative : bool, optional
            Whether to return absolute file paths or paths relative to
            the root of the project, by default False.
        dependency_order : bool, optional
            Whether to return the files in dependency order or not, by
            default False.
            Dependency order means that if one file ``foo`` depends
            upon another file ``bar``, then ``bar`` will appear
            before ``foo`` in the returned list.
            If False, then the files are sorted lexicographically.
        commit_name : str or None, optional
            A commit hash, branch name, or tag name from which to get
            the file list. This is HEAD by default.

        Returns
        -------
        List[str]
            The list of absolute (or `relative`) paths to all Coq files
            in the project sorted according to `dependency_order`, not
            including those ignored by `ignore_path_regex`.
        """
        if commit_name is not None:
            warnings.warn(
                "Querying files of a non-checked out commit is deprecated",
                DeprecationWarning)
            return self.filter_files(
                self.commit(commit_name).tree.traverse(),
                relative,
                dependency_order)
        else:
            return super().get_file_list(relative, dependency_order)

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
