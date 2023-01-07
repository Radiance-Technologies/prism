"""
Utility functions related to Git diffs useful for repair examples.
"""
from typing import Dict, Iterable, List

from prism.data.build_cache import ProjectCommitData
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
    """
    if is_before:
        change_filename = change.before_filename
        change_range = change.before_range
    else:
        change_filename = change.after_filename
        change_range = change.after_range
    return change_filename == loc.filename and change_range and (
        # if there is any intersection, then one endpoint lies in the
        # interval spanned by the change
        loc.lineno in change_range or loc.lineno_last in change_range)


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