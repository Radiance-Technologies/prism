"""
Module for storing cache extraction functions.
"""
from typing import Callable, Dict, Optional, Set

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

VernacDict = Dict[str, Set[VernacCommandData]]


def get_switch(metadata: ProjectMetadata, coq_version: str) -> OpamSwitch:
    """
    Pass args for use as a stub.
    """
    return OpamAPI.active_switch


def extract_vernac_commands(project: ProjectRepo) -> VernacDict:
    """
    Compile vernac commands from a project into a dict.

    Parameters
    ----------
    project : ProjectRepo
        The project from which to extract the vernac commands
    """
    command_data = {}
    for filename in project.get_file_list():
        file_commands: Set[VernacCommandData] = command_data.setdefault(
            filename,
            set())
        doc = project.get_file(filename)
        beg_char_idx = 0
        end_char_idx = 0
        sentences_enumerated = enumerate(
            project.extract_sentences(
                doc,
                sentence_extraction_method=project.sentence_extraction_method))
        for (sentence_idx, sentence) in sentences_enumerated:
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
    return command_data


def extract_cache(
        build_cache: CoqProjectBuildCache,
        project: ProjectRepo,
        commit_sha: str,
        process_project: Callable[[ProjectRepo],
                                  VernacDict],
        coq_version: Optional[str] = None) -> None:
    """
    Extract cache from project commit and insert into build_cache.

    This function does not return its results; instead, it potentially
    modifies on-disk build cache.

    Parameters
    ----------
    coq_version : str
        The version of Coq to use
    build_cache : CoqProjectBuildCache
        The build cache to insert the result into
    project : ProjectRepo
        The project to extract cache from
    process_project : Callable[[ProjectRepo], VernacDict]
        Function that provides fallback vernacular command extraction
        for projects that do not build
    commit_sha : str
        The commit to extract cache from
    """
    project.git.checkout(commit_sha)
    if coq_version is None:
        coq_version = project.metadata.coq_version
    project.opam_switch = get_switch(project.metadata, coq_version)
    if (project.name, commit_sha, coq_version) not in build_cache:
        try:
            project.build()
        except ProjectBuildError as pbe:
            print(pbe.args)
            command_data = process_project(project)
        else:
            command_data = extract_vernac_commands(project)
        data = ProjectCommitData(project.metadata, command_data)
        build_cache.insert(data)
