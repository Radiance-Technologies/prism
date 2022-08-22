"""
Module for storing cache extraction functions.
"""
from functools import reduce
from itertools import chain
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
from prism.project.metadata.version_info import version_info
from prism.project.repo import ProjectRepo
from prism.util.opam import PackageFormula
from prism.util.opam.formula import LogicalPF, LogOp
from prism.util.radpytools.os import pushd
from prism.util.swim import SwitchManager

VernacDict = Dict[str, Set[VernacCommandData]]


def get_formula_from_metadata(
        metadata: ProjectMetadata,
        coq_version: str) -> PackageFormula:
    """
    Get the dependency formula for the given metadata.

    This formula can then be used to retrieve an appropriate switch.
    """
    formula = []
    formula.append(PackageFormula.parse(f'"coq.{coq_version}"'))
    formula.append(
        PackageFormula.parse(f'"coq-serapi.{version_info.get_serapi_version}"'))
    if metadata.ocaml_version is not None:
        formula.append(
            PackageFormula.parse(f'"ocaml.{metadata.ocaml_version}"'))
    for dependency in chain(metadata.opam_dependencies,
                            metadata.coq_dependencies):
        formula.append(PackageFormula.parse(dependency))
    formula = reduce(
        lambda l,
        r: LogicalPF(l,
                     LogOp.AND,
                     r),
        formula[1 :,
                formula[0]])
    return formula


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
        file_commands: Set[VernacCommandData] = command_data.setdefault(
            filename,
            set())
        beg_char_idx = 0
        end_char_idx = 0
        with pushd(project.dir_abspath):
            sentences_enumerated = enumerate(
                CoqParser.parse_sentences(
                    filename,
                    project.serapi_options,
                    project.opam_switch))
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
    switch_manager: SwitchManager,
    project: ProjectRepo,
    commit_sha: str,
    process_project: Callable[[Project],
                              VernacDict],
    coq_version: Optional[str] = None,
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
    switch_manager : SwitchManager
        A source of switches in which to process the project.
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
            switch_manager,
            project,
            commit_sha,
            process_project,
            coq_version)


def extract_cache_new(
        build_cache: CoqProjectBuildCache,
        switch_manager: SwitchManager,
        project: ProjectRepo,
        commit_sha: str,
        process_project: Callable[[Project],
                                  VernacDict],
        coq_version: str):
    """
    Extract a new cache and insert it into the build cache.

    Parameters
    ----------
    build_cache : CoqProjectBuildCache
        The build cache in which to insert the build artifacts.
    switch_manager : SwitchManager
        A source of switches in which to process the project.
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
    """
    project.git.checkout(commit_sha)
    # get a switch
    dependency_formula = get_formula_from_metadata(
        project.metadata,
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
    metadata = project.metadata
    try:
        project.build()
    except ProjectBuildError as pbe:
        print(pbe.args)
        command_data = process_project(project)
    else:
        command_data = extract_vernac_commands(project, metadata.serapi_options)
    data = ProjectCommitData(metadata, command_data)
    build_cache.insert(data)
    # release the switch
    switch_manager.release_switch(project.opam_switch)
    project.opam_switch = original_switch
