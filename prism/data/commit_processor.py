"""
Module for implementing process_commit functions passed to `CommitMap`.
"""
import logging
import traceback
from abc import ABC, abstractmethod
from functools import partial
from typing import Callable, Dict, Iterable, List

from prism.project import ProjectRepo
from prism.util.swim import SwitchManager


class CommitProcessor(ABC):
    """
    Helper class to implement `process_commit` functions.
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
            switch_manager: SwitchManager = None,  # type: ignore
            commits: Dict[str, List[str]] = None,  # type: ignore
    ):
        """
        Initialize commit processor.

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
        commits : Dict[str, List[str]], optional
            Commits to process.
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
        self.switch_manager = switch_manager
        self.commits = commits

    def __call__(self, project: ProjectRepo, commit: str, results: None):
        """
        Prepare project and switch for process_commit method.
        """
        original_switch = project.opam_switch
        try:
            if self.checkout:
                project = self._checkout(project, commit)
            if self.infer_dependencies:
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
            if self.switch_manager is not None:
                self.switch_manager.release_switch(project.opam_switch)
            if original_switch:
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
            coq_versions = project.metadata_storage.get_project_coq_versions(
                project.name,
                project.remote_url,
                project.commit_sha)
            try:
                coq_version = coq_versions.pop()
            except KeyError:
                coq_version = self.default_coq_version
            print(f'Choosing "coq.{coq_version}" for {project.name}')
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

    def _build(self, project: ProjectRepo):
        """
        Call project build method.
        """
        try:
            return project.build()
        except Exception:
            if self.raise_on_build_fail:
                raise
            return

    def get_commit_iterator(self) -> Callable[[ProjectRepo], Iterable[str]]:
        """
        Return function that can return commits given a project.
        """
        return partial(CommitProcessor.commit_iterator, self.commits)

    @abstractmethod
    def process_commit(
        self,
        project: ProjectRepo,
        commit: str,
        results: None,
    ) -> None:
        """
        Process project commit.
        """
        ...

    @staticmethod
    def commit_iterator(
            commitmap: Dict[str,
                            List[str]],
            project: ProjectRepo,
            commit_limit: int = 1) -> List[str]:
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
        commits = commitmap.get(project.metadata.project_name, [])
        if len(commits) > commit_limit:
            commits = commits[: commit_limit]
        return commits
