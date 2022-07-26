"""
Module for storing cache extraction functions.
"""
from typing import Callable

from prism.data.build_cache import CoqProjectBuildCache, ProjectCommitData
from prism.project.exception import ProjectBuildError
from prism.project.metadata import ProjectMetadata
from prism.project.repo import ProjectRepo
from prism.util.opam import OpamAPI, OpamSwitch


def get_switch(metadata: ProjectMetadata) -> OpamSwitch:
    return OpamAPI.find_switch(metadata)


def extract_cache(
        coq_version: str,
        build_cache: CoqProjectBuildCache,
        project: ProjectRepo,
        commit_sha: str,
        process_file: Callable) -> None:
    """
    Extract cache from project commit and insert into build_cache.
    """
    project.git.checkout(commit_sha)
    project.opam_switch = get_switch(project.metadata)
    coq_version = project.metadata.coq_version
    if (project.name, commit_sha, coq_version) not in build_cache:
        try:
            project.build()
            command_data = {}
            for filename in project.get_file_list():
                command_data[filename] = process_file(project, filename)
            data = ProjectCommitData(project.metadata, command_data)
            build_cache.insert(data)
        except ProjectBuildError as pbe:
            print(pbe.args)
