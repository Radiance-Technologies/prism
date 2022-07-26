"""
Module for storing cache extraction functions.
"""
from typing import Callable, Set


from prism.data.build_cache import (
    CoqProjectBuildCache,
    ProjectCommitData,
    VernacCommandData,
)
from prism.language.gallina.analyze import SexpInfo
from prism.language.heuristic.util import ParserUtils
from prism.project.exception import ProjectBuildError
from prism.project.metadata import ProjectMetadata
from prism.project.repo import ProjectRepo
from prism.util.opam import OpamAPI, OpamSwitch


def get_switch(metadata: ProjectMetadata) -> OpamSwitch:
    """
    Pass args for use as a stub.
    """
    return OpamAPI.active_switch


def extract_cache(
        coq_version: str,
        build_cache: CoqProjectBuildCache,
        project: ProjectRepo,
        commit_sha: str,
        process_project: Callable) -> None:
    """
    Extract cache from project commit and insert into build_cache.
    """
    project.git.checkout(commit_sha)
    project.opam_switch = get_switch(project.metadata)
    coq_version = project.metadata.coq_version
    if (project.name, commit_sha, coq_version) not in build_cache:
        try:
            command_data = {}
            for filename in project.get_file_list():
                file_commands: Set[VernacCommandData] = command_data.setdefault(
                    filename,
                    set())
                doc = project.get_file(filename)
                beg_char_idx = 0
                end_char_idx = 0
                for (sentence_idx,
                     sentence) in enumerate(project.extract_sentences(
                         doc,
                         sentence_extraction_method=project
                         .sentence_extraction_method)):
                    end_char_idx += len(sentence)
                    command_type, identifier = ParserUtils.extract_identifier(sentence)
                    file_commands.add(
                        VernacCommandData(
                            identifier,
                            command_type,
                            SexpInfo.Loc(
                                filename,
                                sentence_idx,
                                0,
                                sentence_idx,
                                0,
                                beg_char_idx,
                                end_char_idx),
                            None))
                    beg_char_idx = end_char_idx
            data = ProjectCommitData(project.metadata, command_data)
            build_cache.insert(data)
        except ProjectBuildError as pbe:
            print(pbe.args)
            process_project(project)
