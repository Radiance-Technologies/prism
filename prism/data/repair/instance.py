"""
Defines representations of repair instances (or examples).
"""

import typing
from dataclasses import asdict, dataclass, fields
from itertools import chain
from typing import (
    Callable,
    ClassVar,
    Dict,
    Generic,
    Iterable,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
)

import numpy as np
from bidict import bidict

from prism.data.cache.types.command import (
    VernacCommandData,
    VernacCommandDataList,
    VernacDict,
)
from prism.data.cache.types.project import ProjectCommitData
from prism.data.cache.types.command import VernacSentence
from prism.data.repair.align import (
    AlignedCommands,
    AlignmentFunction,
    align_commits,
    default_align,
    get_aligned_commands,
    left_file_offsets_from_aligned_commands,
    order_preserving_masked_alignment,
    right_file_offsets_from_aligned_commands,
)
from prism.data.repair.diff import compute_git_diff
from prism.interface.coq.options import CoqWarningState, SerAPIOptions
from prism.language.gallina.analyze import SexpInfo
from prism.project.metadata import ProjectMetadata
from prism.util.alignment import Alignment
from prism.util.diff import GitDiff
from prism.util.opam import OpamSwitch, PackageFormula
from prism.util.radpytools.dataclasses import Dataclass, default_field
from prism.util.serialize import (
    Serializable,
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
class FileOffset:
    """
    An offset to a file caused by a changed command.

    Note that a single command may induce multiple offsets as the
    command may be partitioned into multiple contiguous regions by
    nested commands, each of which may require an offset.
    """

    command_index: int
    """
    The index of the command whose modification induced the offset.
    """
    beg_charno: int
    """
    The beginning character number of the unmodified command segment.
    """
    end_charno: int
    """
    The ending character number of the unmodified command.
    """
    excess_charno: int
    """
    The number of excess characters in the modified command.
    """
    lineno: int
    """
    The beginning line number of the unmodified command.
    """
    lineno_last: int
    """
    The last line number of the unmodified command.
    """
    excess_lineno: int
    """
    The number of excess lines in the modified command.
    """


@dataclass
class VernacCommandDataListDiff:
    """
    A change relative to a list of extracted Vernacular commands.

    Ideally, each enumerated change should be independent such that one
    can remove an element and obtain a valid diff. Unfortunately, this
    is not quite achievable as it does not account for shifting content
    to account for the reverted changes. The `offsets` field helps with
    tracking such information for subsequent accounting during the
    patching process.
    """

    added_commands: VernacCommandDataList = default_field(
        VernacCommandDataList())
    """
    A list of new Vernacular commands to be added to the file.
    These new commands are presumed to be completely novel and not arise
    from relocating commands from other files.
    """
    affected_commands: Dict[
        int,
        SerializableDataDiff[VernacCommandData]] = default_field({})
    """
    A map from command indices in the original file to diffs that can be
    used to obtain commands that should replace the indexed commands.
    Note that the replacements may be located in other files.
    The commands are presumed to not be modified in form (text) but may
    be modified in content (AST/goals/hypotheses) as a side-effect of
    other changes.
    """
    changed_commands: Dict[
        int,
        SerializableDataDiff[VernacCommandData]] = default_field({})
    """
    A map from command indices in the original file to diffs that can be
    used to obtain commands that should replace the indexed commands.
    Note that the replacements may be located in other files.
    The commands are presumed to have been modified in form or content
    rather than simply relocated.
    """
    dropped_commands: Set[int] = default_field(set())
    """
    A set of command indices in the original file indicating commands
    that should be removed.
    """
    offsets: List[FileOffset] = default_field([])
    """
    A list identifying character and line offsets.

    The offsets are generally expected to arise from dropped changes.
    """
    # TODO: give ownership of logic around dropping changes to this
    # class

    @property
    def is_empty(self) -> bool:
        """
        Return whether this diff is empty.
        """
        return not (
            self.added_commands or self.affected_commands
            or self.changed_commands or self.dropped_commands)

    def drop_change(  # noqa: C901
        self,
        changed_command_idx: int,
        initial_file: VernacCommandDataList,
        final_state: ProjectCommitData,
        local_alignment_dict: Dict[int,
                                   Tuple[str,
                                         int]]
    ) -> Tuple[VernacCommandData, str,
               List[FileOffset]]:
        """
        Drop a single change from the diff.

        Parameters
        ----------
        changed_command_idx : int
            The index of the command whose changes should be dropped.
        initial_file : VernacCommandDataList
            The initial list of commands to which this diff applies.
        final_state : ProjectCommitData
            The final state of the project after application of this and
            all other diffs.
        local_alignment_dict : Dict[int, Tuple[str, int]]
            A file-local map that identifies each command in
            `initial_file` by mapping its index to filenames and
            file-level command indices in `final_state`.

        Returns
        -------
        VernacCommandData
            The reverted command whose changes were dropped.
            Note that its location may differ from the originally
            modified command.
        str
            The name of the file to which the changed command was moved.
        List[FileOffset]
            A list of offsets to be added to the diff of the file
            identified by the returned name.
        """
        # TODO: refactor to reduce complexity
        initial_command = initial_file[changed_command_idx]
        broken_command = initial_command.shallow_copy()
        repair = self.changed_commands.pop(changed_command_idx)
        repaired_command = repair.patch(broken_command)
        repair_filename = repaired_command.location.filename
        final_file = final_state.command_data[repair_filename]
        # get nested commands
        all_broken_indices = dict(
            enumerate(initial_file.get_covering(changed_command_idx)))
        all_repaired_indices = dict(
            enumerate(final_file.get_covering(repaired_command)))
        all_broken_commands = VernacCommandDataList(
            [
                initial_file[idx]
                if idx != changed_command_idx else broken_command
                for idx in all_broken_indices.values()
            ])
        all_repaired_commands = VernacCommandDataList(
            [final_file[idx] for idx in all_repaired_indices.values()])
        repaired_command_index = None
        for idx in all_repaired_indices.values():
            if repaired_command.spanning_location(
            ) == final_file[idx].spanning_location():
                repaired_command_index = idx
                break
        assert repaired_command_index is not None, \
            "The repaired command should be in its own covering set"
        # get sentences indexed by command and sorted by location
        all_indexed_broken_sentences = sorted(
            (
                (all_broken_indices[i],
                 s) for i,
                s in all_broken_commands.indexed_sentences_iter()),
            key=lambda s: s[1])
        all_indexed_repaired_sentences = sorted(
            (
                (all_repaired_indices[i],
                 s) for i,
                s in all_repaired_commands.indexed_sentences_iter()),
            key=lambda s: s[1])
        # compute mask of allowable sentence assignments
        # do not allow alignment of sentences between commands that
        # were not assigned to one another
        alignment_mask = np.zeros(
            (
                len(all_indexed_broken_sentences),
                len(all_indexed_repaired_sentences)),
            dtype=bool)
        for (i,
             (broken_command_idx,
              _)) in enumerate(all_indexed_broken_sentences):
            for (j,
                 (repaired_command_idx,
                  _)) in enumerate(all_indexed_repaired_sentences):
                if local_alignment_dict.get(broken_command_idx,
                                            ("",
                                             -1)) == (repair_filename,
                                                      repaired_command_idx):
                    alignment_mask[i, j] = True
        # align sentences
        all_broken_sentences = [s for _, s in all_indexed_broken_sentences]
        all_repaired_sentences = [s for _, s in all_indexed_repaired_sentences]
        alignment = order_preserving_masked_alignment(
            all_broken_sentences,
            all_repaired_sentences,
            alignment_mask,
            alpha=0.5)
        aligned_sentences = typing.cast(
            Alignment[Tuple[int,
                            VernacSentence]],
            [
                (
                    None if i is None else all_indexed_broken_sentences[i],
                    None if j is None else all_indexed_repaired_sentences[j])
                for i,
                j in alignment
            ])
        # relocate each sentence in-place, recreate diff, and record
        # offsets
        assert all_repaired_sentences
        target_location = None
        broken_sentence_idx = -1
        repaired_sentence_idx = -1
        offsets: List[FileOffset] = []
        # the offset for the current contiguous region
        current_offset: Optional[FileOffset] = None
        for indexed_broken_sentence, indexed_repaired_sentence in aligned_sentences:
            # update location but not text
            if indexed_repaired_sentence is not None:
                repaired_command_idx, repaired_sentence = indexed_repaired_sentence
                target_location = repaired_sentence.location
                repaired_sentence_idx += 1
            if indexed_broken_sentence is None:
                # nothing to do
                continue
            newline_added = False
            broken_sentence_idx += 1
            broken_command_idx, broken_sentence = indexed_broken_sentence
            broken_location = broken_sentence.location
            if broken_command_idx != changed_command_idx:
                # we do not relocate other commands here
                target_location = None
                if current_offset is not None:
                    # end offset for contiguous region
                    offsets.append(current_offset)
                    current_offset = None
                continue
            elif target_location is None:
                # start of new contiguous region
                # find next valid repaired sentence
                is_valid_alignment = False
                next_valid_repaired_sentence_index = None
                for (next_valid_repaired_sentence_index,  # noqa: B007
                     is_valid_alignment) in enumerate(
                         alignment_mask[broken_sentence_idx,
                                        repaired_sentence_idx + 1 :]):
                    if is_valid_alignment:
                        break
                if is_valid_alignment:
                    assert next_valid_repaired_sentence_index is not None
                    target_location = all_repaired_sentences[
                        next_valid_repaired_sentence_index].location
                else:
                    # no further sentences to align with
                    # use previous location as reference
                    target_location = all_repaired_sentences[
                        repaired_sentence_idx].location
                    # insert immediately after
                    target_location = SexpInfo.Loc(
                        target_location.filename,
                        target_location.lineno_last,
                        target_location.bol_pos_last,
                        target_location.lineno_last,
                        target_location.bol_pos_last,
                        target_location.end_charno,
                        target_location.end_charno)
                newline_added = True
            elif indexed_repaired_sentence is None:
                # continuing contiguous region
                # insert immediately after
                target_location = SexpInfo.Loc(
                    target_location.filename,
                    target_location.lineno_last,
                    target_location.bol_pos_last,
                    target_location.lineno_last,
                    target_location.bol_pos_last,
                    target_location.end_charno,
                    target_location.end_charno)
                newline_added = True
            char_offset = target_location.beg_charno - broken_location.beg_charno
            line_offset = target_location.lineno - broken_location.lineno
            new_broken_location = broken_location.shift(
                char_offset + newline_added,
                line_offset + newline_added)
            broken_sentence.location = new_broken_location.rename(
                repair_filename)
            num_excess_chars = max(
                0,
                new_broken_location.end_charno - target_location.end_charno)
            num_excess_lines = max(
                0,
                new_broken_location.lineno_last - target_location.lineno_last)
            if current_offset is None:
                if num_excess_chars > 0 or num_excess_lines > 0:
                    current_offset = FileOffset(
                        repaired_command_index,
                        target_location.beg_charno,
                        target_location.end_charno,
                        num_excess_chars,
                        target_location.lineno,
                        target_location.lineno_last,
                        num_excess_lines)
            else:
                # expand existing offset
                current_offset.end_charno = target_location.end_charno
                current_offset.lineno_last = target_location.lineno_last
                current_offset.excess_charno += num_excess_chars
                current_offset.excess_lineno += num_excess_lines
        if current_offset is not None:
            # end offset for last contiguous region
            offsets.append(current_offset)
            current_offset = None
        # recreate diff
        repair = SerializableDataDiff[VernacCommandData].compute_diff(
            initial_command,
            broken_command)
        self.affected_commands[changed_command_idx] = repair
        return broken_command, repair_filename, offsets

    def shallow_copy(self) -> 'VernacCommandDataListDiff':
        """
        Get a shallow copy of this structure and its fields.
        """
        return VernacCommandDataListDiff(
            self.added_commands.shallow_copy(),
            dict(self.affected_commands),
            dict(self.changed_commands),
            set(self.dropped_commands),
            list(self.offsets))


@dataclass
class ProjectCommitDataDiff:
    """
    A diff between two commits.

    Notes
    -----
    This diff is purely between the command-related elements of the
    `ProjectCommitData` and thus does not capture changes to the
    environment, metadata, or other fields of `ProjectCommitData`.
    """

    command_changes: Dict[str,
                          VernacCommandDataListDiff] = default_field({})
    """
    A map containing per-file changes.
    """
    file_dependencies_diff: SerializableDataDiff[Optional[Dict[
        str,
        List[str]]]] = default_field(SerializableDataDiff(""))
    """
    Any changes to the precomputed dependency graph between the files.
    """

    @property
    def added_commands(self) -> Iterator[Tuple[str, VernacCommandData]]:
        """
        Get an iterator over commands added to each file.

        Yields
        ------
        str
            The path to the file containing the added command.
        VernacCommandData
            The added command.
        """
        for filename, file_changes in self.command_changes.items():
            for command in file_changes.added_commands:
                yield filename, command

    @property
    def affected_commands(
        self) -> Iterator[Tuple[str,
                                int,
                                SerializableDataDiff[VernacCommandData]]]:
        """
        Get an iterator over commands indirectly affected in each file.

        An affected command is one whose text did not change but whose
        data nevertheless did, e.g., due to a relocation or a
        side-effect of a text modification elsewhere.

        Yields
        ------
        str
            The path to the file containing the affected command.
        int
            The index of the affected command in the original state's
            list of commands for the file.
        SerializableDataDiff[VernacCommandData]]
            A diff that when applied to the original command yields the
            affected version.
        """
        for filename, file_changes in self.command_changes.items():
            for command_index, command_diff in file_changes.affected_commands.items():
                yield filename, command_index, command_diff

    @property
    def changed_commands(
        self) -> Iterator[Tuple[str,
                                int,
                                SerializableDataDiff[VernacCommandData]]]:
        """
        Get an iterator over commands changed in each file.

        Yields
        ------
        str
            The path to the file containing the changed command.
        int
            The index of the changed command in the original state's
            list of commands for the file.
        SerializableDataDiff[VernacCommandData]]
            A diff that when applied to the original command yields the
            changed version.
        """
        for filename, file_changes in self.command_changes.items():
            for command_index, command_diff in file_changes.changed_commands.items():
                yield filename, command_index, command_diff

    @property
    def dropped_commands(self) -> Iterator[Tuple[str, int]]:
        """
        Get an iterator over commands dropped from each file.

        Yields
        ------
        str
            The path to the file containing the dropped command.
        int
            The index of the dropped command in the original state's
            list of commands for the file.
        """
        for filename, file_changes in self.command_changes.items():
            for index in file_changes.dropped_commands:
                yield filename, index

    @property
    def is_empty(self) -> bool:
        """
        Return whether this diff is empty.
        """
        return all([v.is_empty for v in self.command_changes.values()])

    def _patch_locations(self, patched_command_data: VernacDict) -> None:
        """
        Apply offsets in the patch to locations of commands.

        The given `patched_command_data` is presumed to already be
        repaired but for the offsets and sorted in canonical order (such
        that nested commands appear before the commands that surround
        them).
        """
        for filename, change in self.command_changes.items():
            # iterate in reverse order so that we can correctly detect
            # nested commands and not need to offset the offsets
            offsets = sorted(
                change.offsets,
                key=lambda p: p.beg_charno,
                reverse=True)
            if not offsets:
                continue
            commands = patched_command_data[filename]
            for (idx,
                 (command_index,
                  sentence)) in enumerate(reversed(sorted(
                      commands.indexed_sentences_iter(),
                      key=lambda p: p[1]))):
                idx = len(commands) - idx - 1
                sentence_loc = sentence.location
                for offset in offsets:
                    is_already_offset = command_index == offset.command_index
                    if is_already_offset:
                        continue
                    if sentence_loc.beg_charno >= offset.end_charno:
                        # starts after offset region
                        sentence.location = sentence.location.shift(
                            offset.excess_charno,
                            offset.excess_lineno)
                        continue
                    overlaps_right = (
                        sentence_loc.beg_charno >= offset.beg_charno
                        and sentence_loc.end_charno > offset.end_charno)
                    overlaps_left = (
                        sentence_loc.beg_charno < offset.beg_charno
                        and sentence_loc.end_charno > offset.beg_charno)
                    is_subinterval = (
                        sentence_loc.beg_charno >= offset.beg_charno
                        and sentence_loc.end_charno <= offset.end_charno)
                    if overlaps_right or overlaps_left or is_subinterval:
                        raise RuntimeError(
                            "Sentences cannot overlap with offset region. "
                            f"Offset: {offset}."
                            f"Sentence: {sentence}")

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
        result = data.shallow_copy()
        result_command_data = result.command_data
        # decompose moves and changes into drops and adds
        dropped_commands: Dict[str,
                               Set[int]] = {}
        added_commands: Dict[str,
                             VernacCommandDataList] = {}
        for filename, change in self.command_changes.items():
            # Set of commands to be dropped from original state.
            dropped = dropped_commands.setdefault(filename, set())
            dropped.update(change.dropped_commands)
            # Include added commands from diff being applied.
            added = added_commands.setdefault(filename, VernacCommandDataList())
            added.extend(c.shallow_copy() for c in change.added_commands)
            # decompose changes into drops and adds
            dropped.update(change.changed_commands.keys())
            dropped.update(change.affected_commands.keys())
            for (original_command_index,
                 command_diff) in chain(change.changed_commands.items(),
                                        change.affected_commands.items()):
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
            command_data.extend(added)
            if not command_data:
                assert not added, "file cannot be empty if commands were added"
                # the resulting file would be empty; remove it
                result_command_data.pop(filename, None)
        # Apply offsets
        result.sort_commands()
        self._patch_locations(result_command_data)
        result.file_dependencies = self.file_dependencies_diff.patch(
            data.file_dependencies)
        return result

    def shallow_copy(self) -> 'ProjectCommitDataDiff':
        """
        Get a shallow copy of this structure and its fields.
        """
        return ProjectCommitDataDiff(
            {k: v.shallow_copy() for k,
             v in self.command_changes.items()},
            self.file_dependencies_diff)

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

        Notes
        -----
        This computation does not capture changes to the file
        dependencies.
        """
        result = ProjectCommitDataDiff()
        changes = result.command_changes
        a_file_offsets = left_file_offsets_from_aligned_commands(
            aligned_commands)
        for a, b in aligned_commands:
            if a is None:
                # added command
                assert b is not None, "cannot skip both sequences in alignment"
                _, filename, cmd = b
                file_diff = changes.setdefault(
                    filename,
                    VernacCommandDataListDiff())
                file_diff.added_commands.append(cmd.shallow_copy())
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
                    command_diff = SerializableDataDiff[
                        VernacCommandData].compute_diff(acmd,
                                                        bcmd)
                    if acmd.all_text() != bcmd.all_text():
                        # changed command
                        container = file_diff.changed_commands
                    else:
                        # some extraneous content was affected
                        # the command may have been moved, have a
                        # modified AST due to a different Coq version,
                        # or have different goals/hypotheses due to
                        # side-effects
                        container = file_diff.affected_commands
                    container[aidx - offset] = command_diff
                # else the command is unchanged and not in the diff
        return result

    @classmethod
    def from_alignment(
        cls,
        a: ProjectCommitData,
        b: ProjectCommitData,
        alignment: np.ndarray,
        return_aligned_commands: bool = False
    ) -> Union['ProjectCommitDataDiff',
               Tuple['ProjectCommitDataDiff',
                     AlignedCommands]]:
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
        return_aligned_commands : bool, optional
            If True, then return the alignment between the commands of
            `a` and `b`, by default False.

        Returns
        -------
        diff : ProjectCommitDataDiff
            The diff between `a` and `b` such that
            ``diff.patch(a).command_data == b.command_data``.
        aligned_commands : AlignedCommands, optional
            If `return_aligned_commands` is True, then the aligned
            commands are also returned.
        """
        # NOTE (AG): I haven't been able to convince myself why patching
        # goals is necessary, but all tests indicate that it is.
        a.patch_goals()
        b.patch_goals()
        a.sort_commands()
        b.sort_commands()
        aligned_commands = get_aligned_commands(a, b, alignment)
        diff = cls.from_aligned_commands(aligned_commands)
        diff.file_dependencies_diff = SerializableDataDiff.compute_diff(
            a.file_dependencies,
            b.file_dependencies)
        if return_aligned_commands:
            return diff, aligned_commands
        else:
            return diff

    @classmethod
    def from_commit_data(
        cls,
        a: ProjectCommitData,
        b: ProjectCommitData,
        align: AlignmentFunction,
        diff: Optional[GitDiff] = None,
        compute_diff: bool = True,
        return_aligned_commands: bool = False
    ) -> Union['ProjectCommitDataDiff',
               Tuple['ProjectCommitDataDiff',
                     AlignedCommands]]:
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
        return_aligned_commands : bool, optional
            If True, then return the alignment between the commands of
            `a` and `b`, by default False.

        Returns
        -------
        ProjectCommitDataDiff
            The diff between `a` and `b` such that
            ``diff.patch(a).command_data == b.command_data``.
        aligned_commands : AlignedCommands, optional
            If `return_aligned_commands` is True, then the aligned
            commands are also returned.
        """
        if diff is None and compute_diff:
            diff = compute_git_diff(a, b)
        if diff is not None:
            alignment = align_commits(a, b, diff, align)
        else:
            alignment = align(a, b)
        data_diff = cls.from_alignment(a, b, alignment, return_aligned_commands)
        return data_diff


@dataclass
class BuildProcess:
    """
    Metadata that enables functionality in an implicit environment.
    """

    build_cmd: List[str]
    """
    A list of commands for building the project.
    """
    install_cmd: List[str]
    """
    A list of commands for installing the project in a user environment.
    """
    clean_cmd: List[str]
    """
    A list of commands for cleaning build artifacts.
    """
    serapi_options: Optional[SerAPIOptions]
    """
    Flags or options passed to SerAPI command-line executables.
    """

    def embed(self, metadata: ProjectMetadata) -> None:
        """
        Embed the build process in the given metadata.
        """
        for f in fields(self):
            f_name = f.name
            setattr(metadata, f_name, getattr(self, f_name))

    @classmethod
    def from_metadata(cls, metadata: ProjectMetadata) -> 'BuildProcess':
        """
        Extract the build process from given project metadata.
        """
        return BuildProcess(
            metadata.build_cmd,
            metadata.install_cmd,
            metadata.clean_cmd,
            metadata.serapi_options)


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
_StateDiff = TypeVar("_StateDiff")
_Process = TypeVar("_Process")


@dataclass
class ProjectState(Serializable, Generic[_State, _StateDiff, _Process]):
    """
    The state of a project.
    """

    project_state: _State
    """
    A representation of the state of the project.
    """
    offset: Optional[_StateDiff] = None
    """
    A set of changes relative to the `project_state`.

    This field is useful for representing working tree changes.
    """
    _build_process: Optional[_Process] = None
    """
    The build process and/or compiler flags.
    """
    _environment: Optional[OpamSwitch.Configuration] = None
    """
    The environment in which the project is built.

    This field identifies other installed package versions including the
    Coq compiler.
    """

    @property
    def build_process(self) -> Optional[_Process]:
        """
        The build process for the state.
        """
        return self._build_process

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
class ProjectStateDiff(Serializable, Generic[_StateDiff, _Process]):
    """
    A change in some implicit project's state.
    """

    diff: _StateDiff
    """
    A refactor or other change to some implicit state.
    """
    build_process: Optional[_Process] = None
    """
    A change in the build process or compiler flags.

    If None, then it is understood to be the same build process as the
    process associated with the implicit state.
    """
    environment: Optional[OpamSwitch.Configuration] = None
    """
    The changed environment.

    If None, then it is understood to be the same environment as the
    environment associated with implicit state.
    """

    @classmethod
    def deserialize(cls, data: object) -> 'ProjectStateDiff':
        """
        Deserialize a project state diff.

        Note that this only works for monomorphic subclasses.
        """
        return deserialize_generic_dataclass(data, cls, error="raise")


@dataclass
class ErrorInstance(Serializable, Generic[_State, _StateDiff, _Process]):
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
    initial_state: ProjectState[_State, _StateDiff, _Process]
    """
    An initial project state.

    A state of the project, nominally taken to be prior to a change that
    introduced a broken proof or other bug.
    """
    change: ProjectStateDiff[_StateDiff, _Process]
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
    def build_process(self) -> Optional[_Process]:
        """
        Get the build process for the error state, if specified.
        """
        build_process = self.change.build_process
        if build_process is None:
            build_process = self.initial_state.build_process
        return build_process

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
class RepairInstance(Serializable, Generic[_State, _StateDiff, _Process]):
    """
    A concise example of a repair.

    With this representation, one should be able to capture errors and
    repairs due to both changes to the source code and changes in
    environment.
    """

    error: ErrorInstance[_State, _StateDiff, _Process]
    """
    An erroneous project state.
    """
    repaired_state_or_diff: Union[ProjectState[_State,
                                               _StateDiff,
                                               _Process],
                                  ProjectStateDiff[_StateDiff,
                                                   _Process]]
    """
    A repaired proof state.

    A state of the project after an error induced by the change has been
    fixed.
    If the environment is None, then it is understood to be the same
    environment in which the error occurs.
    """

    @property
    def build_process(self) -> Optional[_Process]:
        """
        Get the build process of the repaired state, if specified.
        """
        build_process = self.repaired_state_or_diff.build_process
        if build_process is None:
            build_process = self.error.build_process
        return build_process

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
class GitProjectState(ProjectState[str, GitDiff, BuildProcess]):
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
class GitProjectStateDiff(ProjectStateDiff[GitDiff, BuildProcess]):
    """
    A change in some implicit Git repository's state.
    """

    pass


@dataclass
class GitErrorInstance(ErrorInstance[str, GitDiff, BuildProcess]):
    """
    A concise example of an error in its most raw and unprocessed form.

    With this representation, one should be able to capture errors
    induced by changes to source code and/or environment.
    """

    def __post_init__(self):
        """
        Patch generic attributes to non-generic subclasses.
        """
        if not isinstance(self.initial_state, GitProjectState):
            self.initial_state = GitProjectState(
                self.initial_state.project_state,
                self.initial_state.offset,
                self.initial_state._build_process,
                self.initial_state._environment)
        if not isinstance(self.change, GitProjectStateDiff):
            self.change = GitProjectStateDiff(
                self.change.diff,
                self.change.build_process,
                self.change.environment)


@dataclass
class GitRepairInstance(RepairInstance[str, GitDiff, BuildProcess]):
    """
    A concise example of a repair in its most raw and unprocessed form.

    With this representation, one should be able to capture errors and
    repairs due to both changes to the source code and changes in
    environment.
    """

    def __post_init__(self):
        """
        Patch generic attributes to non-generic subclasses.
        """
        if not isinstance(self.error, GitErrorInstance):
            self.error = GitErrorInstance(
                self.error.project_name,
                self.error.initial_state,
                self.error.change,
                self.error.error_location,
                self.error.tags)
        if isinstance(self.repaired_state_or_diff, ProjectState):
            if not isinstance(self.repaired_state_or_diff, GitProjectState):
                self.repaired_state_or_diff = GitProjectState(
                    self.repaired_state_or_diff.project_state,
                    self.repaired_state_or_diff.offset,
                    self.repaired_state_or_diff._build_process,
                    self.repaired_state_or_diff._environment)
        elif isinstance(self.repaired_state_or_diff, ProjectStateDiff):
            if not isinstance(self.repaired_state_or_diff, GitProjectStateDiff):
                self.repaired_state_or_diff = GitProjectStateDiff(
                    self.repaired_state_or_diff.diff,
                    self.repaired_state_or_diff.build_process,
                    self.repaired_state_or_diff.environment)
        else:
            raise TypeError(
                "repaired_state_or_diff must be a state or a diff, "
                f"got {type(self.repaired_state_or_diff)}")


@dataclass
class ProjectCommitDataState(ProjectState[ProjectCommitData,
                                          ProjectCommitDataDiff,
                                          BuildProcess]):
    """
    The state of a project in terms of extracted commit data.
    """

    @property
    def build_process(self) -> Optional[BuildProcess]:
        """
        Get the environment from the project commit data.
        """
        build_process = self._build_process
        if build_process is None:
            build_process = BuildProcess.from_metadata(
                self.project_state.project_metadata)
        return build_process

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
        if self.build_process is not None:
            self.build_process.embed(state.project_metadata)
        return state

    def compress(
        self,
        reference_build_process: Optional[BuildProcess] = None,
        reference_environment: Optional[OpamSwitch.Configuration] = None
    ) -> GitProjectState:
        r"""
        Get a concise Git-based representation of this state.

        Parameters
        ----------
        reference_build_process : Optional[BuildProcess], optional
            The build process corresponding to a prior reference point.
            For example, `self` may be a repaired state with
            `reference_build_process` taken from a broken state.
        reference_environment : Optional[OpamSwitch.Configuration], \
                optional
            The environment corresponding to a prior reference point.
            For example, `self` may be a repaired state with
            `reference_environment` taken from a broken state.

        Returns
        -------
        GitProjectStateDiff
            A concise representation of this diff.
        """
        offset = self.offset
        if self.offset is not None:
            offset = compute_git_diff(self.project_state, self.offset_state)
        offset = typing.cast(Optional[GitDiff], offset)
        if self.project_state.project_metadata.commit_sha is None:
            raise RuntimeError("Commit SHA must be known")
        build_process = None
        if (reference_build_process is None
                or reference_build_process != self.build_process):
            build_process = self.build_process
        environment = None
        if (reference_environment is None
                or reference_environment != self.environment):
            environment = self.environment
        return GitProjectState(
            self.project_state.project_metadata.commit_sha,
            offset,
            build_process,
            environment)


@dataclass
class ProjectCommitDataStateDiff(ProjectStateDiff[ProjectCommitDataDiff,
                                                  BuildProcess]):
    """
    A change in some implicit commit's extracted state.
    """

    def compress(
        self,
        reference: ProjectCommitData,
        reference_build_process: Optional[BuildProcess],
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
        build_process = None
        if (reference_build_process is None
                or reference_build_process != self.build_process):
            build_process = self.build_process
        environment = None
        if (reference_environment is None
                or reference_environment != self.environment):
            environment = self.environment
        return GitProjectStateDiff(
            compute_git_diff(reference,
                             self.diff.patch(reference)),
            build_process,
            environment)


ErrorAnnotator = Callable[[
    VernacCommandData,
    ProjectCommitData,
    ProjectCommitDataDiff,
    Optional[BuildProcess],
    Optional[OpamSwitch.Configuration],
    Optional[Iterable[str]]
],
                          Set[str]]  # noqa: E126
"""
A function that annotates a erroneous command with a set of tags.
"""

ChangeSelectionMapping = Dict[str, str]
"""
Dictionary mapping field names of ChangeSelection to strings derived
from those fields.
"""


@dataclass
class ChangeSelection:
    """
    Represents a selection from a `ProjectCommitDataDiff`.
    """

    added_commands: Iterable[Tuple[str, int]] = default_field([])
    """
    A list of pairs of filenames and added command indices.
    """
    affected_commands: Iterable[Tuple[str, int]] = default_field([])
    """
    A list of pairs of filenames and affected command indices.
    """
    changed_commands: Iterable[Tuple[str, int]] = default_field([])
    """
    A list of pairs of filenames and changed command indices.
    """
    dropped_commands: Iterable[Tuple[str, int]] = default_field([])
    """
    A list of pairs of filenames and dropped command indices.
    """

    def as_joined_dict(self) -> ChangeSelectionMapping:
        """
        Join ChangeSelection fields as strings and return as dictionary.

        Parameters
        ----------
        change_selection : ChangeSelection
            ChangeSelection object to process

        Returns
        -------
        ChangeSelectionMapping
            Mapping containing joined fields dictionary
        """
        # This function could be a one-liner, but that would just be too
        # much.
        mapping = {}
        for key, value in asdict(self).items():
            mapping[key] = " ".join(
                [f"{item[0]} {item[1]}" for item in sorted(value)])
        return mapping


ChangeSetMiner = Callable[[ProjectCommitData,
                           ProjectCommitDataDiff],
                          Iterable[ChangeSelection]]
"""
A function that takes an initial state and a diff relative to it and
returns a set of changesets derived from the diff.
"""


@dataclass
class ProjectCommitDataErrorInstance(ErrorInstance[ProjectCommitData,
                                                   ProjectCommitDataDiff,
                                                   BuildProcess]):
    """
    An example of an error in a standalone, precomputed offline format.

    With this representation, one should be able to capture errors
    induced by changes to source code and/or environment.
    """

    def __post_init__(self):
        """
        Patch generic attributes to non-generic subclasses.
        """
        if not isinstance(self.initial_state, ProjectCommitDataState):
            self.initial_state = ProjectCommitDataState(
                self.initial_state.project_state,
                self.initial_state.offset,
                self.initial_state._build_process,
                self.initial_state._environment)
        if not isinstance(self.change, ProjectCommitDataStateDiff):
            self.change = ProjectCommitDataStateDiff(
                self.change.diff,
                self.change.build_process,
                self.change.environment)

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
        error_state = self.change.diff.patch(initial_state.offset_state)
        error_state.sort_commands()
        if self.change.build_process is not None:
            self.change.build_process.embed(error_state.project_metadata)
        return error_state

    @property
    def project_metadata(self) -> ProjectMetadata:
        """
        Get the initial state's project metadata.
        """
        return self.initial_state.project_state.project_metadata

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
                initial_state._build_process,
                initial_state._environment),
            self.error_location,
            set(self.tags))

    @classmethod
    def _make_error_instance(
            cls,
            initial_state: ProjectCommitData,
            broken_state_diff: ProjectCommitDataDiff,
            broken_build_process: Optional[BuildProcess],
            broken_environment: Optional[OpamSwitch.Configuration],
            broken_dependencies: Optional[Iterable[str]],
            broken_commands: Iterable[VernacCommandData],
            get_error_tags: ErrorAnnotator) -> 'ProjectCommitDataErrorInstance':
        """
        Create the actual error instance.
        """
        error_build_process = None
        if broken_build_process is not None:
            error_build_process = broken_build_process
            initial_build_process = BuildProcess.from_metadata(
                initial_state.project_metadata)
            if error_build_process == initial_build_process:
                error_build_process = None
        error_environment = None
        if broken_environment is not None:
            error_environment = broken_environment
            if initial_state.environment is not None:
                initial_environment = initial_state.environment.switch_config
                if error_environment == initial_environment:
                    error_environment = None
        tags = set()
        for broken_command in broken_commands:
            tags.update(
                get_error_tags(
                    broken_command,
                    initial_state,
                    broken_state_diff,
                    broken_build_process,
                    broken_environment,
                    broken_dependencies))
        error_instance = cls(
            project_name=initial_state.project_metadata.project_name,
            initial_state=ProjectCommitDataState(initial_state,
                                                 None,
                                                 None),
            change=ProjectCommitDataStateDiff(
                broken_state_diff,
                error_build_process,
                error_environment),
            error_location={bc.command.location for bc in broken_commands},
            tags=tags)
        return error_instance

    @classmethod
    def default_changeset_miner(
        cls,
        initial_state: ProjectCommitData,
        commit_diff: ProjectCommitDataDiff,
        error_filter: Optional[Callable[[VernacCommandData],
                                        bool]] = None
    ) -> List[ChangeSelection]:
        r"""
        Make selections by dropping individual changed commands.

        Parameters
        ----------
        initial_state : ProjectCommitData
            The initial state of the project.
        commit_diff : ProjectCommitDataDiff
            Changes to the state from which selections will be made.
        error_filter : Optional[Callable[[VernacCommandData], bool]], \
                optional
            An optional filter one may use to skip dropping certain
            commands, e.g., to create changes that drop only altered
            proofs, by default None.

        Returns
        -------
        selected_changes : List[ChangeSelection]
            A list of selected changesets.
        """
        selected_changes: List[ChangeSelection] = []
        for filename, command_index, _ in commit_diff.changed_commands:
            # make an example for each filtered, *changed* command
            original_command = initial_state.command_data[filename][
                command_index]
            if error_filter is None or error_filter(original_command):
                # this command is not filtered out
                added_commands = [
                    (f,
                     idx)
                    for f,
                    file_changes in commit_diff.command_changes.items()
                    for idx in range(len(file_changes.added_commands))
                ]
                affected_commands = [
                    (f,
                     idx) for f,
                    idx,
                    _ in commit_diff.affected_commands
                ]
                # drop command in selection
                changed_commands = [
                    (f,
                     idx)
                    for f,
                    idx,
                    _ in commit_diff.changed_commands
                    if f != filename or idx != command_index
                ]
                dropped_commands = list(commit_diff.dropped_commands)
                selected_changes.append(
                    ChangeSelection(
                        added_commands,
                        affected_commands,
                        changed_commands,
                        dropped_commands))
        return selected_changes

    @classmethod
    def get_build_process_tags(
            cls,
            initial_build_process: BuildProcess,
            broken_build_process: Optional[BuildProcess]) -> Set[str]:
        """
        Update tags for an error given before/after build processes.
        """
        tags = set()
        initial_options = initial_build_process.serapi_options
        broken_options = None
        if broken_build_process is not None:
            broken_options = broken_build_process.serapi_options
        if initial_options is not None and broken_options is not None:
            initial_iqr = initial_options.iqr
            broken_iqr = broken_options.iqr
            tags.update(
                {
                    f"dropped-I-path:{p}" for p in initial_iqr.I
                    if p not in broken_iqr.I
                })
            tags.update(
                {
                    f"added-I-path:{p}" for p in broken_iqr.I
                    if p not in initial_iqr.I
                })
            tags.update(
                cls.get_qr_tags(
                    initial_iqr.Q,
                    broken_iqr.Q,
                    broken_iqr.R,
                    True))
            tags.update(
                cls.get_qr_tags(
                    initial_iqr.R,
                    broken_iqr.R,
                    broken_iqr.Q,
                    False))
            initial_settings = initial_options.settings_dict
            broken_settings = broken_options.settings_dict
            for setting_name, setting_enabled in broken_settings.items():
                if (setting_name not in initial_settings
                        or setting_enabled != initial_settings[setting_name]):
                    tags.add(
                        f"{'Set' if setting_enabled else 'Unset'}:{setting_name}"
                    )
            initial_warnings = initial_options.warnings_dict
            broken_warnings = broken_options.warnings_dict
            for warning_name, warning_state in broken_warnings.items():
                if (warning_name not in initial_warnings
                        or warning_state != initial_warnings[warning_name]):
                    if warning_state == CoqWarningState.DISABLED:
                        tags.add(f"warning-disabled:{warning_name}")
                    elif warning_state == CoqWarningState.ENABLED:
                        tags.add(f"warning-enabled:{warning_name}")
                    else:
                        tags.add(f"warning-elevated:{warning_name}")
            for f in fields(initial_options):
                f_name = f.name
                if f.type == bool:
                    initial_flag = getattr(initial_options, f_name)
                    broken_flag = getattr(broken_options, f_name)
                    if initial_flag != broken_flag:
                        if broken_flag != f.default:
                            tags.add(f"added-flag:{f_name}")
                        else:
                            tags.add(f"removed-flag:{f_name}")
        return tags

    @classmethod
    def get_environment_tags(
            cls,
            initial_environment: Optional[OpamSwitch.Configuration],
            initial_opam_dependencies: Optional[List[str]],
            final_environment: Optional[OpamSwitch.Configuration],
            final_opam_dependencies: Optional[Iterable[str]]) -> Set[str]:
        """
        Get tags for an error given the environment before and after.
        """
        tags = set()
        if (initial_environment is not None and final_environment is not None
                and initial_opam_dependencies is not None
                and final_opam_dependencies is not None):
            initial_packages = dict(initial_environment.installed)
            final_packages = dict(final_environment.installed)
            initial_dependencies = set()
            for dep in initial_opam_dependencies:
                for p in typing.cast(PackageFormula,
                                     PackageFormula.parse(dep)).packages:
                    if p in initial_packages:
                        initial_dependencies.add(p)
                    # else not a required dependency if not installed
            repaired_dependencies = set()
            for dep in final_opam_dependencies:
                for p in typing.cast(PackageFormula,
                                     PackageFormula.parse(dep)).packages:
                    if p in final_packages:
                        repaired_dependencies.add(p)
                    # else not a required dependency if not installed
            tags.update(
                {
                    f"dropped-dependency:{p}" for p in final_packages if
                    p in initial_dependencies and p not in repaired_dependencies
                })
            tags.update(
                {
                    f"new-dependency:{p}" for p in final_packages if
                    p not in initial_dependencies and p in repaired_dependencies
                })
            tags.update(
                {
                    f"updated-dependency:{p}" for p in final_packages
                    if p in initial_dependencies and p in repaired_dependencies
                    and initial_packages[p] != final_packages[p]
                })
        return tags

    @classmethod
    def get_qr_tags(
            cls,
            initial_qr: Set[Tuple[str,
                                  str]],
            broken_qr: Set[Tuple[str,
                                 str]],
            broken_rq: Set[Tuple[str,
                                 str]],
            is_Q: bool) -> Set[str]:
        """
        Update tags for an error instance given before/after QR flags.
        """
        tags = set()
        initial_qr_dict = bidict(initial_qr)
        broken_qr_dict = bidict(broken_qr)
        for physical, logical in initial_qr:
            if physical in broken_qr_dict:
                new_logical = broken_qr_dict[physical]
                if new_logical != logical:
                    tags.add(
                        f"changed-logical-{'Q' if is_Q else 'R'}-path:"
                        f"{physical}({logical} -> {new_logical})")
            elif logical not in broken_qr_dict.inv:
                tags.add(
                    f"dropped-{'Q' if is_Q else 'R'}-path:{physical},{logical}")
            if logical in broken_qr_dict.inv:
                new_physical = broken_qr_dict.inv[logical]
                if new_physical != physical:
                    tags.add(
                        f"changed-physical-{'Q' if is_Q else 'R'}-path:"
                        f"{logical}({physical} -> {new_physical})")
            if (physical, logical) in broken_rq:
                tags.add(
                    f"changed-{'Q' if is_Q else 'R'}-to-{'R' if is_Q else 'Q'}:"
                    f"{physical},{logical}")
        for physical, logical in broken_qr.difference(initial_qr):
            if (physical not in initial_qr_dict
                    and logical not in initial_qr_dict.inv):
                tags.add(
                    f"added-{'Q' if is_Q else 'R'}-path:{physical},{logical}")
        return tags

    @classmethod
    def default_get_error_tags(
            cls,
            broken_command: VernacCommandData,
            initial_state: ProjectCommitData,
            broken_state_diff: ProjectCommitDataDiff,
            broken_build_process: Optional[BuildProcess],
            broken_environment: Optional[OpamSwitch.Configuration],
            broken_dependencies: Optional[Iterable[str]]) -> Set[str]:
        """
        Get a default set of tags to apply to an error.

        The default set of tags identify the type of repaired command
        and additionally note that the repair instance has been
        artificially mined, that only one command is repaired in one
        file, and whether any dependencies have been updated, dropped,
        or added (including Coq version).

        Parameters
        ----------
        broken_command : VernacCommandData
            The command in need of repair
        initial_state : ProjectCommitData
            The initial state containing the broken command.
        broken_state_diff : ProjectCommitDataDiff
            A diff that can be applied the the `initial_state` to
            retrieve the entire broken state.
        broken_build_process : Optional[BuildProcess]
            The build process in which the command is broken.
        broken_environment : Optional[OpamSwitch.Configuration]
            The installed environment in which the command is broken.
        broken_dependencies : Optional[Iterable[str]]
            The requested dependencies of the broken project state as a
            collection of serialized package formulae.

        Returns
        -------
        tags : Set[str]
            A set of tags describing the error, each prefixed with
            ``'error'``.
        """
        tags = {
            broken_command.command_type,
            "artificial:mined",
            "one-command",
            "one-file"
        }
        tags.update(
            cls.get_environment_tags(
                initial_state.environment.switch_config
                if initial_state.environment is not None else None,
                initial_state.project_metadata.opam_dependencies,
                broken_environment,
                broken_dependencies))
        initial_build_process = BuildProcess.from_metadata(
            initial_state.project_metadata)
        tags.update(
            cls.get_build_process_tags(
                initial_build_process,
                broken_build_process))
        return {f"error:{t}" for t in tags}

    @classmethod
    def make_error_instance(
            cls,
            initial_state: ProjectCommitData,
            final_state: ProjectCommitData,
            commit_diff: Optional[ProjectCommitDataDiff] = None,
            changeset: Optional[ChangeSelection] = None,
            get_error_tags: Optional[ErrorAnnotator] = None,
            align: Optional[AlignmentFunction] = None,
            **kwargs) -> 'ProjectCommitDataErrorInstance':
        """
        Create an error instance from its constituent components.

        Parameters
        ----------
        initial_state : ProjectCommitData
            An initial state.
        final_state : ProjectCommitData
            Another commit's state presumed to occur after
            `initial_state`.
        commit_diff : Optional[ProjectCommitDataDiff], optional
            A precomputed diff between `initial_state` and
            `final_state`, by default None.
            If None, then the diff will be computed internally.
        changeset : Optional[ChangeSelection], optional
            A selection of changes from `commit_diff` on which to base
            the error instance.
            By default, the entirety of `commit_diff` is used.
        get_error_tags : Optional[ErrorAnnotator], optional
            A function that annotates an error with tags for subsequent
            filtering of the mined examples.
            By default, `default_get_error_ tags` is used.
        align : Optional[AlignmentFunction], optional
            If `commit_diff` is None, then the alignment algorithm used
            to compute the diff, by default `default_align`.
        kwargs
            Additional keyword arguments to
            `ProjectCommitDataDiff.from_commit_data`.

        Returns
        -------
        ProjectCommitDataErrorInstance
            An error instance corresponding to the given `changeset`.
        """
        if align is None:
            align = default_align
        diff = kwargs.pop('diff', None)
        if diff is None:
            diff = compute_git_diff(initial_state, final_state)
        return_aligned_commands = kwargs.pop(
            'return_aligned_commands',
            True) or True
        if commit_diff is None:
            commit_diff, aligned_commands = typing.cast(
                Tuple[ProjectCommitDataDiff, AlignedCommands],
                ProjectCommitDataDiff.from_commit_data(
                    initial_state,
                    final_state,
                    align,
                    diff=diff,
                    return_aligned_commands=return_aligned_commands,
                    **kwargs))
        else:
            alignment = align_commits(initial_state, final_state, diff, align)
            initial_state.patch_goals()
            final_state.patch_goals()
            initial_state.sort_commands()
            final_state.sort_commands()
            aligned_commands = get_aligned_commands(
                initial_state,
                final_state,
                alignment)
        if get_error_tags is None:
            get_error_tags = cls.default_get_error_tags
        broken_command_indices = {
            (f,
             idx) for f,
            idx,
            _ in commit_diff.changed_commands
        }
        if changeset is None:
            broken_state_diff = commit_diff.shallow_copy()
        else:
            broken_state_diff = ProjectCommitDataDiff(
                {
                    k: VernacCommandDataListDiff(offsets=list(v.offsets)) for k,
                    v in commit_diff.command_changes.items()
                },
                commit_diff.file_dependencies_diff)
            for filename, added_idx in changeset.added_commands:
                broken_state_diff.command_changes[
                    filename].added_commands.append(
                        commit_diff.command_changes[filename]
                        .added_commands[added_idx].shallow_copy())
            for filename, changed_idx in changeset.affected_commands:
                # no need to copy since SerializableDataDiff is
                # immutable
                broken_state_diff.command_changes[filename].affected_commands[
                    changed_idx] = commit_diff.command_changes[
                        filename].affected_commands[changed_idx]
            for filename, changed_idx in changeset.changed_commands:
                broken_state_diff.command_changes[filename].changed_commands[
                    changed_idx] = commit_diff.command_changes[
                        filename].changed_commands[changed_idx]
                broken_command_indices.discard((filename, changed_idx))
            # add in changed commands to actually be dropped later
            for filename, changed_idx in broken_command_indices:
                broken_state_diff.command_changes[filename].changed_commands[
                    changed_idx] = commit_diff.command_changes[
                        filename].changed_commands[changed_idx]
            for filename, dropped_idx in changeset.dropped_commands:
                broken_state_diff.command_changes[
                    filename].dropped_commands.add(dropped_idx)
        # "broken" commands are those that did not change
        # However, their location may still have changed, and we wish
        # to preserve that as otherwise its old location may clash with
        # other changes.
        # If the commmand stayed in the same file or not:
        #   Align the sentences of both versions (including nested
        #   commands), and shift each sentence to the start of its
        #   corresponding repaired version.
        #   If it spans fewer lines/characters, then do nothing else.
        #   If it spans more lines/characters, then shift all commands
        #   that appear after the changed version by the difference.
        # Note that the shifting occurs at patch time to avoid needing
        # to reconstruct all of the SerializableDataDiffs.
        # Nested commands introduce a significant complication.
        # The following possibilities are considered for nested
        # commands in two commits A and B where the former command x in
        # A is presumed to be broken with the latter command y in B
        # presumed to be its repaired version:
        # * a nested command w in A is no longer nested in B: this
        #   situation can be ignored as it will not impact the relative
        #   alignment of sentences between x and y. y already accounts
        #   for w's location, and w can be treated as an unrelated
        #   command during patching
        # * a nested command z in B was not nested in A: we can ignore
        #   the corresponding command in A of z (if any), but z's
        #   sentences must be taken into account when aligning x and y.
        # * a nested command

        # Treat sentences as the primary entities; no nesting to
        # consider, should reduce to the previous implementation with
        # sentence-based offsets and patching.
        broken_file_offsets = left_file_offsets_from_aligned_commands(
            aligned_commands)
        repaired_file_offsets = right_file_offsets_from_aligned_commands(
            aligned_commands)
        global_alignment_dict: Dict[str,
                                    Dict[int,
                                         Tuple[str,
                                               int]]] = {}
        for a, b in aligned_commands:
            if a is not None and b is not None:
                aidx, afile, _ = a
                bidx, bfile, _ = b
                local_alignment_dict = global_alignment_dict.setdefault(
                    afile,
                    {})
                local_alignment_dict[aidx - broken_file_offsets[afile]] = (
                    bfile,
                    bidx - repaired_file_offsets[bfile])
        broken_commands: List[VernacCommandData] = []
        for f, idx in broken_command_indices:
            broken_file = initial_state.command_data[f]
            (broken_command,
             repair_filename,
             offsets) = broken_state_diff.command_changes[f].drop_change(
                 idx,
                 broken_file,
                 final_state,
                 global_alignment_dict[f])
            broken_commands.append(broken_command)
            broken_state_diff.command_changes.setdefault(
                repair_filename,
                VernacCommandDataListDiff()).offsets.extend(offsets)
        error_instance = cls._make_error_instance(
            initial_state,
            broken_state_diff,
            BuildProcess.from_metadata(final_state.project_metadata),
            final_state.environment.switch_config
            if final_state.environment is not None else None,
            final_state.project_metadata.opam_dependencies,
            broken_commands,
            get_error_tags)
        return error_instance

    @classmethod
    def mine_error_examples(
            cls,
            initial_state: ProjectCommitData,
            repaired_state: ProjectCommitData,
            align: Optional[AlignmentFunction] = None,
            changeset_miner: Optional[ChangeSetMiner] = None,
            get_error_tags: Optional[ErrorAnnotator] = None,
            **kwargs) -> List['ProjectCommitDataErrorInstance']:
        """
        Mine a pair of commits for error examples.

        By default, error examples produced by this method comprise
        standalone broken commands (complete theorems, definitions,
        etc.) that have been modified between the commits.
        A virtual broken state is induced by partially applying the
        changes between the given commits such that changed commands are
        left out.
        The `changeset_miner` dictates which changes are left out in one
        or more derived changesets.
        The left-out change may constitute a presumptive "repair".
        One may observe that not all mined broken states are guaranteed
        to actually raise an error when compiled.

        Parameters
        ----------
        initial_state : ProjectCommitData
            An initial state, presumed to be without error.
        repaired_state : ProjectCommitData
            Another commit's state presumed to occur after
            `initial_state` and also be without error.
        align : Optional[AlignmentFunction], optional
            A function that may be used to align the commands of
            `initial_state` and `repaired_state`.
        changeset_miner : Optional[ChangeSetMiner], optional
            A function that selects sets of changes from the diff
            between `initial_state` and `repaired_state` to serve as
            error instances.
            By default, changesets are constructed by leaving each
            changed command out one at a time.
        get_error_tags : Optional[RepairAnnotator], optional
            A function that annotates an error with tags for subsequent
            filtering of the mined examples.
            By default, `default_get_error_tags` is used.
        kwargs
            Optional keyword arguments to
            `ProjectCommitDataDiff.from_commit_data`, e.g., a
            pre-computed diff.

        Returns
        -------
        List['ProjectCommitDataErrorInstance']
            A list of mined error instances.
        """
        if align is None:
            align = default_align
        if changeset_miner is None:
            changeset_miner = cls.default_changeset_miner
        if get_error_tags is None:
            get_error_tags = cls.default_get_error_tags
        # sort commands for reproducible indexing of commands in
        # produced diffs
        initial_state.sort_commands()
        commit_diff = typing.cast(
            ProjectCommitDataDiff,
            ProjectCommitDataDiff.from_commit_data(
                initial_state,
                repaired_state,
                align,
                **kwargs))
        error_instances: List[ProjectCommitDataErrorInstance] = []
        for changeset in changeset_miner(initial_state, commit_diff):
            # make two partial diffs
            # one partial diff creates a presumed broken state
            error_instance = cls.make_error_instance(
                initial_state,
                repaired_state,
                commit_diff,
                changeset,
                get_error_tags)
            error_instances.append(error_instance)
        return error_instances


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
                                                     ProjectCommitDataDiff,
                                                     BuildProcess]):
    """
    A concise example of a repair in its most raw and unprocessed form.

    With this representation, one should be able to capture errors and
    repairs due to both changes to the source code and changes in
    environment.
    """

    _repair_commit_tag: ClassVar[str] = "repair:commit:"

    def __post_init__(self):
        """
        Patch generic attributes to non-generic subclasses.
        """
        if not isinstance(self.error, ProjectCommitDataErrorInstance):
            self.error = ProjectCommitDataErrorInstance(
                self.error.project_name,
                self.error.initial_state,
                self.error.change,
                self.error.error_location,
                self.error.tags)
        if isinstance(self.repaired_state_or_diff, ProjectState):
            if not isinstance(self.repaired_state_or_diff,
                              ProjectCommitDataState):
                self.repaired_state_or_diff = ProjectCommitDataState(
                    self.repaired_state_or_diff.project_state,
                    self.repaired_state_or_diff.offset,
                    self.repaired_state_or_diff._build_process,
                    self.repaired_state_or_diff._environment)
        elif isinstance(self.repaired_state_or_diff, ProjectStateDiff):
            if not isinstance(self.repaired_state_or_diff,
                              ProjectCommitDataStateDiff):
                self.repaired_state_or_diff = ProjectCommitDataStateDiff(
                    self.repaired_state_or_diff.diff,
                    self.repaired_state_or_diff.build_process,
                    self.repaired_state_or_diff.environment)
        else:
            raise TypeError(
                "repaired_state_or_diff must be a state or a diff, "
                f"got {type(self.repaired_state_or_diff)}")

    @property
    def tags(self) -> Set[str]:
        """
        The set of tags assigned to this repair instance.
        """
        return self.error.tags

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
            repaired = repaired.compress(error.build_process, error.environment)
        else:
            repaired = cast_from_base_cls(
                ProjectCommitDataStateDiff,
                self.repaired_state_or_diff,
                ProjectStateDiff)
            repaired_commit_sha = None
            tag = None
            for tag in self.tags:
                if tag.startswith(self._repair_commit_tag):
                    repaired_commit_sha = tag[len(self._repair_commit_tag):]
                    break
            if repaired_commit_sha is not None:
                # we can just save the commit SHA instead of the diff
                repaired = GitProjectState(
                    repaired_commit_sha,
                    None,
                    repaired.build_process
                    if repaired.build_process != error.build_process else None,
                    repaired.environment
                    if repaired.environment != error.environment else None)
                # remove the now-redundant tag
                assert tag is not None
                error.tags.discard(tag)
            else:
                repaired = typing.cast(ProjectCommitDataStateDiff, repaired)
                repaired = repaired.compress(
                    error.error_state,
                    error.build_process,
                    error.environment)
        repaired = typing.cast(
            Union[GitProjectState,
                  GitProjectStateDiff],
            repaired)
        return GitRepairInstance(error.compress(), repaired)

    @classmethod
    def _make_repair_instance(
        cls,
        initial_state: ProjectCommitData,
        broken_state_diff: ProjectCommitDataDiff,
        broken_state: ProjectCommitData,
        repaired_state_diff: ProjectCommitDataDiff,
        repaired_state: ProjectCommitData,
        broken_command: VernacCommandData,
        repair: SerializableDataDiff[VernacCommandData],
        get_tags: RepairAnnotator,
    ) -> 'ProjectCommitDataRepairInstance':
        """
        Create the actual repair instance.
        """
        repaired_build_process: Optional[
            BuildProcess] = BuildProcess.from_metadata(
                repaired_state.project_metadata)
        if repaired_build_process == BuildProcess.from_metadata(
                initial_state.project_metadata):
            repaired_build_process = None
        repaired_environment = None
        if repaired_state.environment is not None:
            repaired_environment = repaired_state.environment.switch_config
            if initial_state.environment is not None:
                initial_environment = initial_state.environment.switch_config
                if repaired_environment == initial_environment:
                    repaired_environment = None
        repair_instance = ProjectCommitDataRepairInstance(
            error=ProjectCommitDataErrorInstance(
                project_name=initial_state.project_metadata.project_name,
                initial_state=ProjectCommitDataState(initial_state,
                                                     None,
                                                     None),
                change=ProjectCommitDataStateDiff(broken_state_diff,
                                                  None),
                error_location={broken_command.command.location},
                tags=get_tags(
                    broken_command,
                    repair,
                    broken_state,
                    repaired_state)),
            repaired_state_or_diff=ProjectCommitDataStateDiff(
                repaired_state_diff,
                repaired_build_process,
                repaired_environment))
        return repair_instance

    @classmethod
    def default_changeset_miner(
        cls,
        initial_state: ProjectCommitData,
        commit_diff: ProjectCommitDataDiff,
        error_filter: Optional[Callable[[VernacCommandData],
                                        bool]] = None
    ) -> List[ChangeSelection]:
        r"""
        Make selections by dropping individual changed commands.

        Parameters
        ----------
        initial_state : ProjectCommitData
            The initial state of the project.
        commit_diff : ProjectCommitDataDiff
            Changes to the state from which selections will be made.
        error_filter : Optional[Callable[[VernacCommandData], bool]], \
                optional
            An optional filter one may use to skip dropping certain
            commands, e.g., to create changes that drop only altered
            proofs, by default None.

        Returns
        -------
        selected_changes : List[ChangeSelection]
            A list of selected changesets.
        """
        selected_changes: List[ChangeSelection] = []
        for filename, command_index, _ in commit_diff.changed_commands:
            # make an example for each filtered, *changed* command
            original_command = initial_state.command_data[filename][
                command_index]
            if error_filter is None or error_filter(original_command):
                # this command is not filtered out
                added_commands = [
                    (f,
                     idx)
                    for f,
                    file_changes in commit_diff.command_changes.items()
                    for idx in range(len(file_changes.added_commands))
                ]
                affected_commands = [
                    (f,
                     idx) for f,
                    idx,
                    _ in commit_diff.affected_commands
                ]
                # drop command in selection
                changed_commands = [
                    (f,
                     idx)
                    for f,
                    idx,
                    _ in commit_diff.changed_commands
                    if f != filename or idx != command_index
                ]
                dropped_commands = list(commit_diff.dropped_commands)
                selected_changes.append(
                    ChangeSelection(
                        added_commands,
                        affected_commands,
                        changed_commands,
                        dropped_commands))
        return selected_changes

    @classmethod
    def default_get_error_tags(cls, *args, **kwargs) -> Set[str]:
        """
        Get a default set of tags to apply to an error.

        See Also
        --------
        ProjectCommitDataErrorInstance.default_get_error_tags : For API
        """
        return ProjectCommitDataErrorInstance.default_get_error_tags(
            *args,
            **kwargs)

    @classmethod
    def default_get_repair_tags(
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
            A set of tags describing the repair, each prefixed with
            ``'repair'``.
        """
        tags = {
            f"{broken_command.command_type}",
            "artificial:mined",
            "one-command",
            "one-file"
        }
        repaired_command = repair.patch(broken_command)
        if repaired_command.command.text != broken_command.command.text:
            tags.add("specification")
        if repaired_command.proof_text() != broken_command.proof_text():
            tags.add("proof")
        tags.update(
            ProjectCommitDataErrorInstance.get_environment_tags(
                initial_state.environment.switch_config
                if initial_state.environment is not None else None,
                initial_state.project_metadata.opam_dependencies,
                repaired_state.environment.switch_config
                if repaired_state.environment is not None else None,
                repaired_state.project_metadata.opam_dependencies))
        tags.update(
            ProjectCommitDataErrorInstance.get_build_process_tags(
                BuildProcess.from_metadata(initial_state.project_metadata),
                BuildProcess.from_metadata(repaired_state.project_metadata)))
        return {f"repair:{t}" for t in tags}

    @classmethod
    def make_repair_instance(
        cls,
        error_instance: ProjectCommitDataErrorInstance,
        repaired_state: ProjectCommitData,
        align: Optional[AlignmentFunction] = None,
        get_repair_tags: Optional[RepairAnnotator] = None
    ) -> 'ProjectCommitDataRepairInstance':
        """
        Create a repair instance from a given error instance.

        Parameters
        ----------
        error_instance : ProjectCommitDataErrorInstance
            A preconstructed example of an error.
        repaired_state : ProjectCommitData
            A state based on that of `error_instance` that is presumed
            to be repaired.
        align : Optional[AlignmentFunction], optional
            The alignment algorithm to use when constructing the diff
            between the error instance's state and `repaired_state, by
            default `default_align`.
        get_repair_tags : Optional[RepairAnnotator], optional
            A function that annotates a repair with tags for subsequent
            filtering of the mined examples.
            By default, `default_get_repair_tags` is used.

        Returns
        -------
        ProjectCommitDataRepairInstance
            The repair instance.
        """
        if align is None:
            align = default_align
        if get_repair_tags is None:
            get_repair_tags = cls.default_get_repair_tags
        broken_state = error_instance.error_state
        # sort commands for reproducible indexing of commands in
        # produced diffs
        broken_state.sort_commands()
        # the other partial diff repairs the broken state
        repaired_state_diff = typing.cast(
            ProjectCommitDataDiff,
            ProjectCommitDataDiff.from_commit_data(
                broken_state,
                repaired_state,
                align))
        # get the broken commands
        added = list(repaired_state_diff.added_commands)
        repaired = list(repaired_state_diff.changed_commands)
        dropped = list(repaired_state_diff.dropped_commands)
        assert added or repaired or dropped, \
            "Something should have been repaired"
        # generate repair tags
        tags = error_instance.tags
        for filename, broken_command_index, repair in repaired:
            broken_command = broken_state.command_data[filename][
                broken_command_index]
            tags.update(
                get_repair_tags(
                    broken_command,
                    repair,
                    broken_state,
                    repaired_state))
        # assemble the repair instance
        repaired_build_process: Optional[
            BuildProcess] = BuildProcess.from_metadata(
                repaired_state.project_metadata)
        if repaired_build_process == BuildProcess.from_metadata(
                broken_state.project_metadata):
            repaired_build_process = None
        repaired_environment = None
        if repaired_state.environment is not None:
            repaired_environment = repaired_state.environment.switch_config
            if broken_state.environment is not None:
                initial_environment = broken_state.environment.switch_config
                if repaired_environment == initial_environment:
                    repaired_environment = None
        repair_instance = cls(
            error_instance,
            ProjectCommitDataStateDiff(
                repaired_state_diff,
                repaired_build_process,
                repaired_environment))
        # make sure the repaired state's identity gets captured
        if repaired_state.project_metadata.commit_sha is not None:
            repair_instance.error.tags.add(
                ''.join(
                    [
                        cls._repair_commit_tag,
                        repaired_state.project_metadata.commit_sha
                    ]))
        return repair_instance

    @classmethod
    def mine_repair_examples(
            cls,
            initial_state: ProjectCommitData,
            repaired_state: ProjectCommitData,
            align: Optional[AlignmentFunction] = None,
            changeset_miner: Optional[ChangeSetMiner] = None,
            get_error_tags: Optional[ErrorAnnotator] = None,
            get_repair_tags: Optional[RepairAnnotator] = None,
            **kwargs) -> List['ProjectCommitDataRepairInstance']:
        """
        Mine a pair of commits for repair examples.

        Repair examples produced by this method comprise standalone
        commands (complete theorems, definitions, etc.) that have been
        modified between the commits.
        A virtual broken state is induced by partially applying the
        changes between the given commits such that one changed command
        is left out.
        The left-out change constitutes the presumptive "repair".
        One may observe that not all mined broken states are guaranteed
        to actually raise an error when compiled.
        In such cases, one may infer the "repair" to be simply a
        directive to follow the original user's intention.

        Parameters
        ----------
        initial_state : ProjectCommitData
            An initial state.
        repaired_state : ProjectCommitData
            Another commit's state presumed to occur after
            `initial_state` and be without error.
        align : Optional[AlignmentFunction], optional
            The alignment algorithm to use when constructing diffs
            between project commit states, namely the `initial_state`,
            `repaired_state`, and derived broken state(s).
        changeset_miner : Optional[ChangeSetMiner], optional
            A function that selects sets of changes from the diff
            between `initial_state` and `repaired_state` to serve as
            error instances.
            By default, changesets are constructed by leaving each
            changed command out one at a time.
            Consequently, every changed command is extracted as a repair
            example.
        get_error_tags : Optional[RepairAnnotator], optional
            A function that annotates an error with tags for subsequent
            filtering of the mined examples.
            By default, `default_get_error_tags` is used.
        get_repair_tags : Optional[RepairAnnotator], optional
            A function that annotates a repair with tags for subsequent
            filtering of the mined examples.
            By default, `default_get_repair_tags` is used.
        kwargs
            Optional keyword arguments to
            `ProjectCommitDataDiff.from_commit_data`, e.g., a
            pre-computed diff.

        Returns
        -------
        List['ProjectCommitDataRepairInstance']
            A list of mined repair instances.
        """
        if align is None:
            align = default_align
        if changeset_miner is None:
            changeset_miner = cls.default_changeset_miner
        if get_error_tags is None:
            get_error_tags = cls.default_get_error_tags
        if get_repair_tags is None:
            get_repair_tags = cls.default_get_repair_tags
        error_instances = ProjectCommitDataErrorInstance.mine_error_examples(
            initial_state,
            repaired_state,
            align,
            changeset_miner,
            get_error_tags,
            **kwargs)
        repair_instances = [
            cls.make_repair_instance(
                error_instance,
                repaired_state,
                align,
                get_repair_tags) for error_instance in error_instances
        ]
        return repair_instances
