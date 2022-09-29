"""
Module for storing cache extraction functions.
"""
import re
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

from prism.data.build_cache import (
    CommandType,
    CoqProjectBuildCache,
    ProjectBuildEnvironment,
    ProjectBuildResult,
    ProjectCommitData,
    Proof,
    ProofSentence,
    VernacCommandData,
    VernacDict,
    VernacSentence,
)
from prism.interface.coq.goals import Goals
from prism.interface.coq.serapi import SerAPI
from prism.language.heuristic.parser import CoqSentence
from prism.language.sexp import SexpParser
from prism.project.base import SEM, Project
from prism.project.exception import ProjectBuildError
from prism.project.repo import ProjectRepo
from prism.util.radpytools import unzip
from prism.util.radpytools.os import pushd
from prism.util.swim import SwitchManager

from ..language.gallina.analyze import SexpAnalyzer


def _process_proof_block(
        block: List[Tuple[CoqSentence,
                          Goals,
                          CommandType]]) -> Proof:
    """
    Convert a proof block into the form expected for extraction.

    Parameters
    ----------
    block : List[Tuple[CoqSentence, Goals, CommandType]]
        A list of proof steps within the block paired with goals prior
        to the proof step and Vernacular types.

    Returns
    -------
    Proof
        The compiled proof.
    """
    if not block:
        return None, None, []
    proof_steps, goals, command_types = unzip(block)
    proof = []
    for tactic, goal, command_type in zip(proof_steps, goals, command_types):
        tactic: CoqSentence
        proof.append(
            ProofSentence(
                tactic.text,
                tactic.ast,
                tactic.location,
                command_type,
                goal))
    return proof


def _conclude_proof(
    local_ids: Set[str],
    ids: List[str],
    pre_proof_id: str,
    conjectures: Dict[str,
                      Tuple[CoqSentence,
                            Optional[Goals],
                            CommandType]],
    partial_proof_stacks: Dict[str,
                               List[Tuple[CoqSentence,
                                          Goals,
                                          CommandType]]],
    obligation_map: Dict[str,
                         str],
    finished_proof_stacks: Dict[str,
                                List[Tuple[str,
                                           Proof]]]
) -> Optional[VernacCommandData]:
    r"""
    Complete accumulation of a proof/proved conjecture.

    Parameters
    ----------
    local_ids : Set[str]
        The set of identifiers introduced in the interactive session.
    ids : List[str]
        The list of identifiers introduced by the final proof command.
    pre_proof_id : str
        The ID of the proved conjecture or obligation.
    conjectures : Dict[str, Tuple[CoqSentence, \
                                  Optional[Goals], \
                                  CommandType]]
        A map from conjecture IDs to their statements.
        This map will be modified in-place.
    partial_proof_stacks : Dict[str, List[Tuple[CoqSentence, \
                                                Goals, \
                                                CommandType]]]
        A map from conjecture/obligation IDs to partially accumulated
        proofs.
        This map will be modified in-place.
    obligation_map : Dict[str, str]
        A map from obligation IDs to conjecture IDs.
    finished_proof_stacks : Dict[str, List[Tuple[str, Proof]]]
        A map from conjecture IDs to lists of concluded proof blocks
        (e.g., one block per obligation).
        This map will be modified in-place.

    Returns
    -------
    Optional[VernacCommandData]
        The compiled command data for a concluded conjecture or None if
        no conjecture was concluded (e.g., an obligation was completed
        but more work remains for the overall conjecture).
    """
    new_proofs = []
    for new_id in ids:
        # Try to cover edge cases of plugins with unusual
        # behavior that may conclude multiple
        # proofs/obligations at once.
        # Note that a new ID need not have an explicit proof
        # (for example, an automatically solved obligation).
        proof_block = _process_proof_block(partial_proof_stacks.pop(new_id, []))
        new_proofs.append((new_id, proof_block))
    finished_proof_id = obligation_map.get(pre_proof_id, pre_proof_id)
    # add to other finished obligations
    finished_stack = finished_proof_stacks.setdefault(finished_proof_id, [])
    finished_stack.extend(new_proofs)
    if finished_proof_id in local_ids:
        # A lemma has (presumably) been defined.
        # Note that a plugin may cause related proofs to
        # show up as separate entries if it defines custom
        # proof environments.
        ids, proofs = unzip(finished_proof_stacks.pop(finished_proof_id))
        lemma, pre_goals, lemma_type = conjectures.pop(finished_proof_id)
        lemma = VernacSentence(
            lemma.text,
            lemma.ast,
            lemma.location,
            lemma_type,
            pre_goals)
        ids = list(ids)
        ids.append(finished_proof_id)
        return VernacCommandData(ids, None, lemma, [p for p in proofs if p])
    else:
        return None


def _extract_vernac_commands(
        sentences: Iterable[CoqSentence],
        serapi_options: str = "") -> List[VernacCommandData]:
    """
    Compile vernac commands from a sequence of sentences.

    Parameters
    ----------
    sentences : Iterable[CoqSentence]
        A sequence of sentences derived from a document.
    serapi_options : str, optional
        Arguments with which to initialize `sertop`, namely IQR flags.

    Returns
    -------
    List[VernacCommandData]
        The compiled vernacular commands.

    See Also
    --------
    prism.project.iqr : For more information about IQR flags.

    Notes
    -----
    The accuracy of this extraction depends upon a few assumptions.
    We assume that no plugins define their own Qed equivalents.
    We assume that no command can both end one proof and start another
    (this should be true based on the mutually exclusive VtStartProof
    and VtQed Vernacular classes).
    """
    file_commands: List[VernacCommandData] = []
    programs: List[Tuple[CoqSentence, Optional[Goals], CommandType]] = []
    conjectures: Dict[str,
                      Tuple[CoqSentence,
                            Optional[Goals],
                            CommandType]] = {}
    partial_proof_stacks: Dict[str,
                               List[Tuple[CoqSentence,
                                          Goals,
                                          CommandType]]] = {}
    obligation_map: Dict[str,
                         str] = {}
    finished_proof_stacks: Dict[str,
                                List[Tuple[str,
                                           Proof]]] = {}
    # A partitioned list of sentences that occur at the beginning or
    # in the middle of a proof each paired with the goals that
    # result after the sentence is executed and the type and the
    # identifier of the command.
    # The beginning of each partition is a Vernacular command that
    # is not Ltac-related.
    local_ids = {'SerTop'}
    pre_proof_id = None
    pre_goals = None
    post_proof_id = None
    post_goals = None
    with SerAPI(serapi_options) as serapi:
        for sentence in sentences:
            # TODO: Optionally filter queries out of results (and
            # execution)
            # TODO: Handle control flags
            location = sentence.location
            text = sentence.text
            _, feedback, sexp = serapi.execute(text, return_ast=True)
            sentence.ast = SexpParser.parse(sexp)
            vernac = SexpAnalyzer.analyze_vernac(sentence.ast)
            if vernac.extend_type is None:
                command_type = vernac.vernac_type
            else:
                command_type = vernac.extend_type
            # get new ids
            ids = serapi.parse_new_identifiers(feedback)
            if ids:
                local_ids = local_ids.union(ids)
            else:
                all_local_ids = set(serapi.get_local_ids())
                # get new identifiers
                ids = all_local_ids.difference(local_ids)
                # update reference set
                local_ids = all_local_ids
            pre_proof_id = post_proof_id
            pre_goals = post_goals
            post_proof_id = serapi.get_conjecture_id()
            proof_id_changed = post_proof_id != pre_proof_id
            program_regex = re.compile("[Pp]rogram")
            is_program = any(
                program_regex.search(attr) is not None
                for attr in vernac.attributes)
            if is_program:
                # A program was declared.
                # Persist the current goals.
                # Programs do not open proof mode, so post_proof_id
                # may be None or refer to another conjecture.
                programs.append((sentence, pre_goals, command_type))
            elif proof_id_changed:
                post_goals = serapi.query_goals()
                if pre_proof_id in local_ids:
                    # a proof has concluded
                    assert pre_proof_id in partial_proof_stacks
                    partial_proof_stacks[pre_proof_id].append(
                        (sentence,
                         pre_goals,
                         command_type))
                    completed_lemma = _conclude_proof(
                        local_ids,
                        ids,
                        pre_proof_id,
                        conjectures,
                        partial_proof_stacks,
                        obligation_map,
                        finished_proof_stacks)
                    if completed_lemma is not None:
                        file_commands.append(completed_lemma)
                elif post_proof_id not in partial_proof_stacks:
                    # We are starting a new proof (or obligation).
                    # Obligations get accumulated separately, but we
                    # need to know to which lemma they ultimately
                    # correspond.
                    assert post_proof_id not in partial_proof_stacks
                    if command_type == "Obligations":
                        obligation_id_regex = re.compile(
                            r"(?P<proof_id>\w+)_obligation_\d+")
                        program_id = obligation_id_regex.match(
                            post_proof_id).groupdict()['proof_id']
                        obligation_map[post_proof_id] = program_id
                        proof_stack = partial_proof_stacks.setdefault(
                            post_proof_id,
                            [])
                        proof_stack.append((sentence, pre_goals, command_type))
                        if program_id not in conjectures:
                            # Programs unfortunately do not open proof
                            # mode until an obligation's proof has been
                            # started.
                            # Consequently, we cannot rely upon
                            # get_conjecture_id to catch the statement
                            # of the conjecture.
                            for i, program in enumerate(reversed(programs)):
                                if program_id in program[0].text:
                                    conjectures[program_id] = program
                                    programs.pop(len(programs) - i - 1)
                                    break
                            assert program_id in conjectures
                    else:
                        assert post_proof_id not in conjectures
                        conjectures[post_proof_id] = (
                            sentence,
                            pre_goals,
                            command_type)
                        partial_proof_stacks[post_proof_id] = []
                else:
                    # we are continuing a delayed proof
                    assert post_proof_id in partial_proof_stacks
                    proof_stack = partial_proof_stacks[post_proof_id]
                    proof_stack.append((sentence, pre_goals, command_type))
            elif post_proof_id is not None and not ids:
                # we are continuing an open proof
                assert post_proof_id in partial_proof_stacks
                post_goals = serapi.query_goals()
                proof_stack = partial_proof_stacks[post_proof_id]
                proof_stack.append((sentence, pre_goals, command_type))
            else:
                # We are either not in a proof
                # OR we just defined something new as a side-effect.
                # We let the previous goals persist.
                file_commands.append(
                    VernacCommandData(
                        ids,
                        None,
                        VernacSentence(
                            text,
                            sentence.ast,
                            location,
                            command_type,
                            pre_goals)))
    # assert that we have extracted all proofs
    assert not conjectures
    assert not partial_proof_stacks
    assert not finished_proof_stacks
    assert not programs
    return file_commands


def extract_vernac_commands(project: ProjectRepo) -> VernacDict:
    """
    Compile vernac commands from a project into a dict.

    Parameters
    ----------
    project : ProjectRepo
        The project from which to extract the vernac commands

    Returns
    -------
    VernacDict
        A map from file names to their extracted commands.
    """
    command_data = {}
    with pushd(project.dir_abspath):
        for filename in project.get_file_list():
            command_data[filename] = _extract_vernac_commands(
                project.get_sentences(
                    filename,
                    SEM.HEURISTIC,
                    return_locations=True,
                    glom_proofs=False),
                serapi_options=project.serapi_options)
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
        command_data = extract_vernac_commands(project)
    data = ProjectCommitData(
        metadata,
        command_data,
        ProjectBuildEnvironment(project.opam_switch.export()),
        ProjectBuildResult(*build_result))
    build_cache.insert(data)
    # release the switch
    switch_manager.release_switch(project.opam_switch)
    project.opam_switch = original_switch
