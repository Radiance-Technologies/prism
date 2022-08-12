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
from prism.language.gallina.parser import CoqParser
from prism.language.heuristic.util import ParserUtils
from prism.language.id import LanguageId
from prism.project.base import Project
from prism.project.exception import ProjectBuildError
from prism.project.metadata import ProjectMetadata
from prism.project.repo import ProjectRepo
from prism.util.opam import OpamAPI, OpamSwitch
from prism.util.radpytools.os import pushd

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
        beg_char_idx = 0
        end_char_idx = 0
        with pushd(project.dir_abspath):
            sentences_enumerated = enumerate(
                CoqParser.parse_sentences(filename,
                                          project.serapi_options))
        for (sentence_idx, vernac_sentence) in sentences_enumerated:
            sentence = str(vernac_sentence)
            end_char_idx += len(sentence)
            vs_lid = vernac_sentence.classify_lid()
            if (vs_lid == LanguageId.Vernac
                    or vs_lid == LanguageId.VernacMixedWithGallina):
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
            else:
                # This is where we would handle Ltac, aka proofs
                pass
            beg_char_idx = end_char_idx
    return command_data


def extract_cache(
        build_cache: CoqProjectBuildCache,
        project: ProjectRepo,
        commit_sha: str,
        process_project: Callable[[Project],
                                  VernacDict],
        coq_version: Optional[str] = None) -> None:
    """
    Extract cache from project commit and insert into build_cache.

    The cache is implemented as a file-and-directory-based repository
    structure (`CoqProjectBuildCache`) that provides storage of
    artifacts and concurrent access for parallel processes through the
    operating system's own file system. Directories identify projects
    and commits with a separate cache file per build environment (i.e.,
    Coq version). The presence or absence of a cache file within the
    structure indicates whether the commit has been cached yet. The
    cache files themselves contain two key pieces of information
    (reflected in `ProjectCommitData`): the metadata for the commit and
    a map from Coq file paths in the project to sets of per-sentence
    build artifacts (represented by `VernacCommandData`).

    This function does not return any cache extracted. Instead, it
    modifies on-disk build cache by inserting any previously unseen
    cache artifacts.

    Parameters
    ----------
    build_cache : CoqProjectBuildCache
        The build cache to insert the result into
    project : ProjectRepo
        The project to extract cache from
    commit_sha : str
        The commit to extract cache from
    process_project : Callable[[Project], VernacDict]
        Function that provides fallback vernacular command extraction
        for projects that do not build
    coq_version : str or None, optional
        The version of Coq to use, by default None

    See Also
    --------
    prism.data.build_cache.CoqProjectBuildCache
    prism.data.build_cache.ProjectCommitData
    prism.data.build_cache.VernacCommandData
    """
    if coq_version is None:
        coq_version = project.metadata.coq_version
    if (project.name, commit_sha, coq_version) not in build_cache:
        project.git.checkout(commit_sha)
        project.opam_switch = get_switch(project.metadata, coq_version)
        try:
            project.build()
        except ProjectBuildError as pbe:
            print(pbe.args)
            command_data = process_project(project)
        else:
            command_data = extract_vernac_commands(project)
        data = ProjectCommitData(project.metadata, command_data)
        build_cache.insert(data)
