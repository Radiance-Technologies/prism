"""
Tools for handling repair mining cache.
"""
import glob
import os
import re
import subprocess
import tempfile
import warnings
from dataclasses import InitVar, dataclass, field, fields
from functools import reduce
from itertools import chain
from multiprocessing.managers import BaseManager
from pathlib import Path
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Protocol,
    Set,
    SupportsIndex,
    Tuple,
    TypeVar,
    Union,
    cast,
    overload,
    runtime_checkable,
)

import networkx as nx
import setuptools_scm
import seutil as su

from prism.interface.coq.goals import GoalLocation, Goals, GoalsDiff
from prism.interface.coq.ident import Identifier
from prism.language.gallina.analyze import SexpInfo
from prism.language.sexp.node import SexpNode
from prism.project.metadata import ProjectMetadata
from prism.util.iterable import split
from prism.util.opam.switch import OpamSwitch
from prism.util.opam.version import Version, VersionString
from prism.util.radpytools import PathLike
from prism.util.radpytools.dataclasses import default_field
from prism.util.serialize import Serializable

CommandType = str
_T = TypeVar('_T')


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


@dataclass
class VernacSentence:
    """
    A parsed sentence from a document.
    """

    text: str
    """
    Text of a sentence from a proof.
    """
    ast: str
    """
    The serialized AST derived from this sentence.

    Note that locations within this AST are not accurate with respect to
    the source document.
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
            get_identifiers: Optional[Callable[[str],
                                               List[Identifier]]]) -> None:
        """
        Ensure the AST is serialized and extract goal identifiers.
        """
        if isinstance(self.ast, SexpNode):
            self.ast = str(self.ast)
        goals_identifiers = {}
        if get_identifiers is not None and self.goals is not None:
            # get qualified goal and hypothesis identifiers
            if isinstance(self.goals, Goals):
                goals_iter = self.goals.goal_index_map().items()
            else:
                goals_iter = self.goals.added_goals
            for goal, goal_idxs in goals_iter:
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

    def referenced_identifiers(self) -> Set[str]:
        """
        Get the set of identifiers referenced by this sentence.
        """
        return {ident.string for ident in self.qualified_identifiers}

    def serialize(self, fmt: Optional[su.io.Fmt] = None) -> Dict[str, Any]:
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
                    value = su.io.deserialize(value, clz=tp)
                if f.init:
                    fvs = field_values
                else:
                    fvs = noninit_field_values
                fvs[field_name] = value
        result = cls(**field_values)
        for field_name, value in noninit_field_values.items():
            setattr(result, field_name, value)
        return result

    @staticmethod
    def sort_sentences(
            sentences: List['VernacSentence']) -> List['VernacSentence']:
        """
        Sort the given sentences by their location.

        Parameters
        ----------
        located_sentences : List[VernacSentence]
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
        return [s for _, s in sorted([(s.location, s) for s in sentences])]


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

    def serialize(self, fmt: Optional[su.io.Fmt] = None) -> Dict[str, Any]:
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
        the other or if its location starts before the other.
        """
        if not isinstance(other, VernacCommandData):
            return NotImplemented
        return (
            self.location.beg_charno < other.location.beg_charno
            or self.spanning_location() in other.spanning_location())

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

    def referenced_identifiers(self) -> Set[str]:
        """
        Get the set of identifiers referenced by this command.
        """
        return reduce(
            lambda x,
            y: x.union(y),
            (s.referenced_identifiers() for s in self.sorted_sentences()))

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
                'CoqDocumentData may only contain VernacCommandData')
        self.commands[idx] = item

    def __mul__(  # noqa: D105
            self,
            n: SupportsIndex) -> 'VernacCommandDataList':
        return VernacCommandDataList(self.commands * n)

    def append(self, item: Any) -> None:  # noqa: D102
        if not isinstance(item, VernacCommandData):
            raise TypeError(
                'CoqDocumentData may only contain VernacCommandData')
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
                            "Try patch_goals first and then try again.")
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
                'CoqDocumentData may only contain VernacCommandData')
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
        lines: List[str] = []
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
                    lines[-1] = lines[-1] + sentence_part
                else:
                    # place each part of sentence on new line
                    lines.append(sentence_part)
                    linenos.append(sentence_lineno)
        with open(filepath, "w") as f:
            f.write("\n".join(lines))

    def serialize(self, fmt: Optional[su.io.Fmt] = None) -> List[object]:
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


@dataclass
class ProjectBuildResult:
    """
    The result of building a project commit.

    The project environment and metadata are implicit.
    """

    exit_code: int
    """
    The exit code of the project's build command with
    implicit project metadata.
    """
    stdout: str
    """
    The standard output of the commit's build command with
    implicit project metadata.
    """
    stderr: str
    """
    The standard error of the commit's build command with
    implicit project metadata.
    """


@dataclass
class ProjectBuildEnvironment:
    """
    The environment in which a project's commit data was captured.
    """

    switch_config: OpamSwitch.Configuration
    """
    The configuration of the switch in which the commit's build command
    was invoked.
    """
    current_version: str = field(init=False)
    """
    The current version of this package.
    """
    SHA_regex: ClassVar[re.Pattern] = re.compile(r"\+g[0-9a-f]{5,40}")
    """
    A regular expression that matches Git commit SHAs.
    """
    describe_cmd: ClassVar[
        List[str]] = 'git describe --match="" --always --abbrev=40'.split()
    """
    A command that can retrieve the hash of the checked out commit.

    Note that this will fail if the package is installed.
    """

    def __post_init__(self):
        """
        Cache the commit of the coq-pearls repository.
        """
        try:
            self.current_version = setuptools_scm.get_version(
                __file__,
                search_parent_directories=True)
        except LookupError:
            from importlib.metadata import version
            self.current_version = version("coq-pearls")
        match = self.SHA_regex.search(self.current_version)
        self.switch_config = self.switch_config
        if match is not None:
            # replace abbreviated hash with full hash to guarantee
            # the hash remains unambiguous in the future
            try:
                current_commit = subprocess.check_output(
                    self.describe_cmd,
                    cwd=Path(__file__).parent).strip().decode("utf-8")
            except subprocess.CalledProcessError:
                warnings.warn(
                    "Unable to expand Git hash in version string. "
                    "Try installing `coq-pearls` in editable mode.")
            else:
                self.current_version = ''.join(
                    [
                        self.current_version[: match.start()],
                        current_commit,
                        self.current_version[match.end():]
                    ])


@dataclass
class ProjectCommitData(Serializable):
    """
    Data associated with a project commit.

    The data is expected to be precomputed and cached to assist with
    subsequent repair mining.
    """

    project_metadata: ProjectMetadata
    """
    Metadata that identifies the project name, commit, Coq version, and
    other relevant data for reproduction and of the cache.
    """
    command_data: VernacDict
    """
    A map from file names relative to the root of the project to the set
    of command results.
    Iterating over the map's keys should follow dependency order of the
    files, i.e., if file ``B`` depends on file ``A``, then ``A`` will
    appear in the iteration before ``B``.
    """
    file_dependencies: Optional[Dict[str, List[str]]] = None
    """
    An adjacency list containing the intraproject dependencies of each
    file listed in `command_data`.
    If file ``B`` depends on file ``A``, then ``A`` will appear in
    ``file_dependencies[B]``.
    """
    environment: Optional[ProjectBuildEnvironment] = None
    """
    The environment in which the commit was processed.
    """
    build_result: Optional[ProjectBuildResult] = None
    """
    The result of building the project commit in the `opam_switch` or
    None if building was not required to process the commit.
    """

    @property
    def commands(self) -> List[Tuple[str, VernacCommandData]]:
        """
        Get all of the commands in the project in canonical order.

        Each command is paired with the name of the file from which it
        originated.
        """
        commands = []
        for filename in self.files:
            commands.extend(
                [(filename,
                  c) for c in self.command_data[filename]])
        return commands

    @property
    def files(self) -> List[str]:
        """
        Return the list of Coq files in the project.

        If `file_dependencies` is set, then the files will be listed in
        dependency order. Otherwise, they will match the order of
        iteration of `command_data`.
        """
        if self.file_dependencies is not None:
            G = nx.DiGraph()
            for f, deps in self.file_dependencies.items():
                for dep in deps:
                    G.add_edge(f, dep)
            files = list(reversed(list(nx.topological_sort(G))))
        else:
            files = [k for k in self.command_data.keys()]
        return files

    @property
    def file_sizes(self) -> Dict[str, int]:
        """
        Get the number of commands in each file in this commit.
        """
        return {k: len(v) for k,
                v in self.command_data.items()}

    def diff_goals(self) -> None:
        """
        Diff goals in-place, removing consecutive `Goals` of sentences.
        """
        for _, commands in self.command_data.items():
            commands.diff_goals()

    def patch_goals(self) -> None:
        """
        Patch all goals in-place, removing `GoalsDiff`s from sentences.
        """
        for _, commands in self.command_data.items():
            commands.patch_goals()

    def sort_commands(self) -> None:
        """
        Sort the commands of each file in-place.
        """
        for commands in self.command_data.values():
            commands.commands.sort()

    def sorted_sentences(self) -> Dict[str, List[VernacSentence]]:
        """
        Get the sentences of each file sorted by location.

        Returns
        -------
        Dict[str, List[VernacSentence]]
            A map from file names relative to the project root to lists
            of sentences in each file in order of appearance.
        """
        result = {}
        for filename, commands in self.command_data.items():
            result[filename] = commands.sorted_sentences()
        return result

    def write_coq_project(self, dirpath: PathLike) -> None:
        """
        Dump Coq files in the structure of the original project commit.

        Parameters
        ----------
        dirpath : PathLike
            The directory in which to dump the cached commands.
            If the directory does not exist, it will be created.
            Note that any existing files that clash with file names in
            this object will be overwritten.
        """
        # TODO: dump a buildable project
        dirpath = Path(dirpath)
        dirpath.mkdir(parents=True, exist_ok=True)
        for filename, commands in self.command_data.items():
            commands.write_coq_file(dirpath / filename)


@dataclass
class CacheObjectStatus:
    """
    Dataclass storing status information for (project, commit, version).
    """

    project: str
    """
    Project that partially identifies this cache object
    """
    commit_hash: str
    """
    Commit hash that partially identifies this cache object
    """
    coq_version: str
    """
    Coq version that partially identifies this cache object
    """
    status: str
    """
    Status of the (project, commit_hash, coq_version) cache object. This
    string can take one of the following values:
        * success
        * build error
        * cache error
        * other error
    """


@runtime_checkable
class CoqProjectBuildCacheProtocol(Protocol):
    """
    Object regulating access to repair mining cache on disk.

    On-disk structure:

    Root/
    ├── Project 1/
    |   ├── Commit hash 1/
    |   |   ├── cache_file_1.yml
    |   |   ├── cache_file_2.yml
    |   |   └── ...
    |   ├── Commit hash 2/
    |   └── ...
    ├── Project 2/
    |   └── ...
    └── ...
    """

    root: Path = Path("")
    """
    Root folder of repair mining cache structure
    """
    fmt_ext: str = ""
    """
    The extension for the cache files that defines their format.
    """
    _default_coq_versions: Set[str] = {
        '8.9.1',
        '8.10.2',
        '8.11.2',
        '8.12.2',
        '8.13.2',
        '8.14.1',
        '8.15.2'
    }
    """
    Default coq versions to look for when getting cache status.
    """

    def __contains__(  # noqa: D105
            self,
            obj: Union[ProjectCommitData,
                       ProjectMetadata,
                       Tuple[str, str, str]]) -> bool:
        return self.contains(obj)

    @property
    def fmt(self) -> su.io.Fmt:
        """
        Get the serialization format with which to cache data.
        """
        return su.io.infer_fmt_from_ext(self.fmt_ext)

    def _contains_data(self, data: ProjectCommitData) -> bool:
        return self.get_path_from_data(data).exists()

    def _contains_fields(self, *fields: str) -> bool:
        return self.get_path_from_fields(*fields).exists()

    def _contains_metadata(self, metadata: ProjectMetadata) -> bool:
        return self.get_path_from_metadata(metadata).exists()

    def _write_kernel(
            self,
            cache_id: Union[ProjectCommitData,
                            ProjectMetadata,
                            Tuple[str,
                                  str,
                                  str]],
            block: bool,
            file_contents: Union[str,
                                 Serializable],
            suffix: Optional[str] = None) -> Optional[str]:
        r"""
        Write a message or object to a text file.

        Any existing file contents are overwritten.

        Parameters
        ----------
        cache_id : Union[ProjectCommitData, \
                         ProjectMetadata, \
                         Tuple[str, str, str]]
            An object that identifies the cache to which the
            `file_contents` should be written.
        block : bool
            If true, return a ``"write complete"`` message.
        file_contents : Union[str, Serializable]
            The contents to write or serialized to the file.
        suffix : Optional[str], optional
            An optional suffix (including file extension) that uniquely
            identifies the written file, by default None, which
            corresponds to the cached build data itself.

        Returns
        -------
        str or None
            If `block`, return ``"write complete"``; otherwise, return
            nothing

        Raises
        ------
        TypeError
            If `file_contents` is not a string or `Serializable`.
        """
        if not isinstance(file_contents, (str, Serializable)):
            raise TypeError(
                f"Cannot write object of type {type(file_contents)} to file")
        # standardize inputs to get_path
        if not isinstance(cache_id, tuple):
            cache_id = (cache_id,)
        data_path = self.get_path(*cache_id)
        cache_dir = data_path.parent
        if not cache_dir.exists():
            os.makedirs(str(cache_dir))
        # Ensure that we write atomically.
        # First, we write to a temporary file so that if we get
        # interrupted, we aren't left with a corrupted file.
        if suffix is None and isinstance(file_contents, Serializable):
            suffix = f".{self.fmt_ext}"
        data_path: Path = data_path.parent / (  # type: ignore
            data_path.stem + suffix)
        with tempfile.NamedTemporaryFile("w",
                                         delete=False,
                                         dir=self.root,
                                         encoding='utf-8') as f:
            if isinstance(file_contents, str):
                f.write(file_contents)
        if isinstance(file_contents, Serializable):
            file_contents.dump(f.name, self.fmt)
        # Then, we atomically move the file to the correct, final
        # path.
        os.replace(f.name, data_path)
        if block:
            return "write complete"
        else:
            return None

    def contains(
        self,
        obj: Union[ProjectCommitData,
                   ProjectMetadata,
                   Tuple[str,
                         str,
                         str]]
    ) -> bool:
        """
        Return whether an entry on disk exists for the given data.

        Parameters
        ----------
        obj : Union[ProjectCommitData, ProjectMetadata, Tuple[str]]
            An object that identifies a project commit's cache.

        Returns
        -------
        bool
            Whether data for the given object is already cached on disk.

        Raises
        ------
        TypeError
            If the object is not a `ProjectCommitData`,
            `ProjeceMetadata`, or iterable of fields.
        """
        if isinstance(obj, ProjectCommitData):
            return self._contains_data(obj)
        elif isinstance(obj, ProjectMetadata):
            return self._contains_metadata(obj)
        elif isinstance(obj, Iterable):
            return self._contains_fields(*obj)
        else:
            raise TypeError(f"Arguments of type {type(obj)} not supported.")

    def get(
            self,
            project: str,
            commit: str,
            coq_version: str) -> ProjectCommitData:
        """
        Fetch a data object from the on-disk folder structure.

        Parameters
        ----------
        project : str
            The name of the project
        commit : str
            The commit hash to fetch from
        coq_version : str
            The Coq version

        Returns
        -------
        ProjectCommitData
            The fetched cache object

        Raises
        ------
        ValueError
            If the specified cache object does not exist on disk
        """
        data_path = self.get_path_from_fields(project, commit, coq_version)
        if not data_path.exists():
            raise ValueError(f"No cache file exists at {data_path}.")
        else:
            data = ProjectCommitData.load(data_path)
            return data

    def get_path(self, *args, **kwargs):
        """
        Get the file path for arguments identifying a cache.

        This function serves as an alias for each of
        `get_path_from_data`, `get_path_from_metadata`, and
        `get_path_from_fields`.
        """
        if len(args) == 1:
            data = args[0]
            if isinstance(data, ProjectCommitData):
                path = self.get_path_from_data(data, **kwargs)
            elif isinstance(data, ProjectMetadata):
                path = self.get_path_from_metadata(data, **kwargs)
            else:
                path = self.get_path_from_fields(*args, **kwargs)
        elif 'data' in kwargs:
            path = self.get_path_from_data(**kwargs)
        elif 'metadata' in kwargs:
            path = self.get_path_from_metadata(**kwargs)
        else:
            path = self.get_path_from_fields(*args, **kwargs)
        return path

    def get_path_from_data(self, data: ProjectCommitData) -> Path:
        """
        Get the file path for a given project commit cache.
        """
        return self.get_path_from_metadata(data.project_metadata)

    def get_path_from_fields(
            self,
            project: str,
            commit: str,
            coq_version: str) -> Path:
        """
        Get the file path for identifying fields of a cache.
        """
        return self.root / project / commit / '.'.join(
            [coq_version.replace(".",
                                 "_"),
             self.fmt_ext])

    def get_path_from_metadata(self, metadata: ProjectMetadata) -> Path:
        """
        Get the file path for a given metadata.
        """
        return self.get_path_from_fields(
            metadata.project_name,
            metadata.commit_sha,
            metadata.coq_version)

    def get_status(self, *args, **kwargs) -> Optional[str]:
        """
        Get the status of an indicated cache object.

        Parameters
        ----------
        args
            Positional arguments to `get_path`.
        kwargs
            Keyword arguments to `get_path`.

        Returns
        -------
        Optional[str]
            A string describing the status of the cached object or None
            if the arguments do not describe an object in the cache.
        """
        path = self.get_path(*args, **kwargs)
        prefix = str(path.with_suffix(''))
        if Path(prefix + "_cache_error.txt").exists():
            status_msg = "cache error"
        elif Path(prefix + "_build_error.txt").exists():
            status_msg = "build error"
        elif Path(prefix + "_misc_error.txt").exists():
            status_msg = "other error"
        elif path.exists():
            status_msg = "success"
        else:
            status_msg = None
        return status_msg

    def list_projects(self) -> List[str]:
        """
        Generate a list of projects in cache.

        Returns
        -------
        List[str]
            A list of project names currently present in the cache
        """
        projects: List[str] = []
        for item in glob.glob(f"{str(self.root)}/*"):
            if Path(item).is_dir():
                projects.append(Path(item).stem)
        return projects

    def list_commits(
            self,
            projects: Optional[Iterable[str]] = None) -> Dict[str,
                                                              List[str]]:
        """
        Generate a list of commits for a given project or all projects.

        Parameters
        ----------
        projects : Optional[Iterable[str]], optional
            The projects to get commit hashes for. If None, return
            commit hashes for all projects, by default None.

        Returns
        -------
        Dict[str, List[str]]
            Mapping from project name to commit hash list
        """
        if projects is None:
            projects = self.list_projects()
        elif not isinstance(projects, Iterable):
            projects = [projects]
        output_dict = dict()
        for project in projects:
            commit_list: List[str] = []
            for item in glob.glob(f"{self.root / project}/*"):
                if Path(item).is_dir():
                    commit_list.append(Path(item).stem)
            output_dict[project] = commit_list
        return output_dict

    def list_status(
        self,
        projects: Optional[Iterable[str]] = None,
        commits: Optional[Dict[str,
                               List[str]]] = None,
        coq_versions: Optional[Iterable[Union[Version,
                                              VersionString]]] = None
    ) -> List[CacheObjectStatus]:
        """
        Generate a list of objects detailing cache status.

        Parameters
        ----------
        project : Optional[Iterable[str]], optional
            If given, return status for these projects only, by default
            None
        commit : Optional[Dict[str, List[str]]], optional
            If given, return status for these commit hashes only, by
            default None
        coq_versions : Optional[Iterable[Version]], optional
            If given, return status for these coq versions only, by
            default None

        Returns
        -------
        List[CoqVersionStatus]
            List of objects detailing cache status
        """
        if projects is None:
            projects = self.list_projects()
        if commits is None:
            commits = self.list_commits(projects)
        if coq_versions is None:
            coq_version_strs = self._default_coq_versions
        else:
            coq_version_strs = {str(v) for v in coq_versions}
        status_list = []
        for coq_version_str in coq_version_strs:
            coq_version = coq_version_str.replace(".", "_")
            for project in projects:
                for commit in commits[project]:
                    status_msg = self.get_status(project, commit, coq_version)
                    if status_msg is not None:
                        status_list.append(
                            CacheObjectStatus(
                                project,
                                commit,
                                coq_version_str,
                                status_msg))
        return status_list

    def list_status_failed_only(self,
                                *args,
                                **kwargs) -> List[CacheObjectStatus]:
        """
        Generate a list of objects detailing cache status, errors only.

        Returns
        -------
        List[CoqVersionStatus]
            List of objects detailing cache status
        """
        return list(
            filter(
                lambda x: x.status != "success",
                self.list_status(*args,
                                 **kwargs)))

    def list_status_success_only(self,
                                 *args,
                                 **kwargs) -> List[CacheObjectStatus]:
        """
        Generate a list of objects detailing cache status, success only.

        Returns
        -------
        List[CoqVersionStatus]
            List of objects detailing cache status
        """
        return list(
            filter(
                lambda x: x.status == "success",
                self.list_status(*args,
                                 **kwargs)))

    def write(self,
              data: ProjectCommitData,
              block: bool = True,
              _=None) -> Optional[str]:
        """
        Write to build cache.

        Parameters
        ----------
        data : ProjectCommitData
            Data to write to build cache
        block : bool
            If true, return a ``"write complete"`` message.

        Returns
        -------
        str or None
            If `block`, return ``"write complete"``; otherwise, return
            nothing

        Notes
        -----
        The final `_` parameter in the definition is provided for
        compatibility with the other write methods.
        """
        return self._write_kernel(data, block, data)

    def write_build_error_log(
            self,
            metadata: ProjectMetadata,
            block: bool,
            build_result: ProjectBuildResult) -> Optional[str]:
        """
        Write build error log to build cache directory.

        Parameters
        ----------
        metadata : ProjectMetadata
            Metadata for the project that had an error. Used by this
            method to get the correct path to write to.
        block : bool
            If true, return a ``"write complete"`` message.
        build_result : str
            A triple containing a presumed nonzero exit code, stdout,
            and stderr, in that order.

        Returns
        -------
        str or None
            If `block`, return ``"write complete"``; otherwise, return
            nothing
        """
        str_to_write = "\n".join(
            [
                f"@@Exit code@@\n{build_result.exit_code}",
                f"@@stdout@@\n{build_result.stdout}",
                f"@@stderr@@\n{build_result.stderr}"
            ])
        return self._write_kernel(
            metadata,
            block,
            str_to_write,
            "_build_error.txt")

    def write_cache_error_log(
            self,
            metadata: ProjectMetadata,
            block: bool,
            cache_error_log: str) -> Optional[str]:
        """
        Write caching error log to build cache directory.

        Parameters
        ----------
        metadata : ProjectMetadata
            Metadata for the project that had an error. Used by this
            method to get the correct path to write to.
        block : bool
            If true, return a ``"write complete"`` message.
        cache_error_log : str
            Caching error log string to write to file.

        Returns
        -------
        str or None
            If `block`, return ``"write complete"``; otherwise, return
            nothing
        """
        return self._write_kernel(
            metadata,
            block,
            cache_error_log,
            "_cache_error.txt")

    def write_misc_error_log(
            self,
            metadata: ProjectMetadata,
            block: bool,
            misc_log: str) -> Optional[str]:
        """
        Write miscellaneous error log to build cache directory.

        Parameters
        ----------
        metadata : ProjectMetadata
            Metadata for the project that had an error. Used by this
            method to get the correct path to write to.
        block : bool
            If true, return a "write complete" message
        misc_log : str
            Miscellaneous error message to write to file.

        Returns
        -------
        str or None
            If `block`, return "write complete"; otherwise, return
            nothing
        """
        return self._write_kernel(metadata, block, misc_log, "_misc_error.txt")

    def write_timing_log(
            self,
            metadata: ProjectMetadata,
            block: bool,
            timing_log: str) -> Optional[str]:
        """
        Write timing log to build cache directory.

        Parameters
        ----------
        metadata : ProjectMetadata
            Metadata for the project that had an error. Used by this
            method to get the correct path to write to.
        block : bool
            If true, return a "write complete" message
        timing_log : str
            Timing log string to write to file.

        Returns
        -------
        str or None
            If `block`, return "write complete"; otherwise, return
            nothing
        """
        return self._write_kernel(metadata, block, timing_log, "_timing.txt")


class CoqProjectBuildCache(CoqProjectBuildCacheProtocol):
    """
    Implementation of CoqProjectBuildCacheProtocol with added __init__.
    """

    def __init__(self, root: PathLike, fmt_ext: str = "yml"):
        self.root = Path(root)
        self.fmt_ext = fmt_ext
        if not self.root.exists():
            os.makedirs(self.root)


class CoqProjectBuildCacheServer(BaseManager):
    """
    A BaseManager-derived server for managing build cache.
    """


CoqProjectBuildCacheServer.register(
    "CoqProjectBuildCache",
    CoqProjectBuildCache)


def CoqProjectBuildCacheClient(
        server: CoqProjectBuildCacheServer,
        *args,
        **kwargs):
    """
    Return client object for writing build cache.
    """
    return server.CoqProjectBuildCache(*args, **kwargs)  # type: ignore
