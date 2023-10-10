#
# Copyright (c) 2023 Radiance Technologies, Inc.
#
# This file is part of PRISM
# (see https://github.com/orgs/Radiance-Technologies/prism).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program. If not, see
# <http://www.gnu.org/licenses/>.
#
"""
Module providing utilities related to data processing.
"""
import logging
import traceback
from functools import partial
from pathlib import Path
from typing import Callable, Dict, List

from prism.project.base import SentenceExtractionMethod
from prism.project.metadata.storage import MetadataStorage
from prism.project.repo import ProjectRepo
from prism.util.radpytools import PathLike
from prism.util.swim import SwitchManager


def get_project(
        root_path: PathLike,
        metadata_storage: MetadataStorage,
        n_build_workers: int,
        project_name: str) -> ProjectRepo:
    """
    Get the identified project's `ProjectRepo` representation.
    """
    repo_path = Path(root_path) / project_name
    return ProjectRepo(
        repo_path,
        metadata_storage,
        sentence_extraction_method=SentenceExtractionMethod.SERAPI,
        num_cores=n_build_workers)


def get_project_func(  # noqa: D103
        root_path: PathLike,
        metadata_storage: MetadataStorage,
        n_build_workers: int = 1) -> Callable[[str],
                                              ProjectRepo]:
    return partial(get_project, root_path, metadata_storage, n_build_workers)


def get_default_commit_iterator(
        default_commits: Dict[str,
                              List[str]],
        project: ProjectRepo) -> List[str]:
    """
    Get an iterator over a project's default commits.
    """
    return default_commits[project.metadata.project_name]


def get_default_commit_iterator_func(  # noqa: D103
    default_commits: Dict[str,
                          List[str]]) -> Callable[[ProjectRepo],
                                                  List[str]]:
    return partial(get_default_commit_iterator, default_commits)


# TODO: Fix this function
def build_commit(
        switch_manager: SwitchManager,
        project: ProjectRepo,
        commit: str,
        results: None) -> str:
    """
    Build the project at the given commit.
    """
    try:
        project.git.checkout(commit)
        coq_version = project.metadata_storage.get_project_coq_versions(
            project.name,
            project.remote_url,
            project.commit_sha)
        try:
            coq_version = coq_version.pop()
        except KeyError:
            coq_version = '8.10.2'
        print(f'Choosing "coq.{coq_version}" for {project.name}')
        # get a switch
        project.infer_opam_dependencies()  # force inference
        dependency_formula = project.get_dependency_formula(
            project.opam_dependencies,
            project.ocaml_version,
            coq_version)
        original_switch = project.opam_switch
        project.opam_switch = switch_manager.get_switch(
            dependency_formula,
            variables={
                'build': True,
                'post': True,
                'dev': True
            })
        # process the commit
        _ = project.build()
    except Exception:
        logging.debug(
            f"Skipping build for {project.metadata.project_name}:"
            f"{traceback.format_exc()}")
        raise
    finally:
        switch_manager.release_switch(project.opam_switch)
        project.opam_switch = original_switch
    return coq_version
