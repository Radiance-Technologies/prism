"""
Defines a class for extracting command data from sequences of sentences.
"""
import logging
import re
import typing
import warnings
from dataclasses import InitVar, dataclass, field
from functools import partial
from typing import (
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
)

import numba

from prism.data.cache.types import (
    CommandType,
    Proof,
    ProofSentence,
    VernacCommandData,
    VernacCommandDataList,
    VernacSentence,
)
from prism.interface.coq.exception import CoqExn
from prism.interface.coq.goals import Goals, GoalsDiff
from prism.interface.coq.ident import Identifier, get_all_qualified_idents
from prism.interface.coq.options import CoqFlag, SerAPIOptions
from prism.interface.coq.re_patterns import (
    ABORT_COMMAND_PATTERN,
    IDENT_PATTERN,
    OBLIGATION_ID_PATTERN,
    SUBPROOF_ID_PATTERN,
)
from prism.interface.coq.serapi import AbstractSyntaxTree, SerAPI
from prism.language.gallina.analyze import SexpAnalyzer
from prism.language.heuristic.parser import CoqSentence
from prism.language.sexp.node import SexpNode
from prism.project.base import Project
from prism.util.alignment import Alignment, align_factory
from prism.util.opam.switch import OpamSwitch
from prism.util.opam.version import OpamVersion
from prism.util.radpytools import unzip
from prism.util.radpytools.dataclasses import default_field
from prism.util.radpytools.path import PathLike
from prism.util.re import regex_from_options

_program_regex = re.compile("[Pp]rogram")

_program_mode_regex = regex_from_options(
    ['VernacDefinition',
     'VernacFixpoint',
     'VernacCoFixpoint'],
    False,
    False)
"""
Match command types that can generate obligations when ``Program Mode``
is enabled.

According to official documentation, this should only be definitions and
fixpoints, but the documentation may be incomplete.
"""

_save_pattern = re.compile(rf"Save\s+(?P<ident>{IDENT_PATTERN.pattern})\s*.")

_printing_options_pattern = re.compile(r"(?:Set|Unset)\s+Printing\s+.*\.")

SentenceState = Tuple[CoqSentence,
                      Optional[Union[Goals,
                                     GoalsDiff]],
                      CommandType]
ProofSentenceState = Tuple[CoqSentence,
                           Optional[Union[Goals,
                                          GoalsDiff]],
                           CommandType]
ProofBlock = List[ProofSentenceState]

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
    serapi_options: SerAPIOptions = default_field(SerAPIOptions.empty())
    """
    The options given to `sertop` with which to perform extraction.

    Some options may not be given directly to `sertop` but have
    Vernacular command equivalents that can be performed as part of
    initialization of the SerAPI session.
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
    serapi: Optional[SerAPI] = default_field(None, init=False)

    def __post_init__(self, sentences: Optional[Iterable[CoqSentence]]):
        """
        Initialize the `modpath`.
        """
        self.modpath = Project.get_local_modpath(
            self.filename,
            self.serapi_options.iqr)
        if sentences is not None:
            self(sentences)

    def __call__(
            self,
            sentences: Iterable[CoqSentence]) -> VernacCommandDataList:
        """
        Perform the extraction.
        """
        return self.extract_vernac_commands(sentences)

    def __enter__(self) -> Callable[[CoqSentence], None]:
        """
        Initialize a context for an extraction session.
        """
        self.serapi = SerAPI(self.serapi_options, opam_switch=self.opam_switch)
        get_identifiers = typing.cast(
            Callable[[str],
                     List[Identifier]],
            partial(
                get_all_qualified_idents,
                self.serapi,
                self.modpath,
                ordered=True,
                id_cache=self.expanded_ids))
        return partial(
            self._extract_vernac_sentence,
            self.serapi,
            get_identifiers)

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Conclude a context for an extraction session.
        """
        self.serapi.shutdown()
        self.serapi = None

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

    def _ensure_program_is_conjecture(self, program_id: str) -> None:
        """
        Ensure that the given program ID is recorded as a conjecture.
        """
        if program_id not in self.conjectures:
            # Programs unfortunately do not open proof
            # mode until an obligation's proof has been
            # started.
            # Consequently, we cannot rely upon
            # get_conjecture_id to catch the ID
            # of the program.
            for i, program in enumerate(reversed(self.programs)):
                # XXX: This check is quite brittle and prone to false
                # positives if the program_id is very short.
                # However, usual naming conventions in real developments
                # make this possibility unlikely.
                if program_id in program[0].text.split():
                    self.conjectures[program_id] = program
                    self.programs.pop(len(self.programs) - i - 1)
                    break
            assert program_id in self.conjectures

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
        if not is_program and _program_mode_regex.match(
                command_type) is not None:
            program_mode_setting = serapi.query_setting("Program Mode")
            assert program_mode_setting is not None, \
                "Program Mode should be a valid flag name"
            program_mode_setting = typing.cast(CoqFlag, program_mode_setting)
            is_program = program_mode_setting.value
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
            # Check to see if we advanced any programs
            command = self._process_defined_obligations(
                sentence,
                pre_goals_or_diff,
                command_type,
                ids,
                get_identifiers,
                feedback)
            if command is None:
                command = VernacCommandData(
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
                        feedback))
            self.extracted_commands.append(command)

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
            warnings.warn(message, stacklevel=2)
        if proof_id in self.defined_lemmas:
            # add to the existing lemma as a new proof
            # block
            lemma = self.defined_lemmas[proof_id]
            lemma.proofs.append([proof_sentence])
            return True
        return False

    def _process_defined_obligations(
        self,
        sentence: CoqSentence,
        pre_goals_or_diff: Optional[Union[Goals,
                                          GoalsDiff]],
        command_type: str,
        ids: List[str],
        get_identifiers: Callable[[str],
                                  List[Identifier]],
        feedback: List[str],
    ) -> Optional[VernacCommandData]:
        """
        Process any obligations defined as a side-effect of a command.

        Parameters
        ----------
        sentence : CoqSentence
            An executed sentence.
        pre_goals_or_diff : Optional[Union[Goals, GoalsDiff]]
            The goals prior to execution of the `sentence`.
        command_type : str
            The type of command represented by the `sentence`.
        ids : List[str]
            The identifiers introduced after the `sentence`'s execution.
        get_identifiers : Callable[[str], List[Identifier]]
            A function that accepts a serialized AST and returns a list
            of fully qualified identifiers in the order of their
            appearance in the AST.
        feedback : List[str]
            Feedback from executing the `sentence`.

        Returns
        -------
        Optional[VernacCommandData]
            If a program was defined as a side-effect, then the
            completed program is returned. Otherwise, nothing is
            returned.
        """
        program_id = None
        program = None
        for identifier in ids:
            # Obligations get accumulated separately, but we
            # need to know to which lemma (program) they ultimately
            # correspond.
            m = OBLIGATION_ID_PATTERN.match(identifier)
            if m is not None:
                if program_id is None:
                    # only capture the first obligation as a proof block
                    proof_stack = self.partial_proof_stacks.setdefault(
                        identifier,
                        [])
                    proof_stack.append(
                        (sentence,
                         pre_goals_or_diff,
                         command_type))
                program_id = typing.cast(str, m['proof_id'])
                self.obligation_map[identifier] = program_id
        if program_id is not None:
            self._ensure_program_is_conjecture(program_id)
            if program_id in ids:
                # we completed the program
                if self.pre_proof_id is None:
                    self.pre_proof_id = program_id
                program = self._conclude_proof(
                    ids,
                    False,
                    get_identifiers,
                    feedback)
        return program

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
        candidates: List[str] = []
        for new_id in ids:
            match = OBLIGATION_ID_PATTERN.match(new_id)
            if match is None:
                # if an ID was generated that is not an obligation, then
                # it must be the program
                candidates.append(new_id)
        if candidates:
            assert len(candidates) == 1, \
                "A program can only emit IDs for itself or obligations"
            program_id = candidates.pop()
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
            self._ensure_program_is_conjecture(program_id)
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

    def extract_vernac_commands(
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
        with self as sentence_extractor:
            for sentence in sentences:
                # TODO: Optionally filter queries out of results (and
                # execution)
                try:
                    sentence_extractor(sentence)
                except CoqExn as e:
                    raise CoqExn(
                        e.msg,
                        e.full_sexp,
                        sentence.location,
                        sentence.text,
                        e.query) from e
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
        matched_id = None if match is None else match['proof_id']
        return (
            matched_id is not None
            and (matched_id == proof_id or matched_id == "legacy_pe"))
