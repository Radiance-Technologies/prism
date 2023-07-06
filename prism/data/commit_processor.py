"""
Module for implementing process_commit functions passed to `CommitMap`.
"""
import calendar
import logging
import traceback
from abc import ABC, abstractmethod
from datetime import datetime
from functools import partial
from subprocess import TimeoutExpired
from typing import Callable, Generator, Generic, Iterable, TypeVar, cast

from prism.project import ProjectRepo
from prism.project.exception import ProjectBuildError
from prism.project.repo import ChangedCoqCommitIterator
from prism.project.repo import CommitTraversalStrategy as CTS
from prism.util.swim import AutoSwitchManager, SwitchManager

T = TypeVar("T")


class CommitProcessor(ABC, Generic[T]):
    """
    Helper class for `prism.data.commit_map.ProjectCommitMapper`.

    Provides boilerplate implementation of `process_commit` functions.

    Parameters
    ----------
    checkout : bool, optional
        Checkout the commit before processing, by default True
    default_coq_version : str, optional
        Default coq version for building, by default '8.10.2'
    find_switch : bool, optional
        Find a switch that matches project dependencies,
        by default True
    infer_dependencies : bool, optional
        Force inference of project dependencies, by default True
    build : bool, optional
        Build project before processing, by default True
    raise_on_checkout_fail : bool, optional
        Raise exceptions raised while checking out project commit,
        by default True
    raise_on_build_fail : bool, optional
        Raise exceptions while building, by default True
    raise_on_infer_dependencies_fail : bool, optional
        Raise exceptions while inferring dependencies,
        by default True
    raise_on_process_fail : bool, optional
        Raise exceptions in process function,
        by default True
    raise_on_find_switch_fail : bool, optional
        Raise exceptions finding a switch, by default True
    switch_manager : SwitchManager, optional
        Switch manager used to find a matching switch,
        by default None
    commits : Dict[str, List[str]]
        Commits to process.
    """

    def __init__(
        self,
        checkout: bool = True,
        default_coq_version: str = '8.10.2',
        find_switch: bool = True,
        infer_dependencies: bool = True,
        build: bool = True,
        raise_on_checkout_fail: bool = True,
        raise_on_build_fail: bool = True,
        raise_on_infer_dependencies_fail: bool = True,
        raise_on_process_fail: bool = True,
        raise_on_find_switch_fail: bool = True,
        switch_manager: SwitchManager | None = None,
        commit_date_limit: bool = False,
        commit_march_strategy: CTS = CTS.CURLICUE_NEW,
        commits_to_start: dict[str,
                               str | None] | None = None,
        commits_to_use: dict[str,
                             list[str] | None] | None = None,
        max_num_commits: int | None = None,
    ):
        """
        Initialize commit processor.
        """
        self.checkout = checkout
        self.default_coq_version = default_coq_version
        self.find_switch = find_switch
        self.infer_dependencies = infer_dependencies
        self.build = build
        self.raise_on_checkout_fail = raise_on_checkout_fail
        self.raise_on_build_fail = raise_on_build_fail
        self.raise_on_infer_dependencies_fail = raise_on_infer_dependencies_fail
        self.raise_on_find_switch_fail = raise_on_find_switch_fail
        self.raise_on_process_fail = raise_on_process_fail
        if switch_manager is None:
            switch_manager = AutoSwitchManager()
        self.switch_manager = switch_manager
        self.commit_date_limit = commit_date_limit
        self.commit_march_strategy = commit_march_strategy
        self.commits_to_start = commits_to_start
        self.commits_to_use = commits_to_use
        self.max_num_commits = max_num_commits

    def __call__(
            self,
            project: ProjectRepo,
            commit: str,
            results: T | None) -> T:
        """
        Prepare project and switch for process_commit method.
        """
        original_switch = project.opam_switch
        try:
            if self.checkout:
                project = self._checkout(project, commit)
            if self.infer_dependencies and self.switch_manager is None:
                project = self._infer_dependencies(project)
            if self.find_switch:
                project = self._find_switch(project)
            if self.build:
                _ = self._build(project)
            output = self.process_commit(project, commit, results)
        except Exception:
            name = project.metadata.project_name
            logging.debug(
                f"Skipping process for project {name} on commit {commit}:"
                f"{traceback.format_exc()}")
            raise
        finally:
            self.switch_manager.release_switch(project.opam_switch)
            project.opam_switch = original_switch
        return output

    def _checkout(
        self,
        project: ProjectRepo,
        commit: str,
    ) -> ProjectRepo:
        """
        Build the project at the given commit.
        """
        try:
            # Make sure there aren't any changes or uncommitted files
            # left over from previous iterations, then check out the
            # current commit
            project.git.reset('--hard')
            project.git.clean('-fdx')
            project.git.checkout(commit)
        except Exception:
            if self.raise_on_checkout_fail:
                raise
        return project

    def _infer_dependencies(
        self,
        project: ProjectRepo,
    ) -> ProjectRepo:
        """
        Infer the project opam dependecies.
        """
        try:
            project.infer_opam_dependencies()
        except Exception:
            if self.raise_on_infer_dependencies_fail:
                raise
        return project

    def _find_switch(self, project: ProjectRepo) -> ProjectRepo:
        """
        Find a switch that matches project dependencies.
        """
        try:
            coq_version = project.metadata_storage.get_project_coq_versions(
                project.name,
                project.remote_url,
                project.commit_sha)
            try:
                coq_version = coq_version.pop()
            except KeyError:
                coq_version = self.default_coq_version
            logging.info(f'Choosing "coq.{coq_version}" for {project.name}')
            # get a switch
            dependency_formula = project.get_dependency_formula(
                coq_version,
                project.ocaml_version)
            project.opam_switch = self.switch_manager.get_switch(
                dependency_formula,
                variables={
                    'build': True,
                    'post': True,
                    'dev': True
                })
        except Exception:
            if self.raise_on_find_switch_fail:
                raise
        return project

    def _build(self, project: ProjectRepo) -> tuple[int, str, str] | None:
        """
        Call project build method.
        """
        try:
            return project.build()
        except ProjectBuildError as exc:
            if self.raise_on_build_fail:
                raise exc
            return exc.return_code, exc.stdout, exc.stderr
        except TimeoutExpired as exc:
            if self.raise_on_build_fail:
                raise exc
            return (
                1,
                exc.stdout.decode("utf-8") if exc.stdout is not None else '',
                exc.stderr.decode("utf-8") if exc.stderr is not None else '')
        except Exception:
            if self.raise_on_build_fail:
                raise
            return None

    def get_commit_iterator(self) -> Callable[[ProjectRepo], Iterable[str]]:
        """
        Return function that can return commits given a project.
        """
        return partial(
            CommitProcessor.commit_iterator,
            starting_commit_sha=self.commits_to_start,
            max_num_commits=self.max_num_commits,
            march_strategy=self.commit_march_strategy,
            date_limit=self.commit_date_limit,
        )

    @abstractmethod
    def process_commit(
        self,
        project: ProjectRepo,
        commit: str,
        results: T | None,
    ) -> T:
        """
        Process project commit.
        """
        ...

    @staticmethod
    def commit_iterator(
            project: ProjectRepo,
            starting_commit_sha: dict[str,
                                      str | None] | str | None = None,
            max_num_commits: int | None = None,
            march_strategy: CTS = CTS.CURLICUE_NEW,
            commits_to_use: dict[str,
                                 list[str] | None] | list[str] | None = None,
            date_limit: bool = False) -> Generator[str,
                                                   None,
                                                   None]:
        """
        Return commits for given project.

        Parameters
        ----------
        commits : Dict[str, List[str]]
            Dictionary of commits for each project name.
        project : ProjectRepo
            Specific project whose commits from `commits` to return.
        commit_limit : int, optional
            Maximum number of commits to return, by default 1

        Returns
        -------
        list of commits
            List of commits to iterate over for the given project.
        """
        if isinstance(starting_commit_sha, dict):
            starting_commit_sha = starting_commit_sha.get(project.name, None)
        starting_commit_sha = cast(str | None, starting_commit_sha)
        if isinstance(commits_to_use, dict):
            commits_to_use = commits_to_use.get(project.name, None)
        commits_to_use = cast(list[str] | None, commits_to_use)
        iterator = ChangedCoqCommitIterator(
            project,
            starting_commit_sha,
            march_strategy)
        limit_date = datetime(2019, 1, 1, 0, 0, 0)
        limit_epoch = calendar.timegm(limit_date.timetuple())
        i = 0
        for item in iterator:
            # get commit object
            item = project.commit(item)
            if commits_to_use is not None and item.hexsha not in commits_to_use:
                continue
            # Define the minimum date; convert it to seconds since epoch
            # committed_date is in seconds since epoch
            if not date_limit or (item.committed_date is not None
                                  and item.committed_date >= limit_epoch):
                i += 1
                yield item.hexsha
            if max_num_commits is not None and i >= max_num_commits:
                break
