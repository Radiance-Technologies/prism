"""
Module for storing cache extraction functions.
"""
from typing import Callable, List, Optional

from prism.data.build_cache import (
    CoqProjectBuildCache,
    ProjectCommitData,
    VernacCommandData,
    VernacDict,
)
from prism.interface.coq.serapi import SerAPI
from prism.language.heuristic.util import ParserUtils
from prism.project.base import SEM, Project
from prism.project.exception import ProjectBuildError
from prism.project.metadata import ProjectMetadata
from prism.project.repo import ProjectRepo
from prism.util.opam import OpamAPI, OpamSwitch
from prism.util.radpytools.os import pushd

from ..language.gallina.analyze import SexpAnalyzer


def get_active_switch(
        metadata: ProjectMetadata,
        coq_version: str) -> OpamSwitch:
    """
    Pass args for use as a stub.
    """
    return OpamAPI.active_switch


def extract_vernac_commands(
        project: ProjectRepo,
        serapi_options: Optional[str] = None) -> VernacDict:
    """
    Compile vernac commands from a project into a dict.

    Parameters
    ----------
    project : ProjectRepo
        The project from which to extract the vernac commands
    """
    if serapi_options is None:
        serapi_options = project.serapi_options
    command_data = {}
    for filename in project.get_file_list():
        file_commands: List[VernacCommandData] = command_data.setdefault(
            filename,
            list())
        with pushd(project.dir_abspath):
            with SerAPI(project.serapi_options) as serapi:
                for sentence in project.extract_sentences(
                        project.get_file(filename),
                        sentence_extraction_method=SEM.HEURISTIC):
                    sexp = serapi.query_ast(sentence)
                    if SexpAnalyzer.is_vernac(sexp):
                        command_type, identifier = \
                            ParserUtils.extract_identifier(sentence)
                        file_commands.append(
                            VernacCommandData(
                                identifier,
                                command_type,
                                None,
                                sentence,
                                sexp))
                    else:
                        # This is where we would handle proofs
                        ...
    return command_data


def extract_cache(
    build_cache: CoqProjectBuildCache,
    project: ProjectRepo,
    commit_sha: str,
    process_project: Callable[[Project],
                              VernacDict],
    coq_version: Optional[str] = None,
    get_switch: Callable[[ProjectMetadata,
                          str],
                         OpamSwitch] = get_active_switch,
    recache: Optional[Callable[[CoqProjectBuildCache,
                                ProjectRepo,
                                str,
                                str],
                               bool]] = None
) -> None:
    r"""
    Extract data from a project commit and insert it into `build_cache`.

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
        The build cache in which to insert the build artifacts.
    project : ProjectRepo
        The project from which to extract data.
    commit_sha : str
        The commit whose data should be extracted.
    process_project : Callable[[Project], VernacDict]
        Function that provides fallback vernacular command extraction
        for projects that do not build.
    coq_version : str or None, optional
        The version of Coq in which to build the project, by default
        None.
    get_switch : Callable[[ProjectMetadata, str], OpamSwitch]
        A function that retrieves a switch in which to build an
        indicated project commit with a specified Coq version.
    recache : Callable[[CoqProjectBuildCache, ProjectRepo, str, str], \
                       bool]
              or None, optional
        A function that for an existing entry in the cache returns
        whether it should be reprocessed or not.

    See Also
    --------
    prism.data.build_cache.CoqProjectBuildCache
    prism.data.build_cache.ProjectCommitData
    prism.data.build_cache.VernacCommandData
    """
    if coq_version is None:
        coq_version = project.metadata.coq_version
    if ((project.name,
         commit_sha,
         coq_version) not in build_cache
            or (recache is not None and recache(build_cache,
                                                project,
                                                commit_sha,
                                                coq_version))):
        extract_cache_new(
            build_cache,
            project,
            commit_sha,
            process_project,
            coq_version,
            get_switch)


def extract_cache_new(
        build_cache: CoqProjectBuildCache,
        project: ProjectRepo,
        commit_sha: str,
        process_project: Callable[[Project],
                                  VernacDict],
        coq_version: str,
        get_switch: Callable[[ProjectMetadata,
                              str],
                             OpamSwitch]):
    """
    Extract a new cache and insert it into the build cache.

    Parameters
    ----------
    build_cache : CoqProjectBuildCache
        The build cache in which to insert the build artifacts.
    project : ProjectRepo
        The project from which to extract data.
    commit_sha : str
        The commit whose data should be extracted.
    process_project : Callable[[Project], VernacDict]
        Function that provides fallback vernacular command extraction
        for projects that do not build.
    coq_version : str or None, optional
        The version of Coq in which to build the project, by default
        None.
    get_switch : Callable[[ProjectMetadata, str], OpamSwitch]
        A function that retrieves a switch in which to build an
        indicated project commit with a specified Coq version.
    """
    project.git.checkout(commit_sha)
    metadata = project.metadata
    project.opam_switch = get_switch(metadata, coq_version)
    try:
        project.build()
    except ProjectBuildError as pbe:
        print(pbe.args)
        command_data = process_project(project)
    else:
        command_data = extract_vernac_commands(project, metadata.serapi_options)
    data = ProjectCommitData(metadata, command_data)
    build_cache.insert(data)
