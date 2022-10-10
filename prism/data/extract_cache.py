"""
Module for storing cache extraction functions.
"""
import calendar
import multiprocessing as mp
import os
import re
import warnings
from datetime import datetime
from functools import partial
from logging import warn
from multiprocessing import Pool
from pathlib import Path
from typing import (
    Callable,
    Dict,
    Generator,
    Iterable,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

import tqdm
from seutil import io

from prism.data.build_cache import (
    CommandType,
    CoqProjectBuildCacheClient,
    CoqProjectBuildCacheServer,
    ProjectBuildEnvironment,
    ProjectBuildResult,
    ProjectCommitData,
    Proof,
    ProofSentence,
    VernacCommandData,
    VernacDict,
    VernacSentence,
    create_cpbcs_qs,
)
from prism.data.commit_map import Except, ProjectCommitUpdateMapper
from prism.data.util import get_project_func
from prism.interface.coq.goals import Goals
from prism.interface.coq.re_patterns import OBLIGATION_ID_PATTERN
from prism.interface.coq.serapi import SerAPI
from prism.language.heuristic.parser import CoqSentence
from prism.language.sexp import SexpParser
from prism.project.base import SEM, Project
from prism.project.exception import ProjectBuildError
from prism.project.metadata.storage import MetadataStorage
from prism.project.repo import ChangedCoqCommitIterator, ProjectRepo
from prism.util.opam.version import Version
from prism.util.radpytools import unzip
from prism.util.radpytools.os import pushd
from prism.util.swim import SwitchManager

from ..language.gallina.analyze import SexpAnalyzer

SentenceState = Tuple[CoqSentence, Optional[Goals], CommandType]
ProofSentenceState = Tuple[CoqSentence, Goals, CommandType]
ProofBlock = List[ProofSentenceState]


def _process_proof_block(block: ProofBlock) -> Proof:
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
        return []
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
                      SentenceState],
    partial_proof_stacks: Dict[str,
                               ProofBlock],
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
    conjectures : Dict[str, SentenceState]
        A map from conjecture IDs to their statements.
        This map will be modified in-place.
    partial_proof_stacks : Dict[str, ProofBlock]
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
        # uniquify but keep original order
        ids = dict.fromkeys(ids)
        # ensure conjecture ID is last
        ids.pop(finished_proof_id, None)
        ids[finished_proof_id] = None
        return VernacCommandData(
            list(ids),
            None,
            lemma,
            [p for p in proofs if p])
    else:
        return None


def _start_proof_block(
        sentence: SentenceState,
        post_proof_id: str,
        conjectures: Dict[str,
                          SentenceState],
        partial_proof_stacks: Dict[str,
                                   ProofBlock],
        obligation_map: Dict[str,
                             str],
        programs: List[str]) -> None:
    """
    Start accumulation of a new proof block.

    Parameters
    ----------
    sentence : SentenceState
        The sentence that instigated the proof.
    post_proof_id : str
        The conjecture or obligation ID to which the proof corresponds.
    conjectures : Dict[str, SentenceState]
        A map from conjecture IDs to their statements.
        This map will be modified in-place.
    partial_proof_stacks : Dict[str, ProofBlock]
        A map from conjecture/obligation IDs to partially accumulated
        proofs.
        This map will be modified in-place.
    obligation_map : Dict[str, str]
        A map from obligation IDs to conjecture IDs.
    programs : List[SentenceState]
        A list of unfinished programs begun prior to the `sentence`.
    """
    assert post_proof_id not in partial_proof_stacks
    command_type = sentence[2]
    if command_type == "Obligations":
        # Obligations get accumulated separately, but we
        # need to know to which lemma (program) they ultimately
        # correspond.
        program_id = OBLIGATION_ID_PATTERN.match(
            post_proof_id).groupdict()['proof_id']
        obligation_map[post_proof_id] = program_id
        proof_stack = partial_proof_stacks.setdefault(post_proof_id, [])
        # assert that the proof has goals
        assert sentence[1] is not None
        proof_stack.append(sentence)
        if program_id not in conjectures:
            # Programs unfortunately do not open proof
            # mode until an obligation's proof has been
            # started.
            # Consequently, we cannot rely upon
            # get_conjecture_id to catch the ID
            # of the program.
            for i, program in enumerate(reversed(programs)):
                if program_id in program[0].text:
                    conjectures[program_id] = program
                    programs.pop(len(programs) - i - 1)
                    break
            assert program_id in conjectures
    else:
        assert post_proof_id not in conjectures
        conjectures[post_proof_id] = (sentence)
        partial_proof_stacks[post_proof_id] = []


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
    The accuracy of this extraction depends upon a few assumptions:

    * No lemma emits an identifier before it is defined (i.e., before it
      is proved).
      Neither a verbose info message nor ``Print All.`` command should
      indicate the lemma (or program, or other conjecture) is defined
      before its proof(s) are complete.
    * No plugins define their own ``Obligation`` equivalents (i.e., no
      plugins define multi-block proofs).
      If any plugin does so, then each "obligation" is expected to be
      extracted as an unrelated command.
    * No command can both end one proof and start another (this should
      be true based on the mutually exclusive ``VtStartProof`` and
      ``VtQed`` Vernacular classes in
      https://github.com/coq/coq/blob/master/vernac/vernacextend.mli).
    * No conjecture fails to enter proof mode after its initial
      sentence is executed.
      The only known exceptions to this rule comprise ``Program``s,
      which do not enter proof mode until their first ``Obligation``'s
      proof is begun.
      If a plugin violates this rule, then the conjecture may be
      extracted as an unidentified command.
      However, an error may also be raised as the situation is untested.
    * The conjecture IDs returned by ``Show Conjectures.`` are ordered
      such that the conjecture actively being proved is listed first.
    """
    file_commands: List[VernacCommandData] = []
    programs: List[SentenceState] = []
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
    pre_goals = Goals()
    post_proof_id = None
    post_goals = Goals()
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
                    if pre_proof_id in partial_proof_stacks:
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
                        continue
                    else:
                        # That's not supposed to happen...
                        if OBLIGATION_ID_PATTERN.match(
                                pre_proof_id) is not None:
                            extra = "Is there an extra 'Next Obligation.'?"
                        else:
                            extra = ""
                        warnings.warn(
                            f"Anomaly detected. '{pre_proof_id}' is an open "
                            f"conjecture but is also already defined. {extra}")
                if post_proof_id not in partial_proof_stacks:
                    # We are starting a new proof (or obligation).
                    _start_proof_block(
                        (sentence,
                         pre_goals,
                         command_type),
                        post_proof_id,
                        conjectures,
                        partial_proof_stacks,
                        obligation_map,
                        programs)
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
                        list(ids),
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
        file_list = project.get_file_list()
        pbar = tqdm.tqdm(
            file_list,
            total=len(file_list),
            desc="extract_vernac_commands")
        for filename in pbar:
            # Verify that accompanying vo file exists first
            pbar.set_description(f"extract_vernac_commands: {filename}")
            path = Path(filename)
            vo = path.parent / (path.stem + ".vo")
            if not os.path.exists(vo):
                warn(
                    f"Skipped extraction for file {filename}. "
                    "No .vo file found.")
                continue
            command_data[filename] = _extract_vernac_commands(
                project.get_sentences(
                    filename,
                    SEM.HEURISTIC,
                    return_locations=True,
                    glom_proofs=False),
                serapi_options=project.serapi_options)
    return command_data


def extract_cache(
        build_cache_client: CoqProjectBuildCacheClient,
        switch_manager: SwitchManager,
        project: ProjectRepo,
        commit_sha: str,
        process_project: Callable[[Project],
                                  VernacDict],
        coq_version: Optional[str] = None,
        recache: Optional[Callable[
            [CoqProjectBuildCacheServer,
             ProjectRepo,
             str,
             str],
            bool]] = None,
        block: bool = False) -> None:
    r"""
    Extract data from project commit and insert into `build_cache`.

    The cache is implemented as a file-and-directory-based
    repository structure (`CoqProjectBuildCache`) that provides
    storage of artifacts and concurrent access for parallel
    processes through the operating system's own file system.
    Directories identify projects and commits with a separate cache
    file per build environment (i.e., Coq version). The presence or
    absence of a cache file within the structure indicates whether
    the commit has been cached yet. The cache files themselves
    contain two key pieces of information (reflected in
    `ProjectCommitData`): the metadata for the commit and a map from
    Coq file paths in the project to sets of per-sentence build
    artifacts (represented by `VernacCommandData`).

    This function does not return any cache extracted. Instead, it
    modifies on-disk build cache by inserting any previously unseen
    cache artifacts.

    Parameters
    ----------
    build_cache_client : CoqProjectBuildCacheClient
        The client that can insert the build artifacts into the on-disk
        build cache.
    switch_manager : SwitchManager
        A source of switches in which to process the project.
    project : ProjectRepo
        The project from which to extract data.
    commit_sha : str
        The commit whose data should be extracted.
    process_project : Callable[[Project], VernacDict]
        Function that provides fallback vernacular command
        extraction for projects that do not build.
    coq_version : str or None, optional
        The version of Coq in which to build the project, by default
        None.
    recache : Callable[[CoqProjectBuildCache, ProjectRepo, str, \
                    str], bool]
            or None, optional
        A function that for an existing entry in the cache returns
        whether it should be reprocessed or not.
    block : bool, optional
        Whether to use blocking cache writes, by default False

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
         coq_version) not in build_cache_client
            or (recache is not None and recache(build_cache_client,
                                                project,
                                                commit_sha,
                                                coq_version))):
        extract_cache_new(
            build_cache_client,
            switch_manager,
            project,
            commit_sha,
            process_project,
            coq_version,
            block)


def extract_cache_new(
        build_cache_client: CoqProjectBuildCacheClient,
        switch_manager: SwitchManager,
        project: ProjectRepo,
        commit_sha: str,
        process_project: Callable[[Project],
                                  VernacDict],
        coq_version: str,
        block: bool):
    """
    Extract a new cache and insert it into the build cache.

    Parameters
    ----------
    build_cache_client : CoqProjectBuildCacheClient
        The client that can communicate the build cache to be written to
        the build cache server
    switch_manager : SwitchManager
        A source of switches in which to process the project.
    project : ProjectRepo
        The project from which to extract data.
    commit_sha : str
        The commit whose data should be extracted.
    process_project : Callable[[Project], VernacDict]
        Function that provides fallback vernacular command
        extraction for projects that do not build.
    coq_version : str or None, optional
        The version of Coq in which to build the project, by default
        None.
    block : bool
        Whether to use blocking cache writes
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
    build_cache_client.insert(data, block)
    # release the switch
    switch_manager.release_switch(project.opam_switch)
    project.opam_switch = original_switch


def cache_extract_commit_iterator(
        project: ProjectRepo,
        starting_commit_sha: str) -> Generator[str,
                                               None,
                                               None]:
    """
    Provide default commit iterator for cache extraction.
    """
    iterator = ChangedCoqCommitIterator(project, starting_commit_sha)
    for item in iterator:
        # Define the minimum date; convert it to seconds since epoch
        limit_date = datetime(2019, 1, 1, 0, 0, 0)
        limit_epoch = calendar.timegm(limit_date.timetuple())
        # committed_date is in seconds since epoch
        if item.committed_date and item.committed_date >= limit_epoch:
            yield item.hexsha


class CacheExtractor:
    """
    Class for managing a broad Coq project cache extraction process.
    """

    _avail_cache_kwargs = ["fmt_ext"]
    _avail_mds_kwargs = ["fmt"]

    def __init__(
            self,
            cache_dir: str,
            metadata_storage_file: str,
            swim: SwitchManager,
            default_commits_path: str,
            commit_iterator_factory: Callable[[ProjectRepo,
                                               str],
                                              Iterator[str]],
            coq_version_iterator: Optional[Callable[[Project,
                                                     str],
                                                    Iterable[Union[
                                                        str,
                                                        Version]]]] = None,
            process_project: Optional[Callable[[ProjectRepo],
                                               VernacDict]] = None,
            **kwargs):
        self.cache_kwargs = {
            k: v for k,
            v in kwargs.items() if k in self._avail_cache_kwargs
        }
        """
        Keyword arguments for constructing the project cache build
        server
        """
        mds_kwargs = {
            k: v for k,
            v in kwargs.items() if k in self._avail_mds_kwargs
        }
        """
        Keyword arguments for constructing the metadata storage
        """
        self.cache_dir = cache_dir
        """
        Directory the cache will be read from and written to
        """
        self.swim = swim
        """
        The switch manager used for extraction
        """
        self.md_storage = MetadataStorage.load(
            metadata_storage_file,
            **mds_kwargs)
        """
        The project metadata storage object
        """
        self.md_storage_file = metadata_storage_file
        """
        The project metadata storage file
        """
        self.commit_iterator_factory = commit_iterator_factory
        """
        The factory function that produces a commit iterator given a
        project and a starting commmit SHA
        """
        self.default_commits_path = default_commits_path
        """
        Path to a file containing default commits for each project.
        """
        self.default_commits: Dict[str,
                                   List[str]] = io.load(
                                       self.default_commits_path,
                                       clz=dict)
        """
        The default commits for each project.
        """

        if coq_version_iterator is None:
            coq_version_iterator = self._default_coq_version_iterator
        self.coq_version_iterator = coq_version_iterator
        """
        An iterator over coq versions
        """

        if process_project is None:
            process_project = self._default_process_project
        self.process_project = process_project
        """
        Function to process commits for cache extraction if they do not
        build
        """

    @staticmethod
    def _commit_iterator_func(
        project: ProjectRepo,
        default_commits: Dict[str,
                              List[str]],
        commit_iterator_factory: Callable[[ProjectRepo,
                                           str],
                                          Iterator[str]]
    ) -> Iterator[str]:
        # Just in case the local repo is out of date
        for remote in project.remotes:
            remote.fetch()
        try:
            starting_commit_sha = default_commits[
                project.metadata.project_name][0]
        except IndexError:
            # There's at least one project in the default commits file
            # without a default commit; skip that one and any others
            # like it.
            return []
        return commit_iterator_factory(project, starting_commit_sha)

    def get_commit_iterator_func(
            self) -> Callable[[ProjectRepo],
                              Iterator[str]]:
        """
        Return a commit iterator function.

        Returns
        -------
        Callable[[ProjectRepo], Iterator[str]]
            The chosen commit iterator function
        """
        return partial(
            CacheExtractor._commit_iterator_func,
            default_commits=self.default_commits,
            commit_iterator_factory=self.commit_iterator_factory)

    @staticmethod
    def extract_cache_func(
        project: ProjectRepo,
        commit_sha: str,
        _result: None,
        build_cache_client_map: Dict[str,
                                     CoqProjectBuildCacheClient],
        switch_manager: SwitchManager,
        process_project: Callable[[Project],
                                  VernacDict],
        coq_version_iterator: Callable[[Project,
                                        str],
                                       Iterable[Union[str,
                                                      Version]]]):
        """
        Extract cache.

        Parameters
        ----------
        project : ProjectRepo
            The project to extract cache from
        commit_sha : str
            The commit to extract cache from
        _result : None
            Left empty for compatibility with `ProjectCommitMapper`
        build_cache_client_map : Dict[str, CoqProjectbuildCacheClient]
            A mapping from project name to build cache client, used to
            write extracted cache to disk
        switch_manager : SwitchManager
            A switch manager to use during extraction
        process_project : Callable[[Project], VernacDict]
            A function that does a best-effort cache extraction when the
            project does not build
        coq_version_iterator : Callable[[Project, str],
                                        Iterable[Union[str, Version]]]
            A function that returns an iterable over allowable coq
            versions
        """
        for coq_version in tqdm.tqdm(coq_version_iterator(project,
                                                          commit_sha),
                                     desc="Coq version"):
            extract_cache(
                build_cache_client_map[project.name],
                switch_manager,
                project,
                commit_sha,
                process_project,
                str(coq_version),
                CacheExtractor.recache)

    def get_extract_cache_func(
            self) -> Callable[[ProjectRepo,
                               str,
                               None],
                              None]:
        """
        Return the cache extraction function for the commit mapper.

        Returns
        -------
        Callable[[ProjectRepo, str, None], None]
            The extraction function to be mapped
        """
        return partial(
            CacheExtractor.extract_cache_func,
            build_cache_client_map=self.cache_clients,
            switch_manager=self.swim,
            process_project=self.process_project,
            coq_version_iterator=self.coq_version_iterator)

    def _default_coq_version_iterator(self, *args, **kwargs):
        return ["8.10.2"]

    def _default_process_project(self, *args, **kwargs) -> VernacDict:
        return dict()

    @staticmethod
    def recache(
            build_cache: CoqProjectBuildCacheServer,
            project: ProjectRepo,
            commit_sha: str,
            coq_version: str) -> bool:
        """
        Provide a placeholder function for now.
        """
        return False

    def run(
            self,
            root_path: str,
            log_dir: Optional[str] = None,
            updated_md_storage_file: Optional[str] = None,
            extract_nprocs: int = 8,
            force_serial: bool = False,
            n_build_workers: int = 1,
            profile: bool = False,
            project_names: Optional[List[str]] = None) -> None:
        """
        Build all projects at `root_path` and save updated metadata.

        Parameters
        ----------
        root_path : PathLike
            The root directory containing each project's directory.
            The project directories do not need to already exist.
        log_dir : str or None, optional
            Directory to store log file(s) in, by default the directory
            that the metadata storage file is loaded from
        updated_md_storage_file : str or None, optional
            File to save the updated metadata storage file to, by
            default the original file's parent directory /
            "updated_metadata.yml"
        extract_nprocs : int, optional
            Number of workers to allow for cache extraction, by default
            8
        force_serial : bool, optional
            If this argument is true, disable parallel execution all
            along the cache extraction pipeline. Useful for debugging.
            By default False.
        n_build_workers : int, optional
            The number of workers to allow per project when executing
            the `build` function, by default 1.
        profile : bool, optional
            If true, only 3 projects are used during extraction to allow
            for quicker code profiling, by default False.
        project_names : list of str or None, optional
            If a list is provided, select only projects with names on
            the list for extraction. If projects on the given list
            aren't found, a warning is given. By default None.
        """
        if log_dir is None:
            log_dir = Path(self.md_storage_file).parent
        if updated_md_storage_file is None:
            updated_md_storage_file = (
                Path(self.md_storage_file).parent / "updated_metadata.yml")
        # Generate list of projects
        projects = list(
            tqdm.tqdm(
                Pool(20).imap(
                    get_project_func(
                        root_path,
                        self.md_storage,
                        n_build_workers),
                    self.md_storage.projects),
                desc="Initializing Project instances",
                total=len(self.md_storage.projects)))
        # If we're profiling, limit the number of projects
        if profile and len(projects) > 4:
            projects = projects[: 3]
        # If a list of projects is specified, use only those projects
        if project_names is not None:
            projects = [p for p in projects if p.name in project_names]
            actual_project_set = {p.name for p in projects}
            requested_project_set = set(project_names)
            diff = requested_project_set.difference(actual_project_set)
            if diff:
                warn(
                    "The following projects were requested but were not "
                    f"found: {', '.join(diff)}")
        if force_serial:
            client_keys = None
            client_to_server_q = None
            server_to_client_q_dict = None
        else:
            client_keys = [project.name for project in projects]
            manager = mp.Manager()
            client_to_server_q, server_to_client_q_dict = create_cpbcs_qs(
                manager,
                client_keys)
        with CoqProjectBuildCacheServer(self.cache_dir,
                                        client_keys,
                                        client_to_server_q,
                                        server_to_client_q_dict,
                                        **self.cache_kwargs) as cache_server:
            if force_serial:
                self.cache_clients = {
                    project.name: cache_server for project in projects
                }
            else:
                self.cache_clients = {
                    project.name: CoqProjectBuildCacheClient(
                        cache_server.client_to_server,
                        cache_server.server_to_client_dict[project.name],
                        project.name) for project in projects
                }
            # Create commit mapper
            project_looper = ProjectCommitUpdateMapper[None](
                projects,
                self.get_commit_iterator_func(),
                self.get_extract_cache_func(),
                "Extracting cache",
                terminate_on_except=False)
            # Extract cache in parallel
            results, metadata_storage = project_looper.update_map(
                extract_nprocs,
                force_serial)
            # report errors
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
            with open(os.path.join(log_dir, "extract_cache.log"), "wt") as f:
                for p, result in results.items():
                    if isinstance(result, Except):
                        print(
                            f"{type(result.exception)} encountered in project {p}:"
                        )
                        print(result.trace)
                        f.write(
                            '\n'.join(
                                [
                                    "##########################################"
                                    "#########",
                                    f"{type(result.exception)} encountered in"
                                    f" project {p}:",
                                    result.trace
                                ]))
            # update metadata
            metadata_storage.dump(metadata_storage, updated_md_storage_file)
            print("Done")
