"""
Common types related to cached data.
"""

import warnings
from dataclasses import InitVar, dataclass, field, fields
from functools import reduce
from itertools import chain
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Set,
    SupportsIndex,
    Tuple,
    TypeVar,
    Union,
    cast,
    overload,
)

import seutil as su

from prism.interface.coq.goals import GoalLocation, Goals, GoalsDiff
from prism.interface.coq.ident import Identifier
from prism.language.gallina.analyze import SexpInfo
from prism.language.heuristic.parser import CoqComment, CoqSentence
from prism.language.sexp.node import SexpNode
from prism.util.io import Fmt
from prism.util.iterable import split
from prism.util.radpytools.dataclasses import default_field
from prism.util.radpytools.path import PathLike

CommandType = str
_T = TypeVar('_T')
_VernacSentence = TypeVar('_VernacSentence', bound='VernacSentence')


@dataclass
class HypothesisIndentifiers:
    """
    The identifers contained in an implicit `Hypothesis`.
    """

    term: Optional[List[Identifier]]
    """
    A list of fully qualified identifiers contained within the
    serialized AST of an hypothesis' term in the order of their
    appearance.
    None if the hypothesis has no `term` attribute.
    """
    type: List[Identifier]
    """
    A list of fully qualified identifiers contained within the
    serialized AST of an hypothesis' type in the order of their
    appearance.
    """

    def shallow_copy(self) -> 'HypothesisIndentifiers':
        """
        Get a shallow copy of this structure and its fields.
        """
        return HypothesisIndentifiers(
            list(self.term) if self.term is not None else None,
            list(self.type))


@dataclass
class GoalIdentifiers:
    """
    The identifiers contained in an implicit `Goal`.
    """

    goal: List[Identifier]
    """
    A list of fully qualified identifiers contained within the
    serialized AST of an goal's type in the order of their
    appearance.
    """
    hypotheses: List[HypothesisIndentifiers]
    """
    A list of fully qualified identifiers contained within each of the
    `goal`'s hypotheses.
    """

    def shallow_copy(self) -> 'GoalIdentifiers':
        """
        Get a shallow copy of this structure and its fields.
        """
        return GoalIdentifiers(
            list(self.goal),
            [h.shallow_copy() for h in self.hypotheses])


@dataclass
class VernacSentence:
    """
    A parsed sentence from a document.
    """

    _primitive_fields: ClassVar[Set[str]] = {
        'text',
        'ast',
        'command_type',
        'feedback'
    }
    """
    Attributes that do not require deserialization processing
    """

    text: str
    """
    The text of this sentence.
    """
    ast_: InitVar[Union[str, SexpNode]]
    """
    The AST derived from this sentence.
    """
    ast: str = field(init=False)
    """
    The serialized AST derived from this sentence.

    Note that locations within this AST are not accurate with respect to
    the source document but are instead expected to be relative to the
    sentence's whitespace-normalized `text`.
    """
    qualified_identifiers: List[Identifier]
    """
    A list of fully qualified identifiers contained within the
    serialized AST in the order of their appearance.
    """
    location: SexpInfo.Loc
    """
    The location of this sentence within the source document.
    """
    command_type: CommandType
    """
    The Vernacular type of command, e.g., VernacInductive.
    """
    goals: Optional[Union[Goals, GoalsDiff]] = None
    """
    Open goals, if any, prior to the execution of this sentence.

    This is especially useful for capturing the context of commands
    nested within proofs.
    """
    get_identifiers: InitVar[Optional[Callable[[str], List[Identifier]]]] = None
    """
    A function that accepts a serialized AST and returns a list of
    fully qualified identifiers in the order of their appearance in the
    AST.
    """
    feedback: List[str] = default_field([])
    """
    Feedback obtained from Coq upon execution of this sentence.

    Feedback may include diagnostic messages such as warnings.
    """
    goals_qualified_identifiers: Dict[GoalLocation,
                                      GoalIdentifiers] = field(init=False)
    """
    An enumeration of fully qualified identifiers contained in each goal
    and its hypotheses, each in the order of their appearance.
    """
    command_index: Optional[int] = None
    """
    The index of the Vernacular command in which this sentence partakes
    either as the command itself or part of an associated proof.

    Note that this index should not be relied upon in general to give a
    canonical index of the command.
    Instead, one should get a canonical index from
    `ProjectCommitData.commands` or a list of commands sorted by
    location.
    This attribute does not get serialized.
    """

    def __post_init__(
            self,
            ast_: Union[str,
                        SexpNode],
            get_identifiers: Optional[Callable[[str],
                                               List[Identifier]]]) -> None:
        """
        Ensure the AST is serialized and extract goal identifiers.
        """
        if isinstance(ast_, SexpNode):
            ast_ = str(ast_)
        self.ast = ast_
        goals_identifiers = {}
        if get_identifiers is not None and self.goals is not None:
            # get qualified goal and hypothesis identifiers
            if isinstance(self.goals, Goals):
                goals_iter = self.goals.goal_index_map().items()
            else:
                goals_iter = self.goals.added_goals
            for goal, goal_idxs in goals_iter:
                if goal.sexp is None:
                    continue
                gids = GoalIdentifiers(
                    get_identifiers(goal.sexp),
                    [
                        HypothesisIndentifiers(
                            get_identifiers(h.term_sexp)
                            if h.term_sexp is not None else None,
                            get_identifiers(h.type_sexp))
                        for h in goal.hypotheses
                    ])
                for goal_idx in goal_idxs:
                    goals_identifiers[goal_idx] = gids
        self.goals_qualified_identifiers = goals_identifiers

    def __lt__(self, other: object) -> bool:
        """
        Compare based on location.
        """
        if not isinstance(other, VernacSentence):
            return NotImplemented
        return self.location < other.location

    def __repr__(self) -> str:  # noqa: D105
        return f"VernacSentence(text={self.text}, location={self.location})"

    def discard_data(self) -> None:
        """
        Remove extracted data from the sentence.

        Only the sentence's text and location are guaranteed to remain.
        Note that this operation is performed in-place.
        """
        self.goals = None
        self.ast = ""
        self.feedback = []
        self.qualified_identifiers = []
        self.goals_qualified_identifiers = {}
        self.command_index = None

    def referenced_identifiers(self) -> Set[str]:
        """
        Get the set of identifiers referenced by this sentence.
        """
        return {ident.string for ident in self.qualified_identifiers}

    def serialize(self, fmt: Optional[Fmt] = None) -> Dict[str, Any]:
        """
        Serialize this configuration.

        By default, ignores non-derived fields indicating the switch
        name, root, and whether it is a clone.
        """
        serialized = {
            f.name: su.io.serialize(getattr(self,
                                            f.name),
                                    fmt) for f in fields(self)
        }
        # remove non-derived configuration information
        serialized.pop('command_index', None)
        return serialized

    def shallow_copy(self: _VernacSentence) -> _VernacSentence:
        """
        Get a shallow copy of this structure and its fields.
        """
        result = type(self)(
            self.text,
            self.ast,
            list(self.qualified_identifiers),
            self.location,
            self.command_type,
            self.goals.shallow_copy() if self.goals is not None else None,
            None,
            list(self.feedback),
            self.command_index)
        result.goals_qualified_identifiers = {
            k: v.shallow_copy() for k,
            v in self.goals_qualified_identifiers.items()
        }
        return result

    def to_CoqSentence(self) -> CoqSentence:
        """
        Return a `CoqSentence` consistent with this `VernacSentence`.
        """
        return CoqSentence(self.text, self.location, self.ast)

    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> 'VernacSentence':
        """
        Deserialize the `VernacSentence` from a dictionary.

        Parameters
        ----------
        data : Dict[str, Any]
            The serialized storage as yielded from `su.io.serialize`.

        Returns
        -------
        VernacSentence
            The deserialized sentence.
        """
        field_values: Dict[str,
                           Any] = {}
        noninit_field_values: Dict[str,
                                   Any] = {}
        for f in fields(cls):
            field_name = f.name
            if field_name in data:
                value = data[field_name]
                if value is not None:
                    if field_name == "goals":
                        if "added_goals" in value:
                            tp = GoalsDiff
                        else:
                            tp = Goals
                    else:
                        tp = f.type
                    if field_name not in cls._primitive_fields:
                        value = su.io.deserialize(value, clz=tp)
                if f.init:
                    fvs = field_values
                else:
                    fvs = noninit_field_values
                fvs[field_name] = value
                if field_name == "ast":
                    field_values["ast_"] = value
        result = cls(**field_values)
        for field_name, value in noninit_field_values.items():
            setattr(result, field_name, value)
        return result

    @staticmethod
    def sort_sentences(
            sentences: Iterable['VernacSentence']) -> List['VernacSentence']:
        """
        Sort the given sentences by their location.

        Parameters
        ----------
        located_sentences : Iterable[VernacSentence]
            A list of sentences presumed to come from the same document.

        Returns
        -------
        List['VernacSentence']
            The sentences sorted by their location in the document in
            ascending order.

        Notes
        -----
        Sorting is done purely based on character numbers, so sentences
        from different documents can still be sorted together (although
        the significance of the results may be suspect).
        """
        return sorted(sentences)


@dataclass
class ProofSentence(VernacSentence):
    """
    Type associating individual proof sentences to ASTs and open goals.
    """

    proof_index: Optional[int] = None
    """
    The index of the proof in which this sentence resides.

    For example, a ``Program`` may have multiple proofs, one for each
    outstanding ``Obligation``.

    This attribute does not get serialized.
    See `VernacSentence.command_index`.
    """
    proof_step_index: Optional[int] = None
    """
    The index of this sentence within the body of its surrounding proof.

    This attribute does not get serialized.
    See `VernacSentence.command_index`.
    """

    def __repr__(self) -> str:  # noqa: D105
        return f"ProofSentence(text={self.text}, location={self.location})"

    def discard_data(self) -> None:  # noqa: D102
        super().discard_data()
        self.proof_index = None
        self.proof_step_index = None

    def serialize(self, fmt: Optional[Fmt] = None) -> Dict[str, Any]:
        """
        Serialize this configuration.

        By default, ignores non-derived fields indicating the switch
        name, root, and whether it is a clone.
        """
        serialized = super().serialize(fmt)
        # remove non-derived configuration information
        serialized.pop('proof_index', None)
        serialized.pop('proof_step_index', None)
        return serialized


Proof = List[ProofSentence]


@dataclass
class VernacCommandData:
    """
    The evaluated result for a single Vernacular command.
    """

    identifier: List[str]
    """
    Identifier(s) for the command being cached, e.g., the name of the
    corresponding theorem, lemma, or definition.
    If no identifier exists (for example, if it is an import statement)
    or can be meaningfully defined, then an empty list.
    """
    command_error: Optional[str]
    """
    The error, if any, that results when trying to execute the command
    (e.g., within ``sertop``). If there is no error, then None.
    """
    command: VernacSentence
    """
    The Vernacular command.
    """
    proofs: List[Proof] = default_field(list())
    """
    Associated proofs, if any.
    Proofs are considered to be a list of proof blocks, each dealing
    with a separate obligation of the conjecture stated in `command`.
    Tactics and goals are captured here.
    """

    def __hash__(self) -> int:  # noqa: D105
        # do not include the error
        return hash((self.identifier, self.command_type, self.location))

    def __lt__(self, other: 'VernacCommandData') -> bool:
        """
        Compare two commands based on location.

        One command is less than another if its location is a subset of
        the other or if its location ends before the other.
        """
        if not isinstance(other, VernacCommandData):
            return NotImplemented
        return self.spanning_location() < other.spanning_location()

    def __repr__(self) -> str:  # noqa: D105
        return ''.join(
            [
                f"VernacCommandData(identifier={self.identifier}, ",
                f"command={repr(self.command)}, ",
                f"command_error={self.command_error})"
            ])

    @property
    def command_type(self) -> str:
        """
        Get the type of the Vernacular command.
        """
        return self.command.command_type

    @property
    def location(self) -> SexpInfo.Loc:
        """
        Get the location of the command in the original source document.
        """
        return self.command.location

    def all_text(self) -> str:
        """
        Get all of the text of this command, including any subproofs.

        Each sentence in the command is joined by newlines in the
        result.
        """
        return '\n'.join(s.text for s in self.sorted_sentences())

    def discard_data(self) -> None:
        """
        Remove extracted data from the command.

        Only the text and location of each of the command's constituent
        sentences are guaranteed to remain. Note that this operation is
        performed in-place.
        """
        for sentence in self.sentences_iter():
            sentence.discard_data()

    def proof_text(self) -> str:
        """
        Get the text of this command's proof(s), if any.

        Each sentence in the proof(s) is joined by newlines in the
        result. If this command does not have a proof, then the result
        will be an empty string.
        """
        return '\n'.join(
            s.text for s in VernacSentence.sort_sentences(chain(*self.proofs)))

    def referenced_identifiers(self) -> Set[str]:
        """
        Get the set of identifiers referenced by this command.
        """
        return reduce(
            lambda x,
            y: x.union(y),
            (s.referenced_identifiers() for s in self.sorted_sentences()))

    def relocate(self, new_location: SexpInfo.Loc) -> Tuple[int, int]:
        """
        Shift this command's location to the start of the given one.

        Parameters
        ----------
        new_location : SexpInfo.Loc
            The new location on which to base this command, presumed to
            span the command and its proof(s).

        Returns
        -------
        num_excess_lines : int
            The number of lines in this command's current location in
            excess of the new location.
        num_excess_chars : int
            The number of characters in this command's current location
            in excess of the new location.
        """
        # NOTE: The bol_pos does not currently get shifted.
        if new_location.filename != self.location.filename:
            raise ValueError(
                "Cannot shift location to another file. "
                f"Expected {self.location.filename}, got {new_location.filename}"
            )
        # we assume that the command's location precedes any
        # part of its proof
        line_shift = new_location.lineno - self.location.lineno
        char_shift = new_location.beg_charno - self.location.beg_charno
        # TODO: shift bol_pos as well
        self.shift_location(line_shift, char_shift)
        # calculate extra shift due to the new location being smaller
        spanning_location = self.spanning_location()
        num_excess_lines = max(
            0,
            spanning_location.lineno_last - new_location.lineno_last)
        num_excess_chars = max(
            0,
            spanning_location.end_charno - new_location.end_charno)
        return num_excess_lines, num_excess_chars

    def sentences_iter(self) -> Iterator[VernacSentence]:
        """
        Get an iterator over the command's sentences.

        The order of iteration is not guaranteed to be consistent.
        """
        yield from chain(
            [self.command],
            (sentence for proof in self.proofs for sentence in proof))

    def shallow_copy(self) -> 'VernacCommandData':
        """
        Get a shallow copy of this structure and its fields.
        """
        return VernacCommandData(
            [s for s in self.identifier],
            self.command_error,
            self.command.shallow_copy(),
            [[s.shallow_copy() for s in p] for p in self.proofs])

    def shift_location(self, line_offset: int, char_offset: int) -> None:
        """
        Shift the location of the command and its proof by some offset.
        """
        self.command.location = self.command.location.shift(
            char_offset,
            line_offset)
        for proof in self.proofs:
            for proof_sentence in proof:
                proof_sentence.location = proof_sentence.location.shift(
                    char_offset,
                    line_offset)

    def sorted_sentences(
            self,
            attach_proof_indexes: bool = False,
            command_idx: Optional[int] = None) -> List[VernacSentence]:
        """
        Get the sentences in this command sorted by their locations.

        A command may possess multiple sentences if it has any
        associated proofs.

        Parameters
        ----------
        attach_proof_indexes : bool, optional
            If True, add extra fields to proof sentences with proof and
            proof step indexes, by default False
        command_idx : int or None, optional
            If provided, attach a command index to all sentences
            including this command.
            Otherwise, use the current `command_index` of this
            `VernacCommandData`.
        """
        if command_idx is None:
            command_idx = self.command.command_index
        else:
            self.command.command_index = command_idx
        sentences = [self.command]
        for proof_idx, proof in enumerate(self.proofs):
            for sentence_idx, sentence in enumerate(proof):
                if attach_proof_indexes:
                    sentence.proof_index = proof_idx
                    sentence.proof_step_index = sentence_idx
                sentence.command_index = command_idx
                sentences.append(sentence)
        if len(sentences) > 1:
            return VernacSentence.sort_sentences(sentences)
        else:
            return sentences

    def spanning_location(self) -> SexpInfo.Loc:
        """
        Get a location spanning the command and any associated proofs.
        """
        return self.location.union(*[p.location for p in chain(*self.proofs)])

    def to_CoqSentences(self) -> List[CoqSentence]:
        """
        Get `CoqSentence`s consistent with this command.
        """
        return [s.to_CoqSentence() for s in self.sorted_sentences()]


@dataclass
class VernacCommandDataList:
    """
    A list of extracted Vernacular commands, e.g., from a Coq document.
    """

    # This could have simply been a subclass of list of seutil checked
    # for custom deserializers first instead of builtin types

    commands: List[VernacCommandData] = default_field(list())

    @overload
    def __add__(  # noqa: D105
            self,
            o: List[VernacCommandData]
    ) -> 'VernacCommandDataList':
        ...

    @overload
    def __add__(  # noqa: D105
        self,
        o: List[_T]) -> Union[List[Union[_T,
                                         VernacCommandData]],
                              'VernacCommandDataList']:
        ...

    def __add__(  # noqa: D105
        self,
        o: Union[List[_T],
                 List[VernacCommandData]]
    ) -> Union[List[Union[_T,
                          VernacCommandData]],
               'VernacCommandDataList']:
        result = self.commands + o
        if all(isinstance(i, VernacCommandData) for i in o):
            result = cast(List[VernacCommandData], result)
            return self.__class__(result)
        else:
            result = cast(List[Union[_T, VernacCommandData]], result)
            return result

    def __contains__(self, item: Any) -> bool:  # noqa: D105
        return item in self.commands

    def __delitem__(self, item: SupportsIndex) -> None:  # noqa: D105
        del self.commands[item]

    def __getattribute__(self, name: str) -> Any:
        """
        Pass through attribute accesses to internal list.
        """
        try:
            return super().__getattribute__(name)
        except AttributeError:
            return getattr(super().__getattribute__('commands'), name)

    @overload
    def __getitem__(  # noqa: D105
            self,
            item: SupportsIndex) -> VernacCommandData:
        ...

    @overload
    def __getitem__(self, item: slice) -> 'VernacCommandDataList':  # noqa: D105
        ...

    def __getitem__(  # noqa: D105
        self,
        item: Union[SupportsIndex,
                    slice]) -> Union[VernacCommandData,
                                     'VernacCommandDataList']:
        result = self.commands[item]
        if not isinstance(item, SupportsIndex):
            result = cast(List[VernacCommandData], result)
            return self.__class__(result)
        else:
            result = cast(VernacCommandData, result)
            return result

    def __iter__(self) -> Iterator[VernacCommandData]:  # noqa: D105
        return iter(self.commands)

    def __len__(self) -> int:  # noqa: D105
        return len(self.commands)

    def __setitem__(self, idx: SupportsIndex, item: Any) -> None:  # noqa: D105
        if not isinstance(item, VernacCommandData):
            raise TypeError(
                'VernacCommandDataList may only contain VernacCommandData')
        self.commands[idx] = item

    def __mul__(  # noqa: D105
            self,
            n: SupportsIndex) -> 'VernacCommandDataList':
        return VernacCommandDataList(self.commands * n)

    def append(self, item: Any) -> None:  # noqa: D102
        if not isinstance(item, VernacCommandData):
            raise TypeError(
                'VernacCommandDataList may only contain VernacCommandData')
        self.commands.append(item)

    def copy(self) -> 'VernacCommandDataList':  # noqa: D102
        return self.__class__(self.commands.copy())

    def diff_goals(self) -> None:
        """
        Diff goals in-place, removing consecutive `Goals` of sentences.
        """
        previous_goals = None
        for sentence in self.sorted_sentences():
            current_goals = sentence.goals
            current_goal_identifiers = sentence.goals_qualified_identifiers
            if isinstance(current_goals, Goals):
                if isinstance(previous_goals, Goals):
                    goals_or_goals_diff = GoalsDiff.compute_diff(
                        previous_goals,
                        current_goals)
                    current_goal_identifiers = {
                        gidx: current_goal_identifiers[gidx] for _goal,
                        added_goal_locations in goals_or_goals_diff.added_goals
                        for gidx in added_goal_locations
                    }
                else:
                    if isinstance(previous_goals, GoalsDiff):
                        warnings.warn(
                            "Unable to compute diff with respect to existing diff. "
                            "Try patch_goals first and then try again.",
                            stacklevel=2)
                    goals_or_goals_diff = current_goals
            else:
                goals_or_goals_diff = current_goals
            sentence.goals = goals_or_goals_diff
            sentence.goals_qualified_identifiers = current_goal_identifiers
            previous_goals = current_goals

    def extend(self, items: Iterable[Any]) -> None:  # noqa: D102
        items = list(items)
        if any(not isinstance(item, VernacCommandData) for item in items):
            raise TypeError(
                'VernacCommandDataList may only contain VernacCommandData')
        self.commands.extend(items)

    def patch_goals(self) -> None:
        """
        Patch all goals in-place, removing `GoalsDiff`s from sentences.
        """
        previous_goals = None
        previous_goal_identifiers: Dict[GoalLocation,
                                        GoalIdentifiers] = {}
        for sentence in self.sorted_sentences():
            current_goals = sentence.goals
            current_goal_identifiers = sentence.goals_qualified_identifiers
            if isinstance(current_goals, GoalsDiff):
                assert previous_goals is not None, \
                    "previous_goals must be non-null for a diff to exist"
                # Patch goal identifiers
                # Silently fail if goal identifiers are missing
                added_goal_identifiers = current_goal_identifiers
                # make a copy to avoid modifying previous sentence's
                # goals
                current_goal_identifiers = dict(previous_goal_identifiers)
                # handle removed goals
                for removed_goal_location in current_goals.removed_goals:
                    current_goal_identifiers.pop(removed_goal_location, None)
                # handle moved goals
                for origin, destination in current_goals.moved_goals:
                    moved_goal = current_goal_identifiers.pop(origin, None)
                    if moved_goal is not None:
                        current_goal_identifiers[destination] = moved_goal
                # handle added goals
                current_goal_identifiers.update(added_goal_identifiers)
                # Patch goals
                current_goals = current_goals.patch(previous_goals)
            sentence.goals = current_goals
            sentence.goals_qualified_identifiers = current_goal_identifiers
            previous_goals = current_goals
            previous_goal_identifiers = current_goal_identifiers

    def pop(self) -> VernacCommandData:
        """
        Remove and return the last command from the list.
        """
        return self.commands.pop()

    def shallow_copy(self) -> 'VernacCommandDataList':
        """
        Get a shallow copy of this list.
        """
        return VernacCommandDataList([c.shallow_copy() for c in self])

    def sort(self) -> None:
        """
        Sort the list of commands in place.
        """
        self.commands.sort()

    def sorted_sentences(self) -> List[VernacSentence]:
        """
        Get the sentences of this file sorted by location.
        """
        sorted_sentences = []
        for idx, c in enumerate(self.commands):
            sorted_sentences.extend(
                c.sorted_sentences(attach_proof_indexes=True,
                                   command_idx=idx))
        sorted_sentences = VernacSentence.sort_sentences(sorted_sentences)
        return sorted_sentences

    def to_CoqSentences(self) -> List[CoqSentence]:
        """
        Get `CoqSentence`s consistent with this list of commands.
        """
        sentences = [s for c in self.commands for s in c.to_CoqSentences()]
        sentences.sort()
        return sentences

    def write_coq_file(self, filepath: PathLike) -> None:
        """
        Dump the commands to a Coq file at the given location.

        Parameters
        ----------
        filepath : PathLike
            The location at which the file should be dumped.
            Any file already at the given path will be overwritten.

        Notes
        -----
        While the dumped Coq file cannot match the original from which
        this data was extracted to to normalization of whitespace and
        comments, the line numbers on which each sentence is written
        should match the original Coq file.
        """
        lines: List[str] = [""]
        linenos: List[int] = [0]
        for sentence in self.sorted_sentences():
            while linenos[-1] < sentence.location.lineno:
                lines.append("")
                linenos.append(linenos[-1] + 1)
            # distribute sentence over lines
            sentence_linenos = range(
                sentence.location.lineno,
                sentence.location.lineno_last + 1)
            sentence_parts = split(sentence.text.split(), len(sentence_linenos))
            for sentence_lineno, sentence_part in zip(sentence_linenos, sentence_parts):
                sentence_part = " ".join(sentence_part)
                if linenos and sentence_lineno == linenos[-1]:
                    # sentence starts on same line as another ends
                    if lines:
                        if lines[-1]:
                            lines[-1] = " ".join([lines[-1], sentence_part])
                        else:
                            lines[-1] = sentence_part
                    else:
                        lines.append(sentence_part)
                else:
                    # place each part of sentence on new line
                    lines.append(sentence_part)
                    linenos.append(sentence_lineno)
        with open(filepath, "w") as f:
            f.write("\n".join(lines))

    def serialize(self, fmt: Optional[Fmt] = None) -> List[object]:
        """
        Serialize as a basic list.
        """
        return su.io.serialize(self.commands, fmt)

    @classmethod
    def deserialize(cls, data: object) -> 'VernacCommandDataList':
        """
        Deserialize from a basic list.
        """
        return VernacCommandDataList(
            su.io.deserialize(data,
                              clz=List[VernacCommandData]))


VernacDict = Dict[str, VernacCommandDataList]
CommentDict = Dict[str, List[CoqComment]]
