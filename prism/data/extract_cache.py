"""
Module for storing cache extraction functions.
"""
from functools import reduce
from typing import Callable, List, Optional, Union

from prism.data.build_cache import (
    CoqProjectBuildCache,
    ProjectBuildEnvironment,
    ProjectBuildResult,
    ProjectCommitData,
    VernacCommandData,
    VernacDict,
)
from prism.interface.coq.serapi import SerAPI
from prism.language.heuristic.util import ParserUtils
from prism.project.base import SEM, Project
from prism.project.exception import ProjectBuildError
from prism.project.repo import ProjectRepo
from prism.util.opam import PackageFormula
from prism.util.opam.formula import LogicalPF, LogOp
from prism.util.opam.version import OCamlVersion, Version
from prism.util.radpytools.os import pushd
from prism.util.swim import SwitchManager

from ..language.gallina.analyze import SexpAnalyzer


def get_dependency_formula(
        opam_dependencies: List[str],
        ocaml_version: Optional[Union[str,
                                      Version]],
        coq_version: str) -> PackageFormula:
    """
    Get the dependency formula for the given constraints.

    This formula can then be used to retrieve an appropriate switch.
    """
    formula = []
    # Loosen restriction to matching major.minor~prerelease
    coq_version = Version.parse(coq_version)
    if isinstance(coq_version, OCamlVersion):
        coq_version = OCamlVersion(
            coq_version.major,
            coq_version.minor,
            prerelease=coq_version.prerelease)
    formula.append(PackageFormula.parse(f'"coq.{coq_version}"'))
    formula.append(PackageFormula.parse('"coq-serapi"'))
    if ocaml_version is not None:
        if not isinstance(ocaml_version, Version):
            ocaml_version = Version.parse(ocaml_version)
        ocaml_version = OCamlVersion(
            ocaml_version.major,
            ocaml_version.minor,
            prerelease=ocaml_version.prerelease)
        formula.append(PackageFormula.parse(f'"ocaml.{ocaml_version}"'))
    for dependency in opam_dependencies:
        formula.append(PackageFormula.parse(dependency))
    formula = reduce(
        lambda l,
        r: LogicalPF(l,
                     LogOp.AND,
                     r),
        formula[1 :],
        formula[0])
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
        file_commands: List[VernacCommandData] = command_data.setdefault(
            filename,
            list())
        with pushd(project.dir_abspath):
            with SerAPI(project.serapi_options) as serapi:
                for sentence in project.get_sentences(
                        filename,
                        sentence_extraction_method=SEM.HEURISTIC,
                        return_locations=True,
                        glom_proofs=False):
                    location = sentence.location
                    sentence = sentence.text
                    _, _, sexp = serapi.execute(sentence, True)
                    if SexpAnalyzer.is_ltac(sexp):
                        # This is where we would handle proofs
                        ...
                    else:
                        command_type, identifier = \
                            ParserUtils.extract_identifier(sentence)
                        file_commands.append(
                            VernacCommandData(
                                identifier,
                                command_type,
                                None,
                                sentence,
                                sexp,
                                location))
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
    dependency_formula = get_dependency_formula(
        project.opam_dependencies,  # infers dependencies as side-effect
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
    metadata = project.metadata
    try:
        build_result = project.build()
    except ProjectBuildError as pbe:
        build_result = (pbe.return_code, pbe.stdout, pbe.stderr)
        command_data = process_project(project)
    else:
        command_data = extract_vernac_commands(project, metadata.serapi_options)
    data = ProjectCommitData(
        metadata,
        command_data,
        ProjectBuildEnvironment(project.opam_switch.export()),
        ProjectBuildResult(*build_result))
    build_cache.insert(data)
    # release the switch
    switch_manager.release_switch(project.opam_switch)
    project.opam_switch = original_switch
