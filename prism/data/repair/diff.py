"""
Utility functions related to Git diffs useful for repair examples.
"""

import re
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Set

import seutil.bash as bash

from prism.data.extraction.build_cache import (
    ProjectCommitData,
    VernacCommandData,
)
from prism.language.gallina.analyze import SexpInfo
from prism.util.diff import Change, GitDiff


def is_location_in_change(
        loc: SexpInfo.Loc,
        change: Change,
        is_before: bool) -> bool:
    """
    Return whether a location intersects a given change.

    Parameters
    ----------
    loc : SexpInfo.Loc
        A location.
    change : Change
        A change in a file.
    is_before : bool
        Whether to check if this location intersects the range of
        changed lines in the original file (True) or if it intersects
        the range of lines in the altered file (False).

    Returns
    -------
    bool
        True if the location intersects the diff, False otherwise.

    Notes
    -----
    `SexpInfo.Loc` line numbers are zero-indexed whereas diff line
    numbers are one-indexed.
    """
    if is_before:
        change_filename = str(change.before_filename)
        change_range = change.before_range
    else:
        change_filename = str(change.after_filename)
        change_range = change.after_range
    # make change line numbers zero-indexed
    change_range = range(change_range.start - 1, change_range.stop - 1)
    is_change_nonempty = bool(change_range)
    loc_intersects_change = (
        is_change_nonempty and (
            loc.contains_lineno(change_range.start)
            or loc.contains_lineno(change_range.stop - 1)))
    loc_contains_empty_change = (
        not is_change_nonempty and loc.contains_lineno(change_range.start)
        and change_range.start != loc.lineno)
    return change_filename == loc.filename and (
        # if there is any intersection, then one endpoint lies in the
        # interval spanned by the change
        loc.lineno in change_range or loc.lineno_last in change_range
        or loc_intersects_change or loc_contains_empty_change)


def is_location_in_diff(
        loc: SexpInfo.Loc,
        diff: GitDiff,
        is_before: bool) -> bool:
    """
    Return whether a location intersects a given diff.

    Parameters
    ----------
    loc : SexpInfo.Loc
        A location.
    diff : GitDiff
        A collection of changes in a project.
    is_before : bool
        Whether to check if this location intersects any range of
        changed lines in an original file (True) or if it intersects
        any range of lines in an altered file (False).

    Returns
    -------
    bool
        True if the location intersects the diff, False otherwise.
    """
    return any(
        is_location_in_change(loc,
                              change,
                              is_before) for change in diff.changes)


def locations_in_diff(
        locs: Iterable[SexpInfo.Loc],
        diff: GitDiff,
        is_before: bool) -> List[int]:
    """
    Get the indices of a sequence of locations that intersect a diff.

    Parameters
    ----------
    locs : Iterable[SexpInfo.Loc]
        A sequence of locations.
    diff : GitDiff
        A collection of changes in a project.
    is_before : bool
        Whether to check if each location intersects any range of
        changed lines in an original file (True) or if it intersects
        any range of lines in an altered file (False).

    Returns
    -------
    List[int]
        A list containing the indices of locations in `locs` in
        ascending order that intersect the given `diff`.
    """
    return [
        i for i,
        loc in enumerate(locs) if is_location_in_diff(loc,
                                                      diff,
                                                      is_before)
    ]


def commands_in_diff(data: ProjectCommitData,
                     diff: GitDiff,
                     is_before: bool) -> Dict[str,
                                              List[int]]:
    """
    Get the indices of a project's commands that intersect a diff.

    Parameters
    ----------
    data : ProjectCommitData
        Extracted data for a commit in a project.
    diff : GitDiff
        A collection of changes in a project.
    is_before : bool
        Whether to check if each command intersects any range of
        changed lines in an original file (True) or if it intersects
        any range of lines in an altered file (False).

    Returns
    -------
    Dict[str, List[int]]
        A map from filenames in ``data.command_data`` to the indices of
        files' respective commands that intersect the given `diff`.
    """
    return {
        k: locations_in_diff(
            (c.spanning_location() for c in v),
            diff,
            is_before) for k,
        v in data.command_data.items()
    }


def get_changes_to_command(
        command: VernacCommandData,
        changes: Iterable[Change],
        is_before: bool) -> Set[Change]:
    """
    Get the subset of changes to this command from a larger collection.

    Parameters
    ----------
    command : VernacCommandData
        A command.
    changes : Iterable[Change]
        A collection of changes.
    is_before : bool
        Whether the command should be considered to exist before or
        after the change.

    Returns
    -------
    Set[Change]
        The subset of `changes` to the `command`.
    """
    command_location = command.spanning_location()
    return {
        c for c in changes
        if is_location_in_change(command_location,
                                 c,
                                 is_before)
    }


def compute_git_diff(a: ProjectCommitData, b: ProjectCommitData) -> GitDiff:
    """
    Compute a diff between extracted commits.

    Parameters
    ----------
    a, b : ProjectCommitData
        Command data extracted from two commits.
        Note that there is no requirement for the commits to be from the
        same project.

    Returns
    -------
    GitDiff
        The diff between the commits.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        a_dir = Path(tmpdir) / "a"
        b_dir = Path(tmpdir) / "b"
        a.write_coq_project(a_dir)
        b.write_coq_project(b_dir)
        r = bash.run(f"git diff --no-index -U0 {a_dir} {b_dir}")
    # remove temporary file paths
    diff = re.sub(f"{a_dir}|{b_dir}", '', r.stdout)
    return GitDiff(diff)
