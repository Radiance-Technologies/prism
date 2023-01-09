"""
Defines representations of repair instances (or examples).
"""

import copy
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

import numpy as np

from prism.data.build_cache import (
    ProjectCommitData,
    VernacCommandData,
    VernacCommandDataList,
)
from prism.data.repair.align import AlignedCommands, get_aligned_commands
from prism.language.gallina.analyze import SexpInfo
from prism.util.diff import GitDiff
from prism.util.opam import OpamSwitch
from prism.util.radpytools.dataclasses import default_field


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
            b.lineno_last - b.lineno_last,
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
    moved_commands: Dict[int,
                         List[LocDiff]] = default_field({})
    """
    A map from command indices in the original file to destinations
    indicating where the indexed commands should be moved.
    Note that the destinations may be in other files.
    The commands are presumed to not otherwise be modified in form or
    content.
    A list of location diffs is included, one for each of the sentences
    that may be included in the command.
    """
    changed_commands: Dict[int,
                           VernacCommandData] = default_field({})
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

    def patch(self, data: ProjectCommitData) -> ProjectCommitData:
        """
        Apply this diff to given project data.

        Parameters
        ----------
        data : ProjectCommitData
            Extracted command data from a commit.

        Returns
        -------
        ProjectCommitData
            The patched commit data.
        """
        result = copy.deepcopy(data)
        result_command_data = result.command_data
        # decompose moves and changes into drops and adds
        dropped_commands: Dict[str,
                               Set[int]] = {}
        added_commands: Dict[str,
                             VernacCommandDataList] = {}
        for filename, change in self.changes.items():
            dropped = dropped_commands.setdefault(filename, set())
            dropped.update(change.dropped_commands)
            dropped.update(change.moved_commands.keys())
            dropped.update(change.changed_commands.keys())
            added = added_commands.setdefault(filename, VernacCommandDataList())
            added.extend(change.added_commands)
            for moved_idx, loc_diffs in change.moved_commands.items():
                assert loc_diffs, "moves require destinations"
                assert all(
                    ld.after_filename == loc_diffs[0].after_filename
                    for ld in loc_diffs), "commands move atomically"
                added = added_commands.setdefault(
                    loc_diffs[0].after_filename,
                    VernacCommandDataList())
                for (sentence,
                     loc_diff) in zip(result_command_data[filename]
                                      [moved_idx].sorted_sentences(),
                                      loc_diffs):
                    sentence.location = loc_diff.patch(sentence.location)
            for command in change.changed_commands.values():
                added = added_commands.setdefault(
                    command.location.filename,
                    VernacCommandDataList())
                added.append(command)
        # apply changes
        for filename, added in added_commands.items():
            dropped = dropped_commands.setdefault(filename, set())
            try:
                command_data = result_command_data[filename]
            except KeyError:
                command_data = VernacCommandDataList()
                assert not dropped, "cannot drop commands from non-existent files"
            command_data = VernacCommandDataList(
                [c for i,
                 c in enumerate(command_data) if i not in dropped])
            command_data.extend(added)
            if command_data:
                result_command_data[filename] = command_data
            else:
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
        aidx = 0
        for a, b in aligned_commands:
            if a is None:
                # added command
                assert b is not None, "cannot skip both sequences in alignment"
                filename, cmd = b
                file_diff = changes.setdefault(
                    filename,
                    VernacCommandDataListDiff())
                file_diff.added_commands.append(cmd)
            elif b is None:
                # dropped command
                assert a is not None, "cannot skip both sequences in alignment"
                filename, _ = a
                try:
                    offset = a_file_offsets[filename]
                except KeyError:
                    offset = aidx
                    a_file_offsets[filename] = offset
                file_diff = changes.setdefault(
                    filename,
                    VernacCommandDataListDiff())
                file_diff.dropped_commands.add(aidx - offset)
                aidx += 1
            else:
                # a command with a match
                filename, acmd = a
                _, bcmd = b
                try:
                    offset = a_file_offsets[filename]
                except KeyError:
                    offset = aidx
                    a_file_offsets[filename] = offset
                file_diff = changes.setdefault(
                    filename,
                    VernacCommandDataListDiff())
                if acmd.all_text != bcmd.all_text:
                    # changed command
                    file_diff.changed_commands[aidx - offset] = bcmd
                elif acmd.spanning_location() != bcmd.spanning_location():
                    # the command was moved but otherwise unchanged
                    file_diff.moved_commands[aidx - offset] = [
                        LocDiff.compute_diff(k.location,
                                             l.location) for k,
                        l in zip(
                            acmd.sorted_sentences(),
                            bcmd.sorted_sentences())
                    ]
                # else the command is unchanged and not in the diff
                aidx += 1
        return result

    @classmethod
    def from_commit_data(
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
        return cls.from_aligned_commands(get_aligned_commands(a, b, alignment))


@dataclass
class ProjectRepoState:
    """
    The state of a project.
    """

    commit_sha: str
    """
    A hash identifying a commit within a Git repository.
    """
    offset: Optional[GitDiff] = None
    """
    A set of changes relative to the `commit_sha`.

    This field is useful for representing working tree changes.
    """
    environment: Optional[OpamSwitch.Configuration] = None
    """
    The environment in which the project is built.

    This field identifies other installed package versions including the
    Coq compiler.
    """


@dataclass
class ProjectStateDiff:
    """
    A change in some implicit project's state.
    """

    diff: GitDiff
    """
    A refactor or other change to some implicit state.
    """
    environment: Optional[OpamSwitch.Configuration] = None
    """
    The changed environment.

    If None, then it is understood to be the same environment as the
    implicit state.
    """


@dataclass
class ErrorInstance:
    """
    A concise example of an error in its most raw and unprocessed form.

    With this representation, one should be able to capture errors
    induced by changes to source code and/or environment.
    """

    project_name: str
    """
    An identifier that uniquely determines the project and is implicitly
    linked to a Git repository through some external correspondence.
    """
    initial_state: ProjectRepoState
    """
    An initial project state.

    A state of the project, nominally taken to be prior to a change that
    introduced a broken proof or other bug.
    """
    change: ProjectStateDiff
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


@dataclass
class RepairInstance:
    """
    A concise example of a repair in its most raw and unprocessed form.

    With this representation, one should be able to capture errors and
    repairs due to both changes to the source code and changes in
    environment.
    """

    error: ErrorInstance
    """
    An erroneous project state.
    """
    repaired_state: ProjectRepoState
    """
    A repaired proof state.

    A state of the project after an error induced by the change has been
    fixed.
    If the environment is None, then it is understood to be the same
    environment in which the error occurs.
    """
