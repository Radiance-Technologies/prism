"""
Module for storing cache extraction functions.
"""
import re
from typing import Callable, Iterable, List, Optional, Tuple

from prism.data.build_cache import (
    CoqProjectBuildCache,
    ProjectBuildEnvironment,
    ProjectBuildResult,
    ProjectCommitData,
    ProofSentence,
    VernacCommandData,
    VernacDict,
)
from prism.interface.coq.goals import Goals
from prism.interface.coq.serapi import SerAPI
from prism.language.heuristic.parser import CoqSentence
from prism.language.heuristic.util import ParserUtils
from prism.project.base import SEM, Project
from prism.project.exception import ProjectBuildError
from prism.project.repo import ProjectRepo
from prism.util.radpytools import unzip
from prism.util.radpytools.os import pushd
from prism.util.swim import SwitchManager

from ..language.gallina.analyze import SexpAnalyzer


def _extract_vernac_commands(
        sentences: Iterable[CoqSentence],
        serapi_options: Optional[str] = None) -> List[VernacCommandData]:
    file_commands: List[VernacCommandData] = []
    proof_stack: List[List[Tuple[CoqSentence,
                                 Goals,
                                 Optional[str],
                                 Optional[str]]]] = []
    # """
    # A partitioned list of sentences that occur at the beginning or
    # in the middle of a proof each paired with the goals that
    # result after the sentence is executed and the type and the
    # identifier of the command.
    # The beginning of each partition is a Vernacular command that
    # is not Ltac-related.
    # """
    with SerAPI(serapi_options) as serapi:
        for sentence in sentences:
            location = sentence.location
            sentence = sentence.text
            _, feedback, sexp = serapi.execute(sentence, True)
            sentence.ast = sexp
            ids = serapi.parse_new_identifiers(feedback)
            if ids:
                identifier = ids[0]
            else:
                identifier = None
            if SexpAnalyzer.is_ltac(sexp):
                assert proof_stack and proof_stack[-1]
                proof_stack[-1].extend((sentence, serapi.query_goals(), None))
                if identifier is not None:
                    # a proof has concluded
                    # pop proof stack until we reach the lemma
                    lemma = None
                    for i in range(len(proof_stack) - 1, -1, -1):
                        (lemma,
                         goal,
                         command_type,
                         identifier_) = proof_stack[i][0]
                        if re.search(f" {identifier} ", lemma) is not None:
                            # The newly defined term appears in the
                            # candidate lemma,
                            # which has an identifiable type
                            assert command_type is not None
                            # but not an identifier returned in feedback
                            assert identifier_ is None
                            break
                    # Get the partitions corresponding to the lemma
                    proof = proof_stack[i :]
                    # Pop them from the stack of unresolved proof terms
                    proof_stack = proof_stack[: i]
                    # Record vernacular commands that were in the middle
                    # of the proof.
                    # They will appear before the lemma in the final
                    # list; we also unfold nested proofs in this way.
                    commands = [part[0] for part in proof[1 :]]
                    for other_command in commands:
                        file_commands.append(
                            VernacCommandData(
                                other_command[3],
                                other_command[2],
                                None,
                                other_command[0].text,
                                other_command[0].ast,
                                other_command[0].location))
                    # Aggregate the proof components
                    tactics = sum([part[1 :] for part in proof], start=[])
                    tactics, goals, _, _ = unzip(proof)
                    # Get goals of first tactic
                    goals = [goal]
                    # Pop post-goals of Qed
                    goals.pop()
                    # Combine all goals
                    goals.extend(goals)
                    # Partition by obligations, if any
                    proof = []
                    for tactic, goal in zip(tactics, goals):
                        tactic: CoqSentence
                        sentence = tactic.text
                        tactic_sans_control = ParserUtils.strip_control(
                            sentence)
                        tactic_sans_attributes = ParserUtils.strip_attributes(
                            tactic_sans_control)
                        if (not proof or ParserUtils.is_obligation_starter(
                                tactic_sans_attributes)):
                            proof.append([])
                        proof[-1].append(
                            ProofSentence(sentence,
                                          tactic.ast,
                                          goal))
                    # Record the lemma
                    file_commands.append(
                        VernacCommandData(
                            identifier,
                            command_type,
                            None,
                            lemma.text,
                            lemma.ast,
                            lemma.location,
                            proof))
            else:
                # NOTE: Identification of command type and
                # identifier could be improved using AST with
                # Coq-version-dependent logic. However, the
                # command type would no longer be human-readable
                # but the name of an internal Coq type
                # constructor, namely a variant of vernac_expr
                command_type, _ = ParserUtils.extract_identifier(sentence.text)
                if serapi.is_in_proof_mode:
                    # Not Ltac but in proof mode.
                    # Might be a lemma.
                    proof_stack.append(
                        [
                            (
                                sentence,
                                serapi.query_goals(),
                                command_type,
                                identifier)
                        ])
                else:
                    file_commands.append(
                        VernacCommandData(
                            identifier,
                            command_type,
                            None,
                            sentence,
                            sexp,
                            location))
    return file_commands


def extract_vernac_commands(
        project: ProjectRepo,
        serapi_options: Optional[str] = None) -> VernacDict:
    """
    Compile vernac commands from a project into a dict.

    Parameters
    ----------
    project : ProjectRepo
        The project from which to extract the vernac commands
    serapi_options : Optional[str], optional
        Arguments with which to initialize `sertop`, namely IQR flags.

    See Also
    --------
    prism.project.iqr : For more information about IQR flags.
    """
    if serapi_options is None:
        serapi_options = project.serapi_options
    command_data = {}
    with pushd(project.dir_abspath):
        for filename in project.get_file_list():
            command_data[filename] = _extract_vernac_commands(
                project.get_sentences(
                    filename,
                    SEM.HEURISTIC,
                    return_locations=True,
                    glom_proofs=False))
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
    dependency_formula = project.get_dependency_formula(coq_version)
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
