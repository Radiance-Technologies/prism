"""
Module for storing cache extraction functions.
"""
import calendar
import copy
import logging
import multiprocessing as mp
import os
import re
import traceback
import typing
import warnings
from dataclasses import InitVar, dataclass, field
from datetime import datetime
from functools import partial
from io import StringIO
from multiprocessing import Pool
from pathlib import Path
from subprocess import CalledProcessError, TimeoutExpired
from threading import BoundedSemaphore
from time import time
from typing import (
    Callable,
    Dict,
    Generator,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
)

import numba.typed
import tqdm
from seutil import io
from tqdm.contrib.concurrent import process_map

from prism.data.build_cache import (
    CommandType,
    CommentDict,
    CoqProjectBuildCache,
    CoqProjectBuildCacheClient,
    CoqProjectBuildCacheProtocol,
    CoqProjectBuildCacheServer,
    ProjectBuildEnvironment,
    ProjectBuildResult,
    ProjectCommitData,
    Proof,
    ProofSentence,
    VernacCommandData,
    VernacCommandDataList,
    VernacDict,
    VernacSentence,
)
from prism.data.commit_map import Except, ProjectCommitUpdateMapper
from prism.data.util import get_project_func
from prism.interface.coq.exception import CoqExn
from prism.interface.coq.goals import Goals, GoalsDiff
from prism.interface.coq.ident import Identifier, get_all_qualified_idents
from prism.interface.coq.re_patterns import (
    ABORT_COMMAND_PATTERN,
    IDENT_PATTERN,
    OBLIGATION_ID_PATTERN,
    SUBPROOF_ID_PATTERN,
)
from prism.interface.coq.serapi import AbstractSyntaxTree, SerAPI
from prism.language.gallina.analyze import SexpAnalyzer
from prism.language.heuristic.parser import CoqComment, CoqSentence
from prism.language.sexp.node import SexpNode
from prism.project.base import SEM, Project
from prism.project.exception import MissingMetadataError, ProjectBuildError
from prism.project.metadata.storage import MetadataStorage
from prism.project.repo import (
    ChangedCoqCommitIterator,
    CommitTraversalStrategy,
    ProjectRepo,
)
from prism.util.alignment import Alignment, align_factory
from prism.util.opam.switch import OpamSwitch
from prism.util.opam.version import OpamVersion, Version
from prism.util.radpytools import PathLike, unzip
from prism.util.radpytools.dataclasses import default_field
from prism.util.radpytools.os import pushd
from prism.util.swim import SwitchManager, UnsatisfiableConstraints

SentenceState = Tuple[CoqSentence,
                      Optional[Union[Goals,
                                     GoalsDiff]],
                      CommandType]
ProofSentenceState = Tuple[CoqSentence,
                           Optional[Union[Goals,
                                          GoalsDiff]],
                           CommandType]
ProofBlock = List[ProofSentenceState]

_program_regex = re.compile("[Pp]rogram")

_save_pattern = re.compile(rf"Save\s+(?P<ident>{IDENT_PATTERN.pattern})\s*.")

_printing_options_pattern = re.compile(r"(?:Set|Unset)\s+Printing\s+.*\.")


class ExtractVernacCommandsError(RuntimeError):
    """
    Extended RuntimeError with filename and parent properties.
    """

    def __init__(
            self,
            message: str,
            filename: str = "",
            parent_exception: Optional[Exception] = None,
            parent_stacktrace: Optional[str] = None):
        super().__init__(message)
        self.filename = filename
        self.parent = parent_exception
        self.parent_stacktrace = parent_stacktrace


serapi_id_align_ = align_factory(
    lambda x,
    y: 0. if x == y else 1.,
    # Skip cost is less than half the cost of misalignment to encourage
    # skipping.
    lambda x: 0.25,
    True)


def serapi_id_align(x: Sequence[str], y: Sequence[str]) -> Alignment:
    """
    Align two sequences of IDs produced by `SerAPI.get_local_ids`.

    Parameters
    ----------
    x : Sequence[str]
        Previous ID sequence
    y : Sequence[str]
        Current ID sequence

    Returns
    -------
    Alignment
        Aligned ID sequence
    """
    x = numba.typed.List(xi.split(".")[-1] for xi in x)
    y = numba.typed.List(yi.split(".")[-1] for yi in y)
    alignment = serapi_id_align_(x, y, False)
    return typing.cast(Alignment, alignment)


@dataclass
class CommandExtractor:
    """
    A class that extracts commands from a given Coq file.

    Notes
    -----
    The accuracy of this extraction depends upon a few assumptions:

    * No lemma emits an identifier before it is defined (i.e.,
      before it is proved).
      Neither a verbose info message nor ``Print All.`` command should
      indicate the lemma (or program, or other conjecture) is defined
      before its proof(s) are complete.
    * No plugin defines their own ``Abort`` or ``Abort All``
      equivalents, i.e., no plugin concludes a proof without emitting
      an identifier.
    * No plugins define their own ``Obligation`` equivalents (i.e.,
      no plugins define multi-block proofs).
      If any plugin does so, then each "obligation" is expected to be
      extracted as an unrelated command.
    * No command can both end one proof and start another (this
      should be true based on the mutually exclusive ``VtStartProof``
      and ``VtQed`` Vernacular classes in
    https://github.com/coq/coq/blob/master/vernac/vernacextend.mli).
    * No conjecture fails to enter proof mode after its initial
      sentence is executed.
      The only known exceptions to this rule comprise ``Program``s,
      which do not enter proof mode until their first ``Obligation``'s
      proof is begun.
      If a plugin violates this rule, then the conjecture may be
      extracted as an unidentified command.
      However, an error may also be raised as the situation is
      untested.
    * The conjecture IDs returned by ``Show Conjectures.`` are
      ordered such that the conjecture actively being proved is listed
      first.
    * If a new identifier shadows an existing one, then the defining
      command does not reference the shadowed ID. Violation of this
      assumption is possible (consider a recursive function named
      after a type that takes arguments of said type as input) but not
      expected to occur frequently as it is unlikely in the first
    place and poor practice. If it does occur, then the fully
      qualified identifiers in the cache will erroneously interpret
      the shadowed ID as its shadower (i.e., as the recursive function
      in the example above).
    * A change in the current conjecture implies that either a new
      proof has begun or the current proof has ended (but not both).
    * No plugin defines its own `Qed` or `Save` equivalents (i.e.,
      no plugin defines its own opaque proof environments) or no file
      to be extracted uses such equivalent commands to end a nested
      proof.
    """

    filename: PathLike
    """
    The name of (path to) the file being extracted, relative to the root
    of the project.
    """
    sentences: InitVar[Optional[Iterable[CoqSentence]]] = None
    """
    A sequence of sentences derived from a document.

    If provided, then the extraction occurs upon object initialization.
    Otherwise, one may initiate the extraction by calling the
    constructed object with the sentences as argument.
    """
    serapi_options: str = ""
    """
    The options given to `sertop` with which to perform extraction.
    """
    opam_switch: Optional[OpamSwitch] = None
    """
    The switch in which to execute the commands, which sets the
    version of `sertop` and controls the availability of
    external libraries.
    If None, then the default global switch is used.
    """
    logger: Optional[logging.Logger] = None
    """
    """
    use_goals_diff: bool = True
    """
    If True, make use of GoalsDiff to save space in cache files,
    by default True.
    This argument is for testing purposes only.
    """
    modpath: str = field(init=False)
    """
    The logical library name of the filename.
    """
    extracted_commands: VernacCommandDataList = default_field(
        VernacCommandDataList(),
        init=False)
    """
    The list of extracted commands.
    """
    programs: List[SentenceState] = default_field([], init=False)
    """
    The list of all unfinished programs encountered thus far in
    extraction.
    """
    conjectures: Dict[str,
                      SentenceState] = default_field({},
                                                     init=False)
    """
    A map from conjecture IDs to their statements.
    """
    partial_proof_stacks: Dict[str,
                               ProofBlock] = default_field({},
                                                           init=False)
    """
    A map from conjecture/obligation IDs to partially accumulated
    proofs.
    """
    obligation_map: Dict[str,
                         str] = default_field({},
                                              init=False)
    """
    A map from obligation IDs to conjecture IDs.
    """
    finished_proof_stacks: Dict[str,
                                List[Tuple[str,
                                           Proof]]] = default_field(
                                               {},
                                               init=False)
    """
    A map from conjecture IDs to lists of concluded proof blocks
    (e.g., one block per obligation).
    """
    expanded_ids: Dict[str,
                       str] = default_field({},
                                            init=False)
    """
    A map from unqualified or partially qualified IDs to fully
    qualified variants.
    """
    defined_lemmas: Dict[str,
                         VernacCommandData] = default_field({},
                                                            init=False)
    """
    A map from conjecture/obligation IDs to the corresponding cache
    data structure.
    """
    local_ids: List[str] = default_field(['SerTop'], init=False)
    """
    The set of identifiers introduced in the interactive session.
    """
    pre_proof_id: Optional[str] = default_field(None, init=False)
    """
    The ID of the active open conjecture, if any, before execution of
    the most recent command.
    """
    pre_goals: Optional[Goals] = default_field(None, init=False)
    """
    The open goals, if any, before execution of the most recent command.
    """
    post_proof_id: Optional[str] = default_field(None, init=False)
    """
    The ID of the active open conjecture, if any, after execution of the
    most recent command.
    """
    post_goals: Optional[Goals] = default_field(None, init=False)
    """
    The open goals, if any, after execution of the most recent command.
    """

    def __post_init__(self, sentences: Optional[Iterable[CoqSentence]]):
        """
        Initialize the `modpath`.
        """
        self.modpath = Project.get_local_modpath(
            self.filename,
            self.serapi_options)
        if sentences is not None:
            self(sentences)

    def __call__(
            self,
            sentences: Iterable[CoqSentence]) -> VernacCommandDataList:
        """
        Perform the extraction.
        """
        return self._extract_vernac_commands(sentences)

    def _conclude_proof(
        self,
        ids: List[str],
        is_proof_aborted: bool,
        get_identifiers: Callable[[str],
                                  List[Identifier]],
        feedback: List[str],
    ) -> Optional[VernacCommandData]:
        r"""
        Complete accumulation of a proof/proved conjecture.

        Parameters
        ----------
        ids : List[str]
            The list of identifiers introduced by the final proof
            command.
        is_aborted : bool
            Whether the proof has been aborted or not.
        get_identifiers : Callable[[str], List[Identifier]]
            A function that accepts a serialized AST and returns a list
            of fully qualified identifiers in the order of their
            appearance in the AST.
        feedback : List[str]
            Feedback from executing the `sentence`.

        Returns
        -------
        Optional[VernacCommandData]
            The compiled command data for a concluded conjecture or None
            if no conjecture was concluded (e.g., an obligation was
            completed but more work remains for the overall conjecture).
        """
        assert self.pre_proof_id is not None, \
            "pre_proof_id must not be None"
        new_proofs = []
        for new_id in set(ids).union({self.pre_proof_id}):
            # Try to cover edge cases of plugins with unusual
            # behavior that may conclude multiple
            # proofs/obligations at once.
            # Note that a new ID need not have an explicit proof
            # (for example, an automatically solved obligation).
            proof_block = self._process_proof_block(
                self.partial_proof_stacks.pop(new_id,
                                              []),
                get_identifiers,
                feedback)
            new_proofs.append((new_id, proof_block))
        finished_proof_id = self.obligation_map.get(
            self.pre_proof_id,
            self.pre_proof_id)
        # add to other finished obligations
        finished_stack = self.finished_proof_stacks.setdefault(
            finished_proof_id,
            [])
        finished_stack.extend(new_proofs)
        is_obligation = self.pre_proof_id in self.obligation_map
        is_program_completed = finished_proof_id in self.local_ids
        is_conjecture_completed = not is_obligation or is_program_completed
        if is_conjecture_completed or (not is_obligation and is_proof_aborted):
            # A lemma has (presumably) been defined or aborted.
            # Note that a plugin may cause related proofs to
            # show up as separate entries if it defines custom
            # proof environments.
            (ids,
             proofs) = typing.cast(
                 Tuple[List[str],
                       List[Proof]],
                 unzip(self.finished_proof_stacks.pop(finished_proof_id)))
            (lemma,
             pre_goals_or_diff,
             lemma_type) = self.conjectures.pop(finished_proof_id)
            assert lemma.ast is not None, \
                "The lemma must have an AST"
            assert lemma.location is not None, \
                "The lemma should have a location"
            lemma = VernacSentence(
                lemma.text,
                lemma.ast,
                lemma.identifiers,  # type: ignore
                lemma.location,
                lemma_type,
                pre_goals_or_diff,
                get_identifiers,
                feedback)
            # uniquify but keep original order
            uids = dict.fromkeys(ids)
            # ensure conjecture ID is last
            uids.pop(finished_proof_id, None)
            uids[finished_proof_id] = None
            lemma = VernacCommandData(
                list(uids),
                None,
                lemma,
                [p for p in proofs if p])
            for ident in uids:
                self.defined_lemmas[ident] = lemma
            return lemma
        else:
            return None

    def _execute_cmd(self,
                     serapi: SerAPI,
                     cmd: str) -> Tuple[List[str],
                                        AbstractSyntaxTree]:
        """
        Execute a command in the given SerAPI session.

        Parameters
        ----------
        serapi : SerAPI
            An active `sertop` session.
        cmd : str
            A command to be executed.

        Returns
        -------
        feedback : List[str]
            Verbose feedback from executing the command.
        AbstractSyntaxTree
            The parsed AST of the given command.

        Raises
        ------
        CoqExn
            If an error occurs when attempting to execute the command.
        """
        # We cannot Print All in Coq 8.15.2 in certain situations
        # without getting a "Cannot access delayed opaque proof"
        # error.
        # The culprits (so far) appear to be opaque proofs (Qed or
        # Save).
        # We execute them normally first to verify that they are
        # valid, then we replace the Qed with an Admitted statement,
        # which does not prevent us from printing the environment.
        admit_qed = (
            OpamVersion.less_than("8.14.1",
                                  serapi.serapi_version) and cmd == "Qed.")
        saved_ident_match = _save_pattern.match(cmd)
        define_saved = (
            OpamVersion.less_than("8.14.1",
                                  serapi.serapi_version)
            and saved_ident_match is not None)
        if admit_qed or define_saved:
            serapi.push()
        if _printing_options_pattern.match(cmd):
            # Do not allow alteration of printing options.
            # Changing them can break extraction.
            feedback: List[str] = []
            sexp = serapi.query_ast(cmd)
        else:
            (_,
             feedback,
             sexp) = typing.cast(
                 Tuple[List[SexpNode],
                       List[str],
                       AbstractSyntaxTree],
                 serapi.execute(cmd,
                                return_ast=True,
                                verbose=True))
        if admit_qed:
            serapi.pop()
            if serapi.try_execute("Admitted.",
                                  return_ast=False,
                                  verbose=False) is None:
                # Admitted is not supported for Derived
                # https://github.com/coq/coq/issues/16856.
                # Fall back to Qed in that case (or any other
                # unanticipated error).
                serapi.execute(cmd, return_ast=False, verbose=False)
        elif define_saved:
            serapi.pop()
            assert saved_ident_match is not None
            saved_ident = saved_ident_match['ident']
            serapi.push()
            if (serapi.try_execute(f"Defined {saved_ident}.",
                                   return_ast=False,
                                   verbose=False) is None
                    or serapi.try_execute(f"Opaque {saved_ident}.",
                                          return_ast=False,
                                          verbose=False) is None):
                serapi.pop()
                serapi.execute(cmd, return_ast=False, verbose=False)
            else:
                serapi.pull()
        return feedback, sexp

    def _extract_vernac_commands(
            self,
            sentences: Iterable[CoqSentence]) -> VernacCommandDataList:
        """
        Compile Vernacular commands from a sequence of sentences.

        Parameters
        ----------
        sentences : Iterable[CoqSentence]
            A sequence of sentences derived from a document.

        Returns
        -------
        VernacCommandDataList
            The compiled vernacular commands.

        See Also
        --------
        prism.project.iqr : For more information about IQR flags.
        """
        with SerAPI(self.serapi_options,
                    opam_switch=self.opam_switch) as serapi:
            get_identifiers = typing.cast(
                Callable[[str],
                         List[Identifier]],
                partial(
                    get_all_qualified_idents,
                    serapi,
                    self.modpath,
                    ordered=True,
                    id_cache=self.expanded_ids))
            for sentence in sentences:
                # TODO: Optionally filter queries out of results (and
                # execution)
                try:
                    self._extract_vernac_sentence(
                        serapi,
                        get_identifiers,
                        sentence)
                except CoqExn as e:
                    raise CoqExn(
                        e.msg,
                        e.full_sexp,
                        sentence.location,
                        sentence.text) from e
                except Exception as e:
                    # slight abuse of CoqExn
                    raise CoqExn(
                        str(e),
                        "",
                        sentence.location,
                        sentence.text) from e
        # assert that we have extracted all proofs
        assert not self.conjectures
        assert not self.partial_proof_stacks
        assert not self.finished_proof_stacks
        assert not self.programs
        return self.extracted_commands

    def _extract_vernac_sentence(
            self,
            serapi: SerAPI,
            get_identifiers: Callable[[str],
                                      List[Identifier]],
            sentence: CoqSentence) -> None:
        """
        Extract a single sentence.

        Parameters
        ----------
        serapi : SerAPI
            The established interactive SerAPI session.
        get_identifiers : Callable[[str], List[Identifier]]
            A function that takes a serialized AST and returns a list of
            qualified identifiers in the order of their appearance.
        sentence : CoqSentence
            The sentence to be extracted.
        """
        location = sentence.location
        assert location is not None, \
            "Sentences must be extracted with locations"
        text = sentence.text
        feedback, sexp = self._execute_cmd(serapi, text)
        sentence.ast = sexp
        # Attach an undocumented extra field to the CoqSentence
        # object containing fully qualified referenced identifiers
        # NOTE: This must be done before identifiers get shadowed in
        # the `global_id_cache`
        sentence.identifiers = get_identifiers(str(sexp))  # type: ignore
        # get new ids and shadow redefined ones
        ids = self._update_ids(serapi)
        proof_id_changed = self.post_proof_id != self.pre_proof_id
        # update goals
        if (self.use_goals_diff and self.pre_goals is not None
                and self.post_goals is not None):
            pre_goals_or_diff = GoalsDiff.compute_diff(
                self.pre_goals,
                self.post_goals)
        else:
            pre_goals_or_diff = self.post_goals
        self.pre_goals = self.post_goals
        # analyze command
        vernac = SexpAnalyzer.analyze_vernac(sexp)
        if vernac.extend_type is None:
            command_type = vernac.vernac_type
        else:
            command_type = vernac.extend_type
        is_proof_aborted = ABORT_COMMAND_PATTERN.match(command_type) is not None
        is_program = any(
            _program_regex.search(attr) is not None
            for attr in vernac.attributes)
        # Check if we're dealing with a subproof
        is_subproof = (
            self.post_proof_id is not None
            and any(self.is_subproof_of(self.post_proof_id,
                                        i) for i in ids))
        if is_program:
            # A program was declared.
            # Persist the current goals.
            # Programs do not open proof mode, so post_proof_id
            # may be None or refer to another conjecture.
            program = self._start_program(
                sentence,
                command_type,
                ids,
                pre_goals_or_diff,
                get_identifiers,
                feedback)
            if program is not None:
                self.extracted_commands.append(program)
        elif proof_id_changed:
            self.post_goals = serapi.query_goals()
            if ids or is_proof_aborted:
                # a proof has concluded or been aborted
                if self.pre_proof_id in self.partial_proof_stacks:
                    self.partial_proof_stacks[self.pre_proof_id].append(
                        (sentence,
                         pre_goals_or_diff,
                         command_type))
                    completed_lemma = self._conclude_proof(
                        ids,
                        is_proof_aborted,
                        get_identifiers,
                        feedback)
                    if completed_lemma is not None:
                        self.extracted_commands.append(completed_lemma)
                    return
                else:
                    # That's not supposed to happen...
                    assert self.pre_proof_id is not None
                    already_defined = self._handle_anomalous_proof(
                        self.pre_proof_id,
                        ProofSentence(
                            text,
                            sentence.ast,
                            sentence.identifiers,  # type: ignore
                            location,
                            command_type,
                            pre_goals_or_diff,
                            get_identifiers,
                            feedback),
                        self.logger)
                    if already_defined:
                        return
            if (self.post_proof_id is not None
                    and self.post_proof_id not in self.partial_proof_stacks):
                # We are starting a new proof (or obligation).
                self._start_proof_block(
                    (sentence,
                     pre_goals_or_diff,
                     command_type))
            else:
                # we are continuing a delayed proof
                assert self.post_proof_id in self.partial_proof_stacks, \
                    f"{self.post_proof_id} should be in-progress"
                proof_stack = self.partial_proof_stacks[self.post_proof_id]
                proof_stack.append((sentence, pre_goals_or_diff, command_type))
        elif self.post_proof_id is not None and (not ids or is_subproof):
            # we are continuing an open proof
            if self.post_proof_id in self.partial_proof_stacks:
                self.post_goals = serapi.query_goals()
                proof_stack = self.partial_proof_stacks[self.post_proof_id]
                proof_stack.append((sentence, pre_goals_or_diff, command_type))
            else:
                assert self.post_proof_id in self.defined_lemmas, \
                    f"{self.post_proof_id} should be defined"
                # That's not supposed to happen...
                self._handle_anomalous_proof(
                    self.post_proof_id,
                    ProofSentence(
                        text,
                        sentence.ast,
                        sentence.identifiers,  # type: ignore
                        location,
                        command_type,
                        pre_goals_or_diff,
                        get_identifiers,
                        feedback),
                    self.logger)
                return
        else:
            # We are either not in a proof
            # OR we just defined something new as a side-effect.
            # We let the previous goals persist.
            self.extracted_commands.append(
                VernacCommandData(
                    ids,
                    None,
                    VernacSentence(
                        text,
                        sentence.ast,
                        sentence.identifiers,  # type: ignore
                        location,
                        command_type,
                        pre_goals_or_diff,
                        get_identifiers,
                        feedback)))

    def _handle_anomalous_proof(
            self,
            proof_id: str,
            proof_sentence: ProofSentence,
            logger: Optional[logging.Logger] = None) -> bool:
        """
        Handle anomalies dealing with inconsistent proof states.

        Sometimes a conjecture may be reported as open

        Parameters
        ----------
        proof_id : str
            The reported open conjecture.
        proof_sentence : ProofSentence
            The anomalous proof sentence.
        logger : Optional[logging.Logger], optional
            An optional logger with which a warning will be logged, by
            default None.

        Returns
        -------
        bool
            Whether `proof_id` was indeed already defined.
        """
        if OBLIGATION_ID_PATTERN.match(proof_id) is not None:
            extra = "Is there an extra 'Next Obligation.'?"
        else:
            extra = ""
        message = (
            f"Anomaly detected. '{proof_id}' is an open "
            f"conjecture but is also already defined. {extra}")
        if logger is not None:
            logger.warning(message)
        else:
            warnings.warn(message)
        if proof_id in self.defined_lemmas:
            # add to the existing lemma as a new proof
            # block
            lemma = self.defined_lemmas[proof_id]
            lemma.proofs.append([proof_sentence])
            return True
        return False

    def _process_proof_block(
            self,
            block: ProofBlock,
            get_identifiers: Callable[[str],
                                      List[Identifier]],
            feedback: List[str]) -> Proof:
        """
        Convert a proof block into the form expected for extraction.

        Parameters
        ----------
        block : List[Tuple[CoqSentence, Goals, CommandType]]
            A list of proof steps within the block paired with goals
            prior to the proof step and Vernacular types.
        get_identifiers : Callable[[str], List[Identifier]]
            A function that accepts a serialized AST and returns a list
            of fully qualified identifiers in the order of their
            appearance in the AST.
        feedback : List[str]
            Feedback from executing the `sentence`.

        Returns
        -------
        Proof
            The compiled proof.
        """
        if not block:
            return []
        proof_steps, goals, command_types = unzip(block)
        proof = []
        tactic: CoqSentence
        goal: Optional[Union[Goals, GoalsDiff]]
        command_type: str
        for (tactic,
             goal,
             command_type) in zip(proof_steps,
                                  goals,
                                  command_types):
            assert tactic.ast is not None, \
                "The tactic must have an AST"
            assert tactic.location is not None, \
                "The tactic must be located"
            proof.append(
                ProofSentence(
                    tactic.text,
                    tactic.ast,
                    tactic.identifiers,  # type: ignore
                    tactic.location,
                    command_type,
                    goal,
                    get_identifiers,
                    feedback))
        return proof

    def _start_program(
        self,
        sentence: CoqSentence,
        command_type: str,
        ids: List[str],
        pre_goals_or_diff: Optional[Union[Goals,
                                          GoalsDiff]],
        get_identifiers: Callable[[str],
                                  List[Identifier]],
        feedback: List[str],
    ) -> Optional[VernacCommandData]:
        """
        Start accumulation of a new program.

        Parameters
        ----------
        sentence : CoqSentence
            The sentence that instigated the program.
        command_type : str
            The type of the sentence's Vernacular command.
        ids : List[str]
            The list of definitions emitted by the program's
            declaration, if any.
        pre_goals_or_diff : Optional[Union[Goals, GoalsDiff]]
            Proof goals prior to the execution of the sentence, if any.
        get_identifiers : Callable[[str], List[Identifier]]
            A function that accepts a serialized AST and returns a list
            of fully qualified identifiers in the order of their
            appearance in the AST.
        feedback : List[str]
            Feedback from executing the `sentence`.

        Returns
        -------
        Optional[VernacCommandData]
            The compiled command data for the program if all of its
            obligations were automatically resolved or None if some
            obligations remain.
        """
        # Try to determine if all of the obligations were
        # immediately resolved.
        program_id = None
        ids_set = set(ids)
        for new_id in ids:
            match = OBLIGATION_ID_PATTERN.match(new_id)
            if match is not None:
                program_id = match.groupdict()['proof_id']
                if program_id in ids_set:
                    break
                else:
                    # reset
                    program_id = None
        if program_id is not None:
            # all obligations were resolved
            assert sentence.ast is not None, \
                "The sentence must have an AST"
            assert sentence.location is not None, \
                "The sentence must be located"
            return VernacCommandData(
                ids,
                None,
                VernacSentence(
                    sentence.text,
                    sentence.ast,
                    sentence.identifiers,  # type: ignore
                    sentence.location,
                    command_type,
                    pre_goals_or_diff,
                    get_identifiers,
                    feedback))
        else:
            # some obligations remain
            self.programs.append((sentence, pre_goals_or_diff, command_type))
            return None

    def _start_proof_block(self, sentence: SentenceState) -> None:
        """
        Start accumulation of a new proof block.

        Parameters
        ----------
        sentence : SentenceState
            The sentence that instigated the proof.
        """
        assert self.post_proof_id is not None, \
            "post_proof_id must not be None"
        assert self.post_proof_id not in self.partial_proof_stacks, \
            f"The proof of {self.post_proof_id} has already been started"
        command_type = sentence[2]
        if command_type == "Obligations":
            # Obligations get accumulated separately, but we
            # need to know to which lemma (program) they ultimately
            # correspond.
            m = OBLIGATION_ID_PATTERN.match(self.post_proof_id)
            assert m is not None, \
                "Cannot parse obligation ID"
            program_id = m.groupdict()['proof_id']
            self.obligation_map[self.post_proof_id] = program_id
            proof_stack = self.partial_proof_stacks.setdefault(
                self.post_proof_id,
                [])
            proof_stack.append(sentence)
            if program_id not in self.conjectures:
                # Programs unfortunately do not open proof
                # mode until an obligation's proof has been
                # started.
                # Consequently, we cannot rely upon
                # get_conjecture_id to catch the ID
                # of the program.
                for i, program in enumerate(reversed(self.programs)):
                    if program_id in program[0].text:
                        self.conjectures[program_id] = program
                        self.programs.pop(len(self.programs) - i - 1)
                        break
                assert program_id in self.conjectures
        else:
            assert self.post_proof_id not in self.conjectures, \
                f"The proof of {self.post_proof_id} has already been started"
            self.conjectures[self.post_proof_id] = sentence
            self.partial_proof_stacks[self.post_proof_id] = []

    def _update_ids(
        self,
        serapi: SerAPI,
    ) -> List[str]:
        """
        Update known local identifiers.

        Parameters
        ----------
        serapi : SerAPI
            An interactive `sertop` session.

        Returns
        -------
        ids : List[str]
            The set of identifiers introduced by the most recent
            command.
        """
        # ids = serapi.parse_new_identifiers(feedback)
        all_local_ids = serapi.get_local_ids()
        # get new identifiers
        alignment = serapi_id_align(self.local_ids, all_local_ids)
        new_ids = []
        for element_a, element_b in reversed(alignment):
            if element_a is not None:
                break
            new_ids.append(element_b)
        ids = new_ids[::-1]
        # update reference set
        self.local_ids = all_local_ids
        for ident in ids:
            # shadow old ids
            self.expanded_ids.pop(ident, None)
        self.pre_proof_id = self.post_proof_id
        self.post_proof_id = serapi.get_conjecture_id()
        return ids

    def is_subproof_of(self, proof_id: str, id_under_test: str) -> bool:
        """
        Check if the given ID corresponds to a subproof of a conjecture.

        Parameters
        ----------
        proof_id : str
            The identifier of a conjecture.
        id_under_test : List[str]
            An identifier of a possible subproof.

        Returns
        -------
        bool
            True if `id_under_test` is a subproof of `proof_id`, False
            otherwise.
        """
        match = SUBPROOF_ID_PATTERN.match(id_under_test)
        return match is not None and match['proof_id'] == proof_id


def extract_vernac_commands(
    project: ProjectRepo,
    files_to_use: Optional[Iterable[str]] = None,
    force_serial: bool = False,
    worker_semaphore: Optional[BoundedSemaphore] = None
) -> Tuple[VernacDict,
           CommentDict]:
    """
    Compile vernac commands from a project into a dict.

    Parameters
    ----------
    project : ProjectRepo
        The project from which to extract the vernac commands
    files_to_use : Iterable[str] | None
        An iterable of filenames to use for this project; or None. If
        None, all files are used. By default, None.
        This argument is especially useful for profiling.
    force_serial : bool, optional
        If this argument is true, disable parallel execution. Useful for
        debugging. By default False.
    worker_semaphore : Semaphore or None, optional
        Semaphore used to control the number of file workers than
        can run at once. By default None. If None, ignore.

    Returns
    -------
    VernacDict
        A map from file names to their extracted commands.
    """
    command_data: Dict[str,
                       VernacCommandDataList] = {}
    comment_data: Dict[str,
                       List[CoqComment]] = {}
    with pushd(project.dir_abspath):
        file_list = project.get_file_list(relative=True, dependency_order=True)
        if files_to_use:
            file_list = [f for f in file_list if f in files_to_use]
        # Remove files that don't have corresponding .vo files
        final_file_list = []
        for filename in file_list:
            path = Path(filename)
            vo = path.parent / (path.stem + ".vo")
            if not os.path.exists(vo):
                logging.info(
                    f"Skipped extraction for file {filename}. "
                    "No .vo file found.")
            else:
                final_file_list.append(filename)
        if force_serial:
            pbar = tqdm.tqdm(
                final_file_list,
                total=len(final_file_list),
                desc=f"Caching {project.name}@{project.short_sha}")
            for filename in pbar:
                # Verify that accompanying vo file exists first
                pbar.set_description(
                    f"Caching {project.name}@{project.short_sha}:{filename}")
                result = _extract_vernac_commands_worker(filename, project)
                if isinstance(result, ExtractVernacCommandsError):
                    if result.parent is not None:
                        raise result from result.parent
                    else:
                        raise result
                sentences, comments = result
                command_data[filename] = sentences
                comment_data[filename] = comments
        else:
            if worker_semaphore is None:
                raise ValueError(
                    "force_serial is False but the worker_semaphore is None. "
                    "This is not a valid combination of arguments.")
            arg_list = [(f, project, worker_semaphore) for f in final_file_list]
            results = process_map(
                _extract_vernac_commands_worker_star,
                arg_list,
                desc=f"Caching {project.name}@{project.short_sha}")
            for f, result in zip(final_file_list, results):
                if isinstance(result, ExtractVernacCommandsError):
                    if result.parent is not None:
                        raise result from result.parent
                    else:
                        raise result
                sentences, comments = result
                command_data[f] = sentences
                comment_data[f] = comments
    return command_data, comment_data


def _extract_vernac_commands_worker(
    filename: str,
    project: ProjectRepo,
    worker_semaphore: Optional[BoundedSemaphore] = None,
    pbar: Optional[tqdm.tqdm] = None
) -> Union[Tuple[VernacCommandDataList,
                 List[CoqComment]],
           ExtractVernacCommandsError]:
    """
    Provide worker function for file-parallel cache extraction.
    """
    if worker_semaphore is not None:
        worker_semaphore.acquire()
    try:
        assert project.serapi_options is not None, \
            "serapi_options must not be None"
        (sentences,
         comments) = typing.cast(
             Tuple[List[CoqSentence],
                   List[CoqComment]],
             project.get_sentences(
                 filename,
                 SEM.HEURISTIC,
                 return_locations=True,
                 return_comments=True,
                 glom_proofs=False))
        result = CommandExtractor(
            filename,
            sentences,
            opam_switch=project.opam_switch,
            serapi_options=project.serapi_options)
    except Exception as e:
        return ExtractVernacCommandsError(
            f"Error on {filename}",
            filename,
            e,
            traceback.format_exc())
    finally:
        if worker_semaphore is not None:
            worker_semaphore.release()
    if pbar is not None:
        pbar.update(1)
    return result.extracted_commands, comments


def _extract_vernac_commands_worker_star(
    args
) -> Union[Tuple[VernacCommandDataList,
                 List[CoqComment]],
           ExtractVernacCommandsError]:
    return _extract_vernac_commands_worker(*args)


def extract_cache(
    build_cache_client: CoqProjectBuildCacheProtocol,
    switch_manager: SwitchManager,
    project: ProjectRepo,
    commit_sha: str,
    process_project_fallback: Callable[[ProjectRepo],
                                       Tuple[VernacDict,
                                             CommentDict]],
    coq_version: Optional[str] = None,
    recache: Optional[Callable[
        [CoqProjectBuildCacheProtocol,
         ProjectRepo,
         str,
         str],
        bool]] = None,
    block: bool = False,
    files_to_use: Optional[Iterable[str]] = None,
    force_serial: bool = False,
    worker_semaphore: Optional[BoundedSemaphore] = None,
    max_memory: Optional[int] = None,
    max_runtime: Optional[int] = None,
) -> None:
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
    build_cache_client : CoqProjectBuildCacheProtocol
        The client that can insert the build artifacts into the on-disk
        build cache.
    switch_manager : SwitchManager
        A source of switches in which to process the project.
    project : ProjectRepo
        The project from which to extract data.
    commit_sha : str
        The commit whose data should be extracted.
    process_project_fallback : Callable[[ProjectRepo], \
                                        Tuple[VernacDict, CommentDict]]
        Function that provides fallback vernacular command
        extraction for projects that do not build.
    coq_version : str or None, optional
        The version of Coq in which to build the project, by default
        None.
    recache : Callable[[CoqProjectBuildCache, ProjectRepo, str, str], \
                       bool] \
            or None, optional
        A function that for an existing entry in the cache returns
        whether it should be reprocessed or not.
    block : bool, optional
        Whether to use blocking cache writes, by default False
    files_to_use : Iterable[str] | None
        An iterable of files to use from this project; or None. If None,
        all files are used. By default, None.
        This argument is especially useful for profiling.
    force_serial : bool, optional
        If this argument is true, disable parallel execution. Useful for
        debugging. By default False.
    worker_semaphore : Semaphore or None, optional
        Semaphore used to control the number of file workers than
        can run at once, by default None. If None, ignore.
    max_memory : Optional[ResourceLimits], optional
        Maximum memory (bytes) allowed to build project, by default
        None
    max_runtime : Optional[ResourceLimits], optional
        Maximum cpu time (seconds) allowed to build project, by default
        None

    See Also
    --------
    prism.data.build_cache.CoqProjectBuildCache
    prism.data.build_cache.ProjectCommitData
    prism.data.build_cache.VernacCommandData
    """
    if coq_version is None:
        coq_version = project.metadata.coq_version
    assert coq_version is not None, "coq_version must not be None"
    if (not build_cache_client.contains((project.name,
                                         commit_sha,
                                         coq_version))
            or (recache is not None and recache(build_cache_client,
                                                project,
                                                commit_sha,
                                                coq_version))):
        extract_cache_new(
            build_cache_client,
            switch_manager,
            project,
            commit_sha,
            process_project_fallback,
            coq_version,
            block,
            files_to_use,
            force_serial,
            worker_semaphore,
            max_memory,
            max_runtime)


def extract_cache_new(
    build_cache_client: CoqProjectBuildCacheProtocol,
    switch_manager: SwitchManager,
    project: ProjectRepo,
    commit_sha: str,
    process_project_fallback: Callable[[ProjectRepo],
                                       Tuple[VernacDict,
                                             CommentDict]],
    coq_version: Optional[str],
    block: bool,
    files_to_use: Optional[Iterable[str]],
    force_serial: bool,
    worker_semaphore: Optional[BoundedSemaphore],
    max_memory: Optional[int],
    max_runtime: Optional[int],
):
    r"""
    Extract a new cache object and insert it into the build cache.

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
    process_project_fallback : Callable[[ProjectRepo], \
                                        Tuple[VernacDict, CommentDict]]
        Function that provides fallback vernacular command extraction
        for projects that do not build.
    coq_version : str or None
        The version of Coq in which to build the project, by default
        None.
    block : bool
        Whether to use blocking cache writes
    files_to_use : Iterable[str] | None
        An iterable of files to use from this project; or None. If None,
        all files are used. By default, None.
        This argument is especially useful for profiling.
    force_serial : bool
        If this argument is true, disable parallel execution. Useful for
        debugging.
    worker_semaphore : Semaphore or None
        Semaphore used to control the number of file workers that can
        run at once. If None, ignore.
    max_memory : Optional[ResourceLimits]
        Maximum memory (bytes) allowed to build project
    max_runtime : Optional[ResourceLimits]
        Maximum cpu time (seconds) allowed to build project
    """
    # Construct a logger local to this function and unique to this PID
    pid = os.getpid()
    logger = logging.getLogger(f"extract_vernac_commands-{pid}")
    logger.setLevel(logging.DEBUG)
    # Tell the logger to log to a text stream
    with StringIO() as logger_stream:
        handler = logging.StreamHandler(logger_stream)
        # Clear any default handlers
        for h in logger.handlers:
            logger.removeHandler(h)
        logger.addHandler(handler)
        original_switch = project.opam_switch
        managed_switch_kwargs = {
            'coq_version': coq_version,
            'variables': {
                'build': True,
                'post': True,
                'dev': True
            },
            'release': False,
            'switch_manager': switch_manager,
        }
        try:
            # Make sure there aren't any changes or uncommitted files
            # left over from previous iterations, then check out the
            # current commit
            project.git.reset('--hard')
            project.git.clean('-fdx')
            project.git.checkout(commit_sha)
            project.submodule_update(
                init=True,
                recursive=True,
                keep_going=True,
                force_remove=True,
                force_reset=True)
            # process the commit
            commit_message = project.commit().message
            if isinstance(commit_message, bytes):
                commit_message = commit_message.decode("utf-8")
            try:
                build_result = project.build(
                    managed_switch_kwargs=managed_switch_kwargs,
                    max_runtime=max_runtime,
                    max_memory=max_memory)
            except (ProjectBuildError, TimeoutExpired) as pbe:
                if isinstance(pbe, ProjectBuildError):
                    build_result = (pbe.return_code, pbe.stdout, pbe.stderr)
                else:
                    stdout = pbe.stdout.decode(
                        "utf-8") if pbe.stdout is not None else ''
                    stderr = pbe.stderr.decode(
                        "utf-8") if pbe.stderr is not None else ''
                    build_result = (1, stdout, stderr)
                command_data, comment_data = process_project_fallback(project)
                build_cache_client.write_build_error_log(
                    project.metadata,
                    block,
                    ProjectBuildResult(*build_result))
            else:
                start_time = time()
                try:
                    command_data, comment_data = extract_vernac_commands(
                        project,
                        files_to_use,
                        force_serial,
                        worker_semaphore)
                except ExtractVernacCommandsError as e:
                    logger.critical(f"Filename: {e.filename}\n")
                    logger.critical(
                        f"Parent stack trace:\n{e.parent_stacktrace}\n")
                    logger.exception(e)
                    logger_stream.flush()
                    logged_text = logger_stream.getvalue()
                    build_cache_client.write_cache_error_log(
                        project.metadata,
                        block,
                        logged_text)
                    raise
                finally:
                    elapsed_time = time() - start_time
                    build_cache_client.write_timing_log(
                        project.metadata,
                        block,
                        f"Elapsed time in extract_vernac_commands: {elapsed_time} s"
                    )
            try:
                file_dependencies = project.get_file_dependencies()
            except (MissingMetadataError, CalledProcessError):
                logger.exception(
                    "Failed to get file dependencies. Are the IQR flags set/correct?"
                )
                file_dependencies = None
            data = ProjectCommitData(
                project.metadata,
                command_data,
                commit_message,
                comment_data,
                file_dependencies,
                ProjectBuildEnvironment(project.opam_switch.export()),
                ProjectBuildResult(*build_result))
            build_cache_client.write(data, block)
        except ExtractVernacCommandsError:
            # Don't re-log extract_vernac_commands errors
            pass
        except Exception as e:
            logger.critical(
                "An exception occurred outside of extracting vernacular commands.\n"
            )
            # If a subprocess command failed, capture the standard
            # output and error
            if isinstance(e, CalledProcessError):
                logger.critical(f"stdout:\n{e.stdout}\n")
                logger.critical(f"stderr:\n{e.stderr}\n")
            project_metadata = project.metadata
            if isinstance(e, UnsatisfiableConstraints):
                project_metadata = copy.copy(project_metadata)
                project_metadata.coq_version = coq_version
            logger.exception(e)
            logger_stream.flush()
            logged_text = logger_stream.getvalue()
            build_cache_client.write_misc_error_log(
                project_metadata,
                block,
                logged_text)
        finally:
            # release the switch
            switch_manager.release_switch(project.opam_switch)
            project.opam_switch = original_switch


# Abbreviation defined to satisfy conflicting autoformatting and style
# requirements in cache_extract_commit_iterator.
CTS = CommitTraversalStrategy


def cache_extract_commit_iterator(
        project: ProjectRepo,
        starting_commit_sha: str,
        max_num_commits: Optional[int],
        march_strategy: CTS = CTS.CURLICUE_NEW,
        date_limit: bool = False) -> Generator[str,
                                               None,
                                               None]:
    """
    Provide default commit iterator for cache extraction.

    Commits are limited to those that occur on or after January 1, 2019,
    which roughly coincides with the release of Coq 8.9.1.
    """
    iterator = ChangedCoqCommitIterator(
        project,
        starting_commit_sha,
        march_strategy)
    i = 0
    for item in iterator:
        # get commit object
        item = project.commit(item)
        # Define the minimum date; convert it to seconds since epoch
        limit_date = datetime(2019, 1, 1, 0, 0, 0)
        limit_epoch = calendar.timegm(limit_date.timetuple())
        # committed_date is in seconds since epoch
        if not date_limit or (item.committed_date is not None
                              and item.committed_date >= limit_epoch):
            i += 1
            yield item.hexsha
        if max_num_commits is not None and i >= max_num_commits:
            break


class CacheExtractor:
    """
    Class for managing a broad Coq project cache extraction process.
    """

    def __init__(
            self,
            cache_dir: str,
            metadata_storage_file: str,
            swim: SwitchManager,
            default_commits_path: str,
            commit_iterator_factory: Callable[[ProjectRepo,
                                               str],
                                              Iterable[str]],
            coq_version_iterator: Optional[Callable[[ProjectRepo,
                                                     str],
                                                    Iterable[Union[
                                                        str,
                                                        Version]]]] = None,
            process_project_fallback: Optional[Callable[
                [ProjectRepo],
                Tuple[VernacDict,
                      CommentDict]]] = None,
            recache: Optional[Callable[
                [CoqProjectBuildCacheProtocol,
                 ProjectRepo,
                 str,
                 str],
                bool]] = None,
            files_to_use: Optional[Dict[str,
                                        Iterable[str]]] = None,
            cache_fmt_ext: Optional[str] = None,
            mds_fmt: Optional[str] = None):
        self.cache_kwargs = {
            "fmt_ext": cache_fmt_ext
        } if cache_fmt_ext else {}
        """
        Keyword arguments for constructing the project cache build
        server
        """
        self.mds_kwargs = {
            "fmt": mds_fmt
        } if mds_fmt else {}
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
            **self.mds_kwargs)
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
                                   List[str]] = typing.cast(
                                       Dict[str,
                                            List[str]],
                                       io.load(
                                           str(self.default_commits_path),
                                           clz=dict))
        """
        The default commits for each project.
        """

        if coq_version_iterator is None:
            coq_version_iterator = self.default_coq_version_iterator
        self.coq_version_iterator = coq_version_iterator
        """
        An iterator over coq versions
        """

        if process_project_fallback is None:
            process_project_fallback = self.default_process_project_fallback
        self.process_project_fallback = process_project_fallback
        """
        Function to process commits for cache extraction if they do not
        build
        """

        self.files_to_use_map = files_to_use
        """
        A mapping from project name to files to use from that project;
        or None. If None, all files are used. By default, None.
        This argument is especially useful for profiling.
        """

        if recache is None:
            recache = self.default_recache
        self.recache = recache
        """
        Function that determines when a project commit's cached
        artifacts should be recomputed.
        """

    def get_commit_iterator_func(
            self) -> Callable[[ProjectRepo],
                              Iterable[str]]:
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

    def get_extract_cache_func(
        self,
        force_serial: bool = False,
        worker_semaphore: Optional[BoundedSemaphore] = None,
        max_memory: Optional[int] = None,
        max_runtime: Optional[int] = None,
    ) -> Callable[[ProjectRepo,
                   str,
                   None],
                  None]:
        """
        Return the cache extraction function for the commit mapper.

        Parameters
        ----------
        force_serial : bool, optional
            If this argument is true, disable parallel execution. Useful
            for debugging. By default False.
        worker_semaphore : Semaphore or None, optional
            Semaphore used to control the number of file workers than
            can run at once, by default None. If None, ignore.
        max_memory : Optional[ResourceLimits], optional
            Maximum memory (bytes) allowed to build project, by default
            None
        max_runtime : Optional[ResourceLimits], optional
            Maximum cpu time (seconds) allowed to build project, by
            default None

        Returns
        -------
        Callable[[ProjectRepo, str, None], None]
            The extraction function to be mapped
        """
        return partial(
            CacheExtractor.extract_cache_func,
            build_cache_client=self.cache_client,
            switch_manager=self.swim,
            process_project_fallback=self.process_project_fallback,
            recache=self.recache,
            coq_version_iterator=self.coq_version_iterator,
            files_to_use_map=self.files_to_use_map,
            force_serial=force_serial,
            worker_semaphore=worker_semaphore,
            max_memory=max_memory,
            max_runtime=max_runtime,
        )

    def run(
        self,
        root_path: PathLike,
        log_dir: Optional[PathLike] = None,
        updated_md_storage_file: Optional[PathLike] = None,
        extract_nprocs: int = 8,
        force_serial: bool = False,
        n_build_workers: int = 1,
        project_names: Optional[List[str]] = None,
        max_procs_file_level: int = 0,
        max_memory: Optional[int] = None,
        max_runtime: Optional[int] = None,
    ) -> None:
        """
        Build all projects at `root_path` and save updated metadata.

        Parameters
        ----------
        root_path : PathLike
            The root directory containing each project's directory.
            The project directories do not need to already exist.
        log_dir : PathLike or None, optional
            Directory to store log file(s) in, by default the directory
            that the metadata storage file is loaded from
        updated_md_storage_file : PathLike or None, optional
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
        project_names : list of str or None, optional
            If a list is provided, select only projects with names on
            the list for extraction. If projects on the given list
            aren't found, a warning is given. By default None.
        max_procs_file_level : int, optional
            Maximum number of active workers to allow at once on the
            file-level of extraction, by default 0. If 0, allow
            unlimited processes at this level.
        max_memory : Optional[ResourceLimits], optional
            Maximum memory (bytes) allowed to build project, by default
            None
        max_runtime : Optional[ResourceLimits], optional
            Maximum cpu time (seconds) allowed to build project, by
            default None
        """
        if log_dir is None:
            log_dir = Path(self.md_storage_file).parent
        # Generate list of projects
        project_list = self.md_storage.projects
        if project_names is not None:
            project_list = [p for p in project_list if p in project_names]
        projects = list(
            tqdm.tqdm(
                Pool(20).imap(
                    get_project_func(
                        root_path,
                        self.md_storage,
                        n_build_workers),
                    project_list),
                desc="Initializing project instances",
                total=len(project_list)))
        # Issue a warning if any requested projects are not present in
        # metadata.
        if project_names is not None:
            actual_project_set = {p.name for p in projects}
            requested_project_set = set(project_names)
            diff = requested_project_set.difference(actual_project_set)
            if diff:
                logging.warn(
                    "The following projects were requested but were not "
                    f"found: {', '.join(diff)}")
        if force_serial:
            manager = None
        else:
            manager = mp.Manager()
        # The following CoqProjectBuildCacheServer is created whether or
        # not force_serial is True, even though the server is not used
        # if force_serial is True. The overhead of starting a server is
        # not so great that it would be worth complicating the control
        # flow to avoid it in the force_serial=True case.
        with CoqProjectBuildCacheServer() as cache_server:
            if force_serial:
                self.cache_client = CoqProjectBuildCache(
                    self.cache_dir,
                    **self.cache_kwargs)
            else:
                self.cache_client = CoqProjectBuildCacheClient(
                    cache_server,
                    self.cache_dir,
                    **self.cache_kwargs)
            # Create semaphore for controlling file-level workers
            if manager is not None:
                nprocs = os.cpu_count(
                ) if not max_procs_file_level else max_procs_file_level
                worker_semaphore = manager.BoundedSemaphore(nprocs)
            else:
                worker_semaphore = None
            # Create commit mapper
            project_looper = ProjectCommitUpdateMapper[None](
                projects,
                self.get_commit_iterator_func(),
                self.get_extract_cache_func(
                    force_serial,
                    worker_semaphore,
                    max_memory=max_memory,
                    max_runtime=max_runtime),
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
            if updated_md_storage_file:
                metadata_storage.dump(metadata_storage, updated_md_storage_file)
            print("Done")

    @staticmethod
    def _commit_iterator_func(
        project: ProjectRepo,
        default_commits: Dict[str,
                              List[str]],
        commit_iterator_factory: Callable[[ProjectRepo,
                                           str],
                                          Iterable[str]]
    ) -> Iterable[str]:
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

    @classmethod
    def default_coq_version_iterator(cls,
                                     _project: ProjectRepo,
                                     _commit: str) -> List[str]:
        """
        Extract build caches for all Coq versions we consider.
        """
        return [
            "8.9.1",
            "8.10.2",
            "8.11.2",
            "8.12.2",
            "8.13.2",
            "8.14.1",
            "8.15.2"
        ]

    @classmethod
    def default_process_project_fallback(cls,
                                         _project: ProjectRepo
                                         ) -> Tuple[VernacDict,
                                                    CommentDict]:
        """
        By default, do nothing on project build failure.
        """
        return dict(), dict()

    @classmethod
    def default_recache(
            cls,
            _build_cache: CoqProjectBuildCacheProtocol,
            _project: ProjectRepo,
            _commit_sha: str,
            _coq_version: str) -> bool:
        """
        By default, do not recache anything.
        """
        return False

    @classmethod
    def extract_cache_func(
        cls,
        project: ProjectRepo,
        commit_sha: str,
        _result: None,
        build_cache_client: CoqProjectBuildCacheProtocol,
        switch_manager: SwitchManager,
        process_project_fallback: Callable[[ProjectRepo],
                                           Tuple[VernacDict,
                                                 CommentDict]],
        recache: Callable[[CoqProjectBuildCacheProtocol,
                           ProjectRepo,
                           str,
                           str],
                          bool],
        coq_version_iterator: Callable[[ProjectRepo,
                                        str],
                                       Iterable[Union[str,
                                                      Version]]],
        files_to_use_map: Optional[Dict[str,
                                        Iterable[str]]],
        force_serial: bool,
        worker_semaphore: Optional[BoundedSemaphore],
        max_memory: Optional[int],
        max_runtime: Optional[int],
    ):
        r"""
        Extract cache.

        Parameters
        ----------
        project : ProjectRepo
            The project to extract cache from
        commit_sha : str
            The commit to extract cache from
        _result : None
            Left empty for compatibility with `ProjectCommitMapper`
        build_cache_client : CoqProjectbuildCacheProtocol
            A mapping from project name to build cache client, used to
            write extracted cache to disk
        switch_manager : SwitchManager
            A switch manager to use during extraction
        process_project_fallback : Callable[[ProjectRepo], \
                                            Tuple[VernacDict, \
                                                  CommentDict]]
            A function that does a best-effort cache extraction when the
            project does not build
        recache : Callable[[CoqProjectBuildCache, ProjectRepo, str, \
                            str], \
                           bool]
            A function that for an existing entry in the cache returns
            whether it should be reprocessed or not.
        coq_version_iterator : Callable[[ProjectRepo, str],
                                        Iterable[Union[str, Version]]]
            A function that returns an iterable over allowable coq
            versions
        files_to_use_map : Dict[str, Iterable[str]] | None
            A mapping from project name to files to use from that
            project; or None. If None, all files are used. By default,
            None. This argument is especially useful for profiling.
        force_serial : bool
            If this argument is true, disable parallel execution. Useful
            for debugging.
        worker_semaphore : Semaphore or None
            Semaphore used to control the number of file workers than
            can run at once. If None, ignore.
        max_memory : Optional[ResourceLimits]
            Maximum memory (bytes) allowed to build project
        max_runtime : Optional[ResourceLimits]
            Maximum cpu time (seconds) allowed to build project
        """
        pbar = tqdm.tqdm(
            coq_version_iterator(project,
                                 commit_sha),
            desc="Coq version")
        files_to_use = None
        if files_to_use_map is not None:
            try:
                files_to_use = files_to_use_map[f"{project.name}@{commit_sha}"]
            except KeyError:
                try:
                    files_to_use = files_to_use_map[project.name]
                except KeyError:
                    files_to_use = None
        for coq_version in pbar:
            pbar.set_description(
                f"Coq version ({project.name}@{commit_sha[: 8]}): {coq_version}"
            )
            extract_cache(
                build_cache_client,
                switch_manager,
                project,
                commit_sha,
                process_project_fallback,
                str(coq_version),
                recache,
                files_to_use=files_to_use,
                force_serial=force_serial,
                worker_semaphore=worker_semaphore,
                max_memory=max_memory,
                max_runtime=max_runtime,
            )
