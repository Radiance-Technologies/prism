"""
Defines representations of repair instances (or examples).
"""

import copy
import typing
from dataclasses import dataclass, fields
from typing import (
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    Set,
    Type,
    TypeVar,
    Union,
)

import numpy as np

from prism.data.build_cache import (
    ProjectCommitData,
    VernacCommandData,
    VernacCommandDataList,
)
from prism.data.repair.align import (
    AlignedCommands,
    AlignmentFunction,
    align_commits,
    get_aligned_commands,
)
from prism.data.repair.diff import compute_git_diff
from prism.language.gallina.analyze import SexpInfo
from prism.util.diff import GitDiff
from prism.util.opam import OpamSwitch, PackageFormula
from prism.util.radpytools.dataclasses import Dataclass, default_field
from prism.util.serialize import (
    SerializableDataDiff,
    deserialize_generic_dataclass,
)


@dataclass
class LocDiff:
    """
    A relative change in a source code location.
    """

    after_filename: str
    """
    The name of the file containing the location after the change.
    """
    lineno_diff: int
    """
    The change in starting line number.
    """
    bol_pos_diff: int
    """
    The change in beginning line character index.
    """
    lineno_last_diff: int
    """
    The change in final line number.
    """
    bol_pos_last_diff: int
    """
    The change in final line character index.
    """
    beg_charno_diff: int
    """
    The change in beginning character number.
    """
    end_charno_diff: int
    """
    The change in ending character number.
    """

    def patch(self, loc: SexpInfo.Loc) -> SexpInfo.Loc:
        """
        Apply the change to a given location.

        Parameters
        ----------
        loc : SexpInfo.Loc
            A location.

        Returns
        -------
        SexpInfo.Loc
            A new location resulting from applying this diff to `loc`.
        """
        return SexpInfo.Loc(
            self.after_filename,
            loc.lineno + self.lineno_diff,
            loc.bol_pos + self.bol_pos_diff,
            loc.lineno_last + self.lineno_last_diff,
            loc.bol_pos_last + self.bol_pos_last_diff,
            loc.beg_charno + self.beg_charno_diff,
            loc.end_charno + self.end_charno_diff)

    @classmethod
    def compute_diff(cls, a: SexpInfo.Loc, b: SexpInfo.Loc) -> 'LocDiff':
        """
        Compute the difference between two locations.

        Parameters
        ----------
        a, b : SexpInfo.Loc
            Two locations from the same or different documents.

        Returns
        -------
        diff : LocDiff
            The difference between `a` and `b` such that
            ``diff.patch(a) == b``.
        """
        return LocDiff(
            b.filename,
            b.lineno - a.lineno,
            b.bol_pos - a.bol_pos,
            b.lineno_last - a.lineno_last,
            b.bol_pos_last - a.bol_pos_last,
            b.beg_charno - a.beg_charno,
            b.end_charno - a.end_charno)


@dataclass
class VernacCommandDataListDiff:
    """
    A change relative to a list of extracted Vernacular commands.

    Each enumerated change should be independent such that one can
    remove an element and obtain a valid diff.
    """

    added_commands: VernacCommandDataList = default_field(
        VernacCommandDataList())
    """
    A list of new Vernacular commands to be added to the file.
    These new commands are presumed to be completely novel and not arise
    from relocating commands from other files.
    """
    changed_commands: Dict[
        int,
        SerializableDataDiff[VernacCommandData]] = default_field({})
    """
    A map from command indices in the original file to commands that
    should replace the indexed commands.
    Note that the replacements may be located in other files.
    The commands are presumed to have been modified in form or content
    rather than simply relocated.
    """
    dropped_commands: Set[int] = default_field(set())
    """
    A set of command indices in the original file indicating commands
    that should be removed.
    """

    @property
    def is_empty(self) -> bool:
        """
        Return whether this diff is empty.
        """
        return not (
            self.added_commands or self.changed_commands
            or self.dropped_commands)


@dataclass
class ProjectCommitDataDiff:
    """
    A diff between two commits.

    Notes
    -----
    This diff is purely between the command elements of the
    `ProjectCommitData` and thus does not capture changes to the
    environment, metadata, or other fields of `ProjectCommitData`.
    """

    changes: Dict[str,
                  VernacCommandDataListDiff] = default_field({})
    """
    A map containing per-file changes.
    """

    @property
    def is_empty(self) -> bool:
        """
        Return whether this diff is empty.
        """
        return all([v.is_empty for v in self.changes.values()])

    def patch(self, data: ProjectCommitData) -> ProjectCommitData:
        """
        Apply this diff to given project data.

        Note that only the command elements of the `data` will be
        patched.

        Parameters
        ----------
        data : ProjectCommitData
            Extracted command data from a commit.

        Returns
        -------
        ProjectCommitData
            The patched commit data.
            Note that goals will be fully patched and expanded.
            Call `ProjectCommitData.diff_goals` on the result
        """
        # ensure goals are uncompressed
        data.patch_goals()
        result = copy.deepcopy(data)
        result_command_data = result.command_data
        # decompose moves and changes into drops and adds
        dropped_commands: Dict[str,
                               Set[int]] = {}
        added_commands: Dict[str,
                             VernacCommandDataList] = {}
        for filename, change in self.changes.items():
            # Set of commands to be dropped from original state.
            dropped = dropped_commands.setdefault(filename, set())
            dropped.update(change.dropped_commands)
            # Include added commands from diff being applied.
            added = added_commands.setdefault(filename, VernacCommandDataList())
            added.extend(change.added_commands)
            # decompose changes into drops and adds
            dropped.update(change.changed_commands.keys())
            for original_command_index, command_diff in change.changed_commands.items():
                # patch the original command
                original_command = data.command_data[filename][
                    original_command_index]
                command = command_diff.patch(original_command)
                added = added_commands.setdefault(
                    command.location.filename,
                    VernacCommandDataList())
                added.append(command)
        # Apply Changes
        # Drop commands. This results in:
        #   1) removal of commands removed by diff
        #   2) removal of commands moved by diff
        #      from original locations
        for filename, dropped in dropped_commands.items():
            # Get the command data from original file.
            try:
                command_data = result_command_data[filename]
            except KeyError:
                command_data = VernacCommandDataList()
                assert not dropped, "cannot drop commands from non-existent files"
                result_command_data[filename] = command_data
            # Create new command data without dropped commands
            command_data = VernacCommandDataList(
                [c for i,
                 c in enumerate(command_data) if i not in dropped])
            # Replace original command data with new one.
            # Empty command data implies the whole file was dropped.
            if not command_data:
                # the resulting file would be empty; remove it
                result_command_data.pop(filename, None)
            else:
                result_command_data[filename] = command_data
        # Apply Changes
        # Add commands. This results in:
        #   1) Add commands added by the diff.
        #   2) Add commands moved by the diff to their new locations.
        for filename, added in added_commands.items():
            try:
                command_data = result_command_data[filename]
            except KeyError:
                command_data = VernacCommandDataList()
                result_command_data[filename] = command_data
            command_data.extend((copy.deepcopy(c) for c in added))
            if not command_data:
                assert not added, "file cannot be empty if commands were added"
                # the resulting file would be empty; remove it
                result_command_data.pop(filename, None)
        return result

    @classmethod
    def from_aligned_commands(
            cls,
            aligned_commands: AlignedCommands) -> 'ProjectCommitDataDiff':
        """
        Create a diff from aligned commands of two implied commits.

        Parameters
        ----------
        aligned_commands : AlignedCommands
            A list of pairs of aligned commands between two commits.

        Returns
        -------
        diff : ProjectCommitDataDiff
            A diff between the implied commits consistent with the given
            alignment.
        """
        result = ProjectCommitDataDiff()
        changes = result.changes
        a_file_offsets: Dict[str,
                             int] = {}
        for a, _ in aligned_commands:
            if a is not None:
                aidx, filename, _ = a
            else:
                continue
            try:
                offset = a_file_offsets[filename]
            except KeyError:
                offset = aidx
            a_file_offsets[filename] = min(aidx, offset)
        for a, b in aligned_commands:
            if a is None:
                # added command
                assert b is not None, "cannot skip both sequences in alignment"
                _, filename, cmd = b
                file_diff = changes.setdefault(
                    filename,
                    VernacCommandDataListDiff())
                file_diff.added_commands.append(copy.deepcopy(cmd))
            elif b is None:
                # dropped command
                assert a is not None, "cannot skip both sequences in alignment"
                aidx, filename, _ = a
                offset = a_file_offsets[filename]
                file_diff = changes.setdefault(
                    filename,
                    VernacCommandDataListDiff())
                file_diff.dropped_commands.add(aidx - offset)
            else:
                # a command with a match
                aidx, filename, acmd = a
                _, _, bcmd = b
                offset = a_file_offsets[filename]
                file_diff = changes.setdefault(
                    filename,
                    VernacCommandDataListDiff())
                if acmd != bcmd:
                    # changed command
                    command_diff = SerializableDataDiff[
                        VernacCommandData].compute_diff(acmd,
                                                        bcmd)
                    file_diff.changed_commands[aidx - offset] = command_diff
                # else the command is unchanged and not in the diff
        return result

    @classmethod
    def from_alignment(
            cls,
            a: ProjectCommitData,
            b: ProjectCommitData,
            alignment: np.ndarray) -> 'ProjectCommitDataDiff':
        """
        Create a diff between two commits given a precomputed alignment.

        Parameters
        ----------
        a, b : ProjectCommitData
            Command data extracted from two commits of a project.
            The goals of each command will be patched in-place as a
            side-effect.
            Call ``a.diff_goals()`` and ``b.diff_goals()`` to compress
            them after alignment, if desired.
        alignment : np.ndarray
            A precomputed alignment between the commands of each project
            where ``(i,j)`` matches the ``i``-th command of `a` to the
            ``j``-th command of `b`.

        Returns
        -------
        diff : ProjectCommitDataDiff
            The diff between `a` and `b` such that
            ``diff.patch(a).command_data == b.command_data``.
        """
        a.patch_goals()
        b.patch_goals()
        diff = cls.from_aligned_commands(get_aligned_commands(a, b, alignment))
        return diff

    @classmethod
    def from_commit_data(
            cls,
            a: ProjectCommitData,
            b: ProjectCommitData,
            align: AlignmentFunction,
            diff: Optional[GitDiff] = None,
            compute_diff: bool = True) -> 'ProjectCommitDataDiff':
        """
        Create a diff between two commits.

        Parameters
        ----------
        a, b : ProjectCommitData
            Command data extracted from two commits of a project.
        align : AlignmentFunction
            A function to align the commands of `a` and `b`.
            If a `diff` is available, then the alignment is only applied
            to parts of each commit that intersect the `diff`.
        diff : Optional[GitDiff], optional
            A `diff` between the source code of each commit.
            If ``None`` and `compute_diff` is True, then a surrogate
            `diff` will be computed between the data in `a` and `b`.
            By default None.
        compute_diff : bool, optional
            If True, then compute a default `diff` when `diff` is None.
            Otherwise, do nothing such that `align` operates on the
            entirety of `a` and `b`, which may be expensive depending on
            the alignment algorithm.
            By default True.

        Returns
        -------
        ProjectCommitDataDiff
            The diff between `a` and `b` such that
            ``diff.patch(a).command_data == b.command_data``.
        """
        if diff is None and compute_diff:
            diff = compute_git_diff(a, b)
        if diff is not None:
            alignment = align_commits(a, b, diff, align)
        else:
            alignment = align(a, b)
        return cls.from_alignment(a, b, alignment)


T = TypeVar('T', bound=Dataclass)


def cast_from_base_cls(cls: Type[T], obj: T, base_cls: Type[T]) -> T:
    """
    Cast a value to a subclass of a given base dataclass.
    """
    if not isinstance(obj, cls):
        obj = cls(**{f.name: getattr(obj,
                                     f.name) for f in fields(base_cls)})
    return obj


_State = TypeVar("_State")
_Diff = TypeVar("_Diff")


@dataclass
class ProjectState(Generic[_State, _Diff]):
    """
    The state of a project.
    """

    project_state: _State
    """
    A representation of the state of the project.
    """
    offset: Optional[_Diff] = None
    """
    A set of changes relative to the `project_state`.

    This field is useful for representing working tree changes.
    """
    _environment: Optional[OpamSwitch.Configuration] = None
    """
    The environment in which the project is built.

    This field identifies other installed package versions including the
    Coq compiler.
    """

    @property
    def environment(self) -> Optional[OpamSwitch.Configuration]:
        """
        Get the environment for the state.
        """
        return self._environment

    @classmethod
    def deserialize(cls, data: object) -> 'ProjectState':
        """
        Deserialize a project state.

        Note that this only works for monomorphic subclasses.
        """
        return deserialize_generic_dataclass(data, cls, error="raise")


@dataclass
class ProjectStateDiff(Generic[_Diff]):
    """
    A change in some implicit project's state.
    """

    diff: _Diff
    """
    A refactor or other change to some implicit state.
    """
    environment: Optional[OpamSwitch.Configuration] = None
    """
    The changed environment.

    If None, then it is understood to be the same environment as the
    environment associatd with implicit state.
    """

    @classmethod
    def deserialize(cls, data: object) -> 'ProjectStateDiff':
        """
        Deserialize a project state diff.

        Note that this only works for monomorphic subclasses.
        """
        return deserialize_generic_dataclass(data, cls, error="raise")


@dataclass
class ErrorInstance(Generic[_State, _Diff]):
    """
    A concise example of an error.

    With this representation, one should be able to capture errors
    induced by changes to source code and/or environment.
    """

    project_name: str
    """
    An identifier that uniquely determines the project and is implicitly
    linked to a Git repository through some external correspondence.
    """
    initial_state: ProjectState[_State, _Diff]
    """
    An initial project state.

    A state of the project, nominally taken to be prior to a change that
    introduced a broken proof or other bug.
    """
    change: ProjectStateDiff[_Diff]
    """
    A refactor or other change that introduces an error when applied to
    the `initial_state`.

    If the diff is empty and the environment is None, then
    `initial_state` is understood to be broken.
    """
    error_location: Set[SexpInfo.Loc] = default_field(set())
    """
    A precise location for the error(s).

    This field allows one to avoid needing to attempt compilation of the
    project to identify the error(s).
    In addition, it allows an `ErrorInstance` to focus on a subset of
    errors in the event that the `change` induces multiple independent
    errors.
    The location is understood to be with respect to the project after
    application of the `change`.
    """
    tags: Set[str] = default_field(set())
    """
    Tag(s) characterizing the nature of the change or error.

    Optional labels that can be used to partition a dataset based upon a
    custom taxonomy for finer-grained evaluation or meta-studies.
    """

    @property
    def environment(self) -> Optional[OpamSwitch.Configuration]:
        """
        Get the environment of the error state, if specified.
        """
        environment = self.change.environment
        if environment is None:
            environment = self.initial_state.environment
        return environment

    @classmethod
    def deserialize(cls, data: object) -> 'ErrorInstance':
        """
        Deserialize an error instance.

        Note that this only works for monomorphic subclasses.
        """
        return deserialize_generic_dataclass(data, cls, error="raise")


@dataclass
class RepairInstance(Generic[_State, _Diff]):
    """
    A concise example of a repair.

    With this representation, one should be able to capture errors and
    repairs due to both changes to the source code and changes in
    environment.
    """

    error: ErrorInstance[_State, _Diff]
    """
    An erroneous project state.
    """
    repaired_state_or_diff: Union[ProjectState[_State,
                                               _Diff],
                                  ProjectStateDiff[_Diff]]
    """
    A repaired proof state.

    A state of the project after an error induced by the change has been
    fixed.
    If the environment is None, then it is understood to be the same
    environment in which the error occurs.
    """

    @property
    def environment(self) -> Optional[OpamSwitch.Configuration]:
        """
        Get the environment of the repaired state, if specified.
        """
        environment = self.repaired_state_or_diff.environment
        if environment is None:
            environment = self.error.environment
        return environment

    @classmethod
    def deserialize(cls, data: object) -> 'RepairInstance':
        """
        Deserialize a repair instance.

        Note that this only works for monomorphic subclasses.
        """
        return deserialize_generic_dataclass(data, cls, error="raise")


@dataclass
class GitProjectState(ProjectState[str, GitDiff]):
    """
    The state of a project in terms of Git commits and diffs.
    """

    @property
    def commit_sha(self) -> str:
        """
        Get a hash identifying a commit within a Git repository.
        """
        return self.project_state


@dataclass
class GitProjectStateDiff(ProjectStateDiff[GitDiff]):
    """
    A change in some implicit Git repository's state.
    """

    pass


@dataclass
class GitErrorInstance(ErrorInstance[str, GitDiff]):
    """
    A concise example of an error in its most raw and unprocessed form.

    With this representation, one should be able to capture errors
    induced by changes to source code and/or environment.
    """

    pass


@dataclass
class GitRepairInstance(RepairInstance[str, GitDiff]):
    """
    A concise example of a repair in its most raw and unprocessed form.

    With this representation, one should be able to capture errors and
    repairs due to both changes to the source code and changes in
    environment.
    """

    pass


@dataclass
class ProjectCommitDataState(ProjectState[ProjectCommitData,
                                          ProjectCommitDataDiff]):
    """
    The state of a project in terms of extracted commit data.
    """

    @property
    def commit_data(self) -> ProjectCommitData:
        """
        Get the commit data containing the state of the project.
        """
        return self.project_state

    @property
    def environment(self) -> Optional[OpamSwitch.Configuration]:
        """
        Get the environment from the project commit data.
        """
        environment = self._environment
        if environment is None and self.project_state.environment is not None:
            environment = self.project_state.environment.switch_config
        return environment

    @property
    def offset_state(self) -> ProjectCommitData:
        """
        Get the cumulative project state represented by this object.
        """
        state = self.project_state
        if self.offset is not None:
            state = self.offset.patch(state)
        return state

    def compress(self) -> GitProjectState:
        """
        Get a concise Git-based representation of this state.
        """
        offset = self.offset
        if self.offset is not None:
            offset = compute_git_diff(self.project_state, self.offset_state)
        offset = typing.cast(Optional[GitDiff], offset)
        if self.project_state.project_metadata.commit_sha is None:
            raise RuntimeError("Commit SHA must be known")
        return GitProjectState(
            self.project_state.project_metadata.commit_sha,
            offset,
            self.environment)


@dataclass
class ProjectCommitDataStateDiff(ProjectStateDiff[ProjectCommitDataDiff]):
    """
    A change in some implicit commit's extracted state.
    """

    def compress(
        self,
        reference: ProjectCommitData,
        reference_environment: Optional[OpamSwitch.Configuration]
    ) -> GitProjectStateDiff:
        """
        Compress this diff data into a text-based Git diff.

        Parameters
        ----------
        reference : ProjectCommitData
            A reference point against which to compute the Git diff.
        reference_environment : Optional[OpamSwitch.Configuration]
            The environment corresponding to the `reference` point.

        Returns
        -------
        GitProjectStateDiff
            A concise representation of this diff.
        """
        environment = None
        if (reference_environment is None
                or reference_environment != self.environment):
            environment = self.environment
        return GitProjectStateDiff(
            compute_git_diff(reference,
                             self.diff.patch(reference)),
            environment)


@dataclass
class ProjectCommitDataErrorInstance(ErrorInstance[ProjectCommitData,
                                                   ProjectCommitDataDiff]):
    """
    An example of an error in a standalone, precomputed offline format.

    With this representation, one should be able to capture errors
    induced by changes to source code and/or environment.
    """

    @property
    def error_state(self) -> ProjectCommitData:
        """
        Get the project state containing the error.
        """
        initial_state = cast_from_base_cls(
            ProjectCommitDataState,
            self.initial_state,
            ProjectState)
        initial_state = typing.cast(ProjectCommitDataState, initial_state)
        return self.change.diff.patch(initial_state.offset_state)

    def compress(self) -> GitErrorInstance:
        """
        Get a concise Git-based representation of this error instance.
        """
        initial_state = cast_from_base_cls(
            ProjectCommitDataState,
            self.initial_state,
            ProjectState)
        initial_state = typing.cast(ProjectCommitDataState, initial_state)
        change = cast_from_base_cls(
            ProjectCommitDataStateDiff,
            self.change,
            ProjectStateDiff)
        change = typing.cast(ProjectCommitDataStateDiff, change)
        return GitErrorInstance(
            initial_state.project_state.project_metadata.project_name,
            initial_state.compress(),
            change.compress(
                initial_state.project_state,
                initial_state._environment),
            self.error_location,
            set(self.tags))


RepairAnnotator = Callable[[
    VernacCommandData,
    SerializableDataDiff[VernacCommandData],
    ProjectCommitData,
    ProjectCommitData
],
                           Set[str]]  # noqa: E126
"""
A function that annotates a repaired command with a set of tags.
"""


@dataclass
class ProjectCommitDataRepairInstance(RepairInstance[ProjectCommitData,
                                                     ProjectCommitDataDiff]):
    """
    A concise example of a repair in its most raw and unprocessed form.

    With this representation, one should be able to capture errors and
    repairs due to both changes to the source code and changes in
    environment.
    """

    def compress(self) -> GitRepairInstance:
        """
        Get a concise Git-based representation of this repair instance.
        """
        error = cast_from_base_cls(
            ProjectCommitDataErrorInstance,
            self.error,
            ErrorInstance)
        error = typing.cast(ProjectCommitDataErrorInstance, error)
        if isinstance(self.repaired_state_or_diff, ProjectState):
            repaired = cast_from_base_cls(
                ProjectCommitDataStateDiff,
                self.repaired_state_or_diff,
                ProjectStateDiff)
            repaired = typing.cast(ProjectCommitDataState, repaired)
            repaired = repaired.compress()
        else:
            repaired = cast_from_base_cls(
                ProjectCommitDataStateDiff,
                self.repaired_state_or_diff,
                ProjectStateDiff)
            repaired = typing.cast(ProjectCommitDataStateDiff, repaired)
            repaired = repaired.compress(error.error_state, error.environment)
        repaired = typing.cast(
            Union[GitProjectState,
                  GitProjectStateDiff],
            repaired)
        return GitRepairInstance(error.compress(), repaired)

    @classmethod
    def _make_repair_instance(
        cls,
        initial_state: ProjectCommitData,
        error_state_diff: ProjectCommitDataDiff,
        error_state: ProjectCommitData,
        repaired_state_diff: ProjectCommitDataDiff,
        repaired_state: ProjectCommitData,
        broken_command: VernacCommandData,
        repair: SerializableDataDiff[VernacCommandData],
        get_tags: RepairAnnotator,
    ) -> 'ProjectCommitDataRepairInstance':
        """
        Create the actual repair instance.
        """
        repaired_environment = None
        if repaired_state.environment is not None:
            repaired_environment = repaired_state.environment.switch_config
            if initial_state.environment is not None:
                initial_environment = initial_state.environment.switch_config
                if repaired_environment != initial_environment:
                    repaired_environment = repaired_state.environment.switch_config
        repair_instance = ProjectCommitDataRepairInstance(
            error=ProjectCommitDataErrorInstance(
                project_name=initial_state.project_metadata.project_name,
                initial_state=ProjectCommitDataState(initial_state,
                                                     None,
                                                     None),
                change=ProjectCommitDataStateDiff(error_state_diff,
                                                  None),
                error_location={broken_command.command.location},
                tags=get_tags(
                    broken_command,
                    repair,
                    error_state,
                    repaired_state)),
            repaired_state_or_diff=ProjectCommitDataStateDiff(
                repaired_state_diff,
                repaired_environment))
        return repair_instance

    @classmethod
    def default_get_tags(
            cls,
            broken_command: VernacCommandData,
            repair: SerializableDataDiff[VernacCommandData],
            initial_state: ProjectCommitData,
            repaired_state: ProjectCommitData) -> Set[str]:
        """
        Get a default set of tags to apply to a repair.

        The default set of tags identify the type of repaired command
        and additionally note that the repair instance has been
        artificially mined, that only one command is repaired in one
        file, and whether any dependencies have been updated, dropped,
        or added (including Coq version).

        Parameters
        ----------
        broken_command : VernacCommandData
            The command in need of repair
        repair : SerializableDataDiff[VernacCommandData]
            A diff that can be applied to the command to retrieve its
            repaired version via ``repair.patch(broken_command)``.
        initial_state : ProjectCommitData
            The initial state containing the broken command.
        repaired_state : ProjectCommitData
            The repaired state.

        Returns
        -------
        tags : Set[str]
            A set of tags describing the repair.
        """
        tags = {
            f"repair:{broken_command.command_type}",
            "artificial:mined",
            "repair:one-command",
            "repair:one-file"
        }
        if (initial_state.environment is not None
                and repaired_state.environment is not None
                and initial_state.project_metadata.opam_dependencies is not None
                and repaired_state.project_metadata.opam_dependencies):
            initial_dependencies = set()
            for dep in initial_state.project_metadata.opam_dependencies:
                initial_dependencies.update(
                    typing.cast(PackageFormula,
                                PackageFormula.parse(dep)).packages)
            repaired_dependencies = set()
            for dep in repaired_state.project_metadata.opam_dependencies:
                repaired_dependencies.update(
                    typing.cast(PackageFormula,
                                PackageFormula.parse(dep)).packages)
            initial_packages = dict(
                initial_state.environment.switch_config.installed)
            repair_packages = dict(
                repaired_state.environment.switch_config.installed)
            tags.update(
                {
                    f"dropped-dependency:{p}" for p in repair_packages if
                    p in initial_dependencies and p not in repaired_dependencies
                })
            tags.update(
                {
                    f"new-dependency:{p}" for p in repair_packages if
                    p not in initial_dependencies and p in repaired_dependencies
                })
            tags.update(
                {
                    f"updated-dependency:{p}" for p in repair_packages
                    if p in initial_dependencies and p in repaired_dependencies
                    and initial_packages[p] != repair_packages[p]
                })
        return tags

    @classmethod
    def mine_repair_examples_from_successful_commits(
            cls,
            initial_state: ProjectCommitData,
            repaired_state: ProjectCommitData,
            repair_filter: Optional[Callable[[VernacCommandData],
                                             bool]] = None,
            get_tags: Optional[RepairAnnotator] = None,
            **kwargs) -> List['ProjectCommitDataRepairInstance']:
        r"""
        Mine a pair of commits for repair examples.

        Repair examples produced by this method comprise standalone
        commands (complete theorems, definitions, etc.) that have been
        modified between the commits.
        A virtual broken state is induced by partially applying the
        changes between the given commits such that one changed command
        is left out.
        The left out change constitutes the presumptive "repair".
        One may observe that not all mined broken states are guaranteed
        to actually raise an error when compiled.
        In such cases, one may infer the "repair" to be simply a
        directive to follow the original user's intention.

        Parameters
        ----------
        initial_state : ProjectCommitData
            An initial state, presumed to be without error.
        repaired_state : ProjectCommitData
            Another commit's state presumed to occur after
            `initial_state` and also be without error.
        repair_filter : Optional[Callable[[VernacCommandData], bool]], \
                optional
            A filter applied to changed commands' initial states that
            can be used to select types of repair examples to mine.
            By default, every changed command is extracted as a repair
            example.
        get_tags : Optional[RepairAnnotator], optional
            A function that annotates a repair with tags for subsequent
            filtering of the mined examples.
            By default, `default_get_tags` is used.

        Returns
        -------
        List['ProjectCommitDataRepairInstance']
            A list of mined repair instances.
        """
        if get_tags is None:
            get_tags = cls.default_get_tags
        # sort commands for reproducible indexing of commands in
        # produced diffs
        initial_state.sort_commands()
        commit_diff = ProjectCommitDataDiff.from_commit_data(
            initial_state,
            repaired_state,
            **kwargs)
        repair_instances: List[ProjectCommitDataRepairInstance] = []
        for filename, file_changes in commit_diff.changes.items():
            # make an example for each filtered, *changed* command
            for command_index in file_changes.changed_commands.keys():
                original_command = initial_state.command_data[filename][
                    command_index]
                if repair_filter is not None and not repair_filter(
                        original_command):
                    # this command is filtered out
                    continue
                # make two partial diffs
                # one partial diff creates a presumed broken state
                broken_state_diff = copy.deepcopy(commit_diff)
                broken_state_diff.changes[filename].changed_commands.pop(
                    command_index)
                broken_state = broken_state_diff.patch(initial_state)
                # sort commands for reproducible indexing of commands in
                # produced diffs
                broken_state.sort_commands()
                # the other partial diff repairs the broken state
                repaired_state_diff = ProjectCommitDataDiff.from_commit_data(
                    broken_state,
                    repaired_state,
                    **kwargs)
                # get the broken command
                repaired_files = list(repaired_state_diff.changes.keys())
                assert repaired_files, \
                    "A file should have been repaired"
                repaired_filename = repaired_files[0]
                repaired_commands = list(
                    repaired_state_diff.changes[repaired_filename]
                    .changed_commands.keys())
                assert repaired_commands, \
                    "A command should have been repaired"
                repaired_command_index = repaired_commands[0]
                broken_command = broken_state.command_data[repaired_filename][
                    repaired_command_index]
                # get the actual repair
                repair = repaired_state_diff.changes[
                    repaired_filename].changed_commands[repaired_command_index]
                # assemble the repair instance
                repair_instance = cls._make_repair_instance(
                    initial_state,
                    broken_state_diff,
                    broken_state,
                    repaired_state_diff,
                    repaired_state,
                    broken_command,
                    repair,
                    get_tags)
                repair_instances.append(repair_instance)
        return repair_instances
