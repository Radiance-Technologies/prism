"""
Tools for aligning the same proofs across commits.
"""

import enum
import math
import warnings
from functools import partial
from typing import Callable, Dict, List, Optional, Tuple, TypeVar, Union

import numpy as np
from Levenshtein import distance as levenshtein
from scipy.optimize import linear_sum_assignment

from prism.data.cache.types import (
    ProjectCommitData,
    VernacCommandData,
    VernacCommandDataList,
    VernacSentence,
)
from prism.data.repair.diff import commands_in_diff
from prism.util.alignment import Alignment, lazy_align
from prism.util.diff import GitDiff
from prism.util.iterable import fast_contains

T = TypeVar('T')

Assignment = np.ndarray
"""
An array of pairs of integers indicating the indices of assigned object
pairs from two implicit indexed sets.
A row :math:`(i,j)` indicates that the :math:`i`-th command in the first
commit is assigned to the :math:`j`-th command in the second commit.
Unassigned commands in either commit are not enumerated in the array,
and there is no prescribed order in which the rows must be combined.
Indices may be ordered in any manner.
"""

AlignmentFunction = Callable[[ProjectCommitData, ProjectCommitData], Assignment]
"""
A function that takes two commits and produces an alignment/assignment
between their commands as a two-dimensional Numpy array with :math:`m`
rows corresponding to :math:`m` aligned command pairs and 2 columns.
A row :math:`(i,j)` indicates that the :math:`i`-th command in the first
commit is assigned to the :math:`j`-th command in the second commit.
Unassigned commands in either commit are not enumerated in the array,
and there is no prescribed order in which the rows must be combined.
"""


class Norm(enum.Enum):
    """
    A normalization that can be applied to a distance function.
    """

    MAX = enum.auto()
    """
    Normalize by dividing by the maximum norm of both inputs.
    """
    PRODUCT = enum.auto()
    """
    Normalize by dividing by the square root of both inputs' norms.
    """
    TANIMOTO = enum.auto()
    """
    Apply the biotope transform to obtain the Tanimoto distance.
    """

    def apply(
            self,
            D: Callable[[T,
                         T],
                        float],
            a: T,
            b: T,
            norm: Optional[Callable[[T],
                                    float]] = None,
            zero: Optional[T] = None) -> float:
        """
        Apply the normalization to a given distance function.

        The distance function is presumed to be non-negative and
        symmetric.

        Parameters
        ----------
        D : Callable[[T, T], float]
            A distance function.
        a : T
            The first argument to the distance function.
        b : T
            The second argument to the distance function.
        norm : Callable[[T], float] | None, optional
            A function that computes the norm of an input to `D`.
            For the result to be a guaranteed normalization, the
            function should satisfy ``norm(c) == D(c, zero)`` for any
            choice of ``c``.
        zero : T | None, optiona
            The identity element of type `T` satisfying
            ``norm(zero) == 0``.
            This argument must be provided if `norm` is not.

        Returns
        -------
        float
            The normalized distance between the given inputs.

        Raises
        ------
        ValueError
            If `norm` and `zero` are not given.
        """
        if norm is None:
            if zero is None:
                raise ValueError("Either 'norm' or 'zero' must be provided.")
            else:

                def norm(c: T) -> float:
                    assert zero is not None
                    return D(c, zero)

        distance = D(a, b)
        norm_a = norm(a)
        norm_b = norm(b)
        if norm_a == 0 and norm_b == 0:
            # both inputs are by definition equal to `zero`
            distance = 0
        elif self == Norm.MAX:
            distance = distance / max(norm_a, norm_b)
        elif self == Norm.PRODUCT:
            distance = norm_a + norm_b - distance
            distance = distance / (2 * math.sqrt(norm_a * norm_b))
            distance = 1 - distance / 2
        elif self == Norm.TANIMOTO:
            distance = 2 * distance / (norm_a + norm_b + distance)
        return distance


def thresholded_distance(
        D: Callable[[T,
                     T],
                    float],
        a: T,
        b: T,
        threshold: float) -> float:
    """
    Apply a threshold to a given distance function.

    Parameters
    ----------
    D : Callable[[T, T], float]
        A distance function.
    a : T
        The first argument to the distance function.
    b : T
        The second argument to the distance function.
    threshold : float
        An upper limit on the distance.

    Returns
    -------
    float
        The thresholded distance between two inputs.
    """
    if threshold < 0:
        raise ValueError(
            f"Distance threshold must be non-negative, got {threshold}")
    distance = D(a, b)
    distance = min(distance, float(threshold))
    return distance


def normalized_edit_distance(
        a: str,
        b: str,
        norm: Norm = Norm.TANIMOTO) -> float:
    """
    Find the cost of aligning two strings.

    Returns a value independent of the length of the strings, where 0.0
    is the best possible alignment (``a == b``) and 1.0 is the worst
    possible alignment.
    """
    return norm.apply(levenshtein, a, b, len)


def thresholded_edit_distance(
        a: str,
        b: str,
        threshold: float = 0.4,
        norm: Norm = Norm.TANIMOTO) -> float:
    """
    Find the cost of aligning two strings.

    Returns a value independent of the length of the strings, where 0.0
    is the best possible alignment (``a == b``) and `threshold` is the
    worst possible alignment.
    """
    if threshold >= 1:
        warnings.warn("A threshold greater than 1 will not have any effect")
    normed_distance = partial(normalized_edit_distance, norm=norm)
    return thresholded_distance(normed_distance, a, b, threshold)


def command_text_distance(
        D: Callable[[str,
                     str],
                    float],
        a: VernacCommandData,
        b: VernacCommandData) -> float:
    """
    Create a distance function between commands based on their text.
    """
    return D(a.command.text, b.command.text)


def default_command_distance(
        a: VernacCommandData,
        b: VernacCommandData) -> float:
    """
    Return the default distance between commands.
    """
    return command_text_distance(thresholded_edit_distance, a, b)


def order_preserving_alignment(
        a: List[VernacSentence],
        b: List[VernacSentence],
        alpha: float = 0.1) -> Alignment:
    """
    Align two lists of `VernacSentence`s.

    The order of each sequence is preserved after alignment, i.e., the
    resulting aligned indices are monotonically increasing.

    Parameters
    ----------
    a, b : List[VernacSentence]
        Sequences of `VernacSentence` to be aligned.
        Only the plaintext of the sentences are used in the alignment.
    alpha : float, optional
        An optional hyperparameter, by default 0.1, that controls the
        trade-off between skipping an element versus mismatching.
        A value of 1.0 always mismatches and a value of 0.0 always
        skips.

    Returns
    -------
    Alignment
        A list of tuples of `Optional` integers representing aligned
        one-indexed indices.
        For example, ``(0,0)`` matches the first element of `a` to the
        first element of `b`.
        Alternatively, ``(0,None)`` matches the first element of `a` to
        no element of `b`, skipping it.
    """
    return lazy_align(
        range(len(a)),
        range(len(b)),
        lambda x,
        y: normalized_edit_distance(a[x].text,
                                    b[y].text),
        lambda _: alpha)


def align_commits_per_file(
        a: ProjectCommitData,
        b: ProjectCommitData) -> Assignment:
    """
    Align two `ProjectCommit` based on matching files.

    Aligns commands in files pairwise based on file names.
    Files that have been renamed or removed between the two commits are
    not included.
    Consequently, the quality of the alignment will suffer in such
    scenarios.

    Parameters
    ----------
    a, b : ProjectCommitData
        Command data extracted from two commits of a project.

    Returns
    -------
    Assignment
        An array of pairs of integers indicating the indices of aligned
        commands between each commit with commands enumerated over all
        matching files in `a` and `b`.
        For example, ``(0,0)`` matches the first element of the first
        file of `a` to the first element of the first file of `b`.
        Indices of elements in either `a` or `b` that were skipped in
        the alignment do not appear in the output.

    Warns
    -----
    UserWarning
        If `a` and `b` belong to different projects.
    """
    if a.project_metadata.project_name != b.project_metadata.project_name:
        warnings.warn(
            "Cannot align files from different projects: "
            f"{a.project_metadata.project_name} and {b.project_metadata.project_name}"
        )

    # only attempt to align files present in both roots.
    alignable_files = a.command_data.keys() & b.command_data.keys()
    aligned_files: List[np.ndarray] = []

    a_files = a.files
    b_files = b.files

    a_file_offsets = dict(
        zip(
            a_files,
            [0] + list(np.cumsum([len(a.command_data[x]) for x in a_files]))))
    b_file_offsets = dict(
        zip(
            b_files,
            [0] + list(np.cumsum([len(b.command_data[x]) for x in b_files]))))

    for f in a_files:
        if f not in alignable_files:
            continue
        a_sentences = [x.command for x in a.command_data[f]]
        b_sentences = [x.command for x in b.command_data[f]]
        aligned_sentences = np.asarray(
            list(
                filter(
                    lambda x: x[0] is not None and x[1] is not None,
                    order_preserving_alignment(a_sentences,
                                               b_sentences))),
            dtype=int)
        # seek to the right part of the alignment
        a_offset = a_file_offsets[f]
        b_offset = b_file_offsets[f]
        aligned_sentences += np.resize(
            np.array([a_offset,
                      b_offset],
                     dtype=int),
            aligned_sentences.shape)
        aligned_files.append(aligned_sentences)
    alignment = np.concatenate(aligned_files, axis=0, dtype=int)
    return alignment


def assign_commits(
        a: ProjectCommitData,
        b: ProjectCommitData,
        cost_function: Callable[[VernacCommandData,
                                 VernacCommandData],
                                float],
        threshold: float = np.inf) -> Assignment:
    r"""
    Align two `ProjectCommit` based on a minimum cost assignment.

    Commands in each commit are assigned to one another according to
    a `cost_function` such that the overall sum of assigned commands is
    minimized.

    Parameters
    ----------
    a, b : ProjectCommitData
        Command data extracted from two commits of a project.
    cost_function : Callable[[VernacCommandData, VernacCommandData], \
                             float]
        A non-negative function that measures the distance or
        dissimilarity between two commands.
    threshold : float
        An upper limit on the cost of assigning two commands such that
        no assignments returned by this function will meet or exceed the
        threshold.

    Returns
    -------
    Assignment
        An array of pairs of integers indicating the indices of aligned
        commands between each commit with commands enumerated over all
        matching files in `a` and `b`.
        For example, ``(0,0)`` matches the first element of the first
        file of `a` to the first element of the first file of `b`.
        Indices of elements in either `a` or `b` that were skipped in
        the alignment do not appear in the output.
    """
    # calculate cost matrix
    a_commands = a.commands
    b_commands = b.commands
    cost_matrix = np.asarray(
        [
            cost_function(a_command,
                          b_command) for _,
            a_command in a_commands for _,
            b_command in b_commands
        ]).reshape(len(a_commands),
                   len(b_commands))
    # compute assignment
    assignment = linear_sum_assignment(cost_matrix, maximize=False)
    # apply threshold
    assignment_mask = cost_matrix[assignment[0], assignment[1]] < threshold
    assignment = np.stack(
        [assignment[0][assignment_mask],
         assignment[1][assignment_mask]],
        axis=-1)
    return assignment


def _compute_diff_alignment(
        a: ProjectCommitData,
        b: ProjectCommitData,
        diff: GitDiff,
        a_indices_in_diff: Dict[str,
                                List[int]],
        b_indices_in_diff: Dict[str,
                                List[int]],
        align: AlignmentFunction) -> Assignment:
    """
    Get the alignment only between items contained in a Git diff.

    Parameters
    ----------
    a, b : ProjectCommitData
        Command data extracted from two commits of a project.
    diff : GitDiff
        A precomputed Git diff between the commits of `a` and `b` with
        `a` taken to be "before" the change.
    a_indices_in_diff : Dict[str, List[int]]
        A precomputed set of per-file command indices within `a` that
        intersect the `diff`.
    b_indices_in_diff : Dict[str, List[int]]
        A precomputed set of per-file command indices within `b` that
        intersect the `diff`.
    align : AlignmentFunction
        An alignment algorithm that will be applied to commands that
        appear in the provided `diff`.

    Returns
    -------
    Assignment
        An array of pairs of integers indicating the indices of aligned
        commands between each commit with commands enumerated over all
        commands appearing within the diff in files in `a` and `b`.
        For example, ``(0,0)`` matches the first element of the first
        file of `a` that appears in the `diff` to the first element of
        the first file of `b` that appears in the `diff`.
        Indices of elements in either `a` or `b` that were skipped in
        the alignment do not appear in the output.
    """
    # downselect commit data to changed commands
    a_in_diff = ProjectCommitData(
        a.project_metadata,
        {
            k: VernacCommandDataList([v[i] for i in a_indices_in_diff[k]])
            for k,
            v in a.command_data.items()
        },
        a.commit_message,
        a.comment_data,
        a.file_dependencies,
        a.environment,
        a.build_result)
    b_in_diff = ProjectCommitData(
        b.project_metadata,
        {
            k: VernacCommandDataList([v[i] for i in b_indices_in_diff[k]])
            for k,
            v in b.command_data.items()
        },
        b.commit_message,
        b.comment_data,
        b.file_dependencies,
        b.environment,
        b.build_result)
    # rename files in b to match those renamed in a
    rename_map: Dict[str,
                     str] = {k: k for k in b.command_data.keys()}
    for change in diff.changes:
        if change.is_rename:
            assert change.after_filename is not None
            assert change.before_filename is not None
            rename_map[str(change.after_filename)] = str(change.before_filename)
    b_in_diff.command_data = {
        rename_map[k]: v for k,
        v in b_in_diff.command_data.items()
    }
    if b_in_diff.file_dependencies is not None:
        b_in_diff.file_dependencies = {
            # file dependencies may catch files that were not built
            (rename_map[k] if k in b.command_data.keys() else k):
            ([rename_map[f] if f in b.command_data.keys() else f for f in v])
            for k,
            v in b_in_diff.file_dependencies.items()
        }
    # calculate alignment only for those items that are known to have
    # changed
    diff_alignment = align(a_in_diff, b_in_diff)
    return diff_alignment


def align_commits(
        a: ProjectCommitData,
        b: ProjectCommitData,
        diff: GitDiff,
        align: AlignmentFunction) -> Assignment:
    """
    Align two `ProjectCommit` based on the provided alignment algorithm.

    Parameters
    ----------
    a, b : ProjectCommitData
        Command data extracted from two commits of a project.
    diff : GitDiff
        A precomputed diff between the commits represented by `a` and
        `b`.
    align : AlignmentFunction
        An alignment algorithm that will be applied to commands that
        appear in the provided `diff`.

    Returns
    -------
    Assignment
        An array of pairs of integers indicating the indices of aligned
        commands between each commit with commands enumerated over all
        files in `a` and `b`.
        For example, ``(0,0)`` matches the first element of the first
        file of `a` to the first element of the first file of `b`.
        Indices of elements in either `a` or `b` that were skipped in
        the alignment do not appear in the output.

    Raises
    ------
    ValueError
        If the number of commands in `a` and `b` that do not appear in
        the `diff` do not match.
    """
    # get changed and unchanged sentence per-file indices
    a_indices_in_diff = commands_in_diff(a, diff, True)
    b_indices_in_diff = commands_in_diff(b, diff, False)
    a_files = a.files
    b_files = b.files
    a_file_sizes = {k: len(v) for k,
                    v in a.command_data.items()}
    b_file_sizes = {k: len(v) for k,
                    v in b.command_data.items()}
    a_indices_not_in_diff = {
        k: [i for i in range(a_file_sizes[k]) if not fast_contains(v,
                                                                   i)] for k,
        v in a_indices_in_diff.items()
    }
    b_indices_not_in_diff = {
        k: [i for i in range(b_file_sizes[k]) if not fast_contains(v,
                                                                   i)] for k,
        v in b_indices_in_diff.items()
    }
    # sort unchanged indices by command location
    a_indices_not_in_diff = {
        k: [
            i for _,
            i in sorted(
                zip([a.command_data[k][i] for i in v],
                    v),
                key=lambda p: p[0])
        ] for k,
        v in a_indices_not_in_diff.items()
    }
    b_indices_not_in_diff = {
        k: [
            i for _,
            i in sorted(
                zip([b.command_data[k][i] for i in v],
                    v),
                key=lambda p: p[0])
        ] for k,
        v in b_indices_not_in_diff.items()
    }
    # calculate alignment only for those items that are known to have
    # changed
    diff_alignment = _compute_diff_alignment(
        a,
        b,
        diff,
        a_indices_in_diff,
        b_indices_in_diff,
        align)
    # offset file-level indices to match final global alignment
    a_file_offsets = dict(
        zip(a_files,
            [0] + list(np.cumsum([a_file_sizes[x] for x in a_files]))))
    b_file_offsets = dict(
        zip(
            b_files,
            [0] + list(np.cumsum([len(b.command_data[x]) for x in b_files]))))
    # get final indices of changed elements of a
    changed_a_indices = np.concatenate(
        [
            np.asarray(a_indices_in_diff[filename],
                       dtype=int) + a_file_offsets[filename]
            for filename in a_files
        ],
        axis=0)
    # get final indices of changed elements of b
    changed_b_indices = np.concatenate(
        [
            np.asarray(b_indices_in_diff[filename],
                       dtype=int) + b_file_offsets[filename]
            for filename in b_files
        ],
        axis=0)
    # sort unchanged indices
    # get final indices of unchanged elements of a
    unchanged_a_indices = np.concatenate(
        [
            np.asarray(a_indices_not_in_diff[filename],
                       dtype=int) + a_file_offsets[filename]
            for filename in a_files
        ],
        axis=0)
    # get final indices of unchanged elements of b
    # get map from a filenames to b filenames
    # only need to cover files that exist in both commits
    # since indices within added or dropped files will be considered
    # "changed"
    rename_map: Dict[str, str]
    rename_map = {k: k for k in a.command_data.keys() if k in b.command_data}
    for change in diff.changes:
        if change.is_rename:
            assert change.after_filename is not None
            assert change.before_filename is not None
            rename_map[str(change.before_filename)] = str(change.after_filename)
    unchanged_b_indices = np.concatenate(
        [
            np.asarray(b_indices_not_in_diff[rename_map[filename]],
                       dtype=int) + b_file_offsets[rename_map[filename]]
            for filename in a_files
        ],
        axis=0)
    # Compute alignment
    # Unchanged indices should map one-to-one in ascending order.
    # Any dropped or added content will have been handled in
    # diff_alignment.
    if unchanged_a_indices.shape != unchanged_b_indices.shape:
        raise ValueError(
            "The number of unchanged commands do not match: "
            f"got {unchanged_b_indices.shape[0]}, "
            f"expected {unchanged_a_indices.shape[0]}. "
            "Is the diff correct?")
    no_diff_alignment: Assignment = np.stack(
        [unchanged_a_indices,
         unchanged_b_indices],
        axis=-1)
    # remap alignment of changed items to use final indices
    diff_alignment = np.stack(
        [
            changed_a_indices[diff_alignment[:,
                                             0]],
            changed_b_indices[diff_alignment[:,
                                             1]]
        ],
        axis=-1)
    alignment = np.concatenate([no_diff_alignment, diff_alignment], axis=0)
    return alignment


IndexedCommand = Tuple[int, str, VernacCommandData]
"""
A tuple containing a index, filename, and command.

The filename is the file that contains the command, and the index is the
index of the command in the total list of project commands in canonical
order.
"""

AlignedCommands = List[Union[Tuple[IndexedCommand,
                                   Optional[IndexedCommand]],
                             Tuple[Optional[IndexedCommand],
                                   IndexedCommand]]]
"""
A list of pairs of aligned commands where ``None`` in any pair indicates
that a command has no aligned partner (in other words, the command was
either added or dropped between the commits).
"""


def get_aligned_commands(
        a: ProjectCommitData,
        b: ProjectCommitData,
        alignment: Assignment) -> AlignedCommands:
    """
    Get the aligned command sequences of two commits.

    Parameters
    ----------
    a, b : ProjectCommitData
        Command data extracted from two commits of a project.
    alignment : Assignment
        A precomputed alignment between the commands of `a` and `b`.

    Returns
    -------
    AlignedCommands
        The sequence of aligned commands.

    Raises
    ------
    IndexError
        If the given `alignment` includes any indices that are out of
        bounds with respect to the given commits, i.e., if it indexes
        commands that do not exist.
    """
    if alignment.dtype != int:
        alignment = alignment.astype(int)
    aligned_commands: AlignedCommands = []
    a_commands = a.commands
    b_commands = b.commands
    if np.any(np.logical_and(alignment < 0,
                             alignment < (len(a_commands),
                                          len(b_commands)))):
        raise IndexError(
            "Alignment indices are out of bounds for the given projects. "
            f"Expected values in the ranges (0, {len(a_commands)}) and "
            f"(0, {len(b_commands)}), respectively, but got values in the ranges "
            f"({np.min(alignment[:,0])}, {np.max(alignment[:,0])}) and "
            f"({np.min(alignment[:,1])}, {np.max(alignment[:,1])})")
    # add matched commands
    aligned_commands.extend(
        ((i,
          ) + a_commands[i],
         (j,
          ) + b_commands[j]) for i,
        j in alignment)
    # add unmatched commands from first commit
    skipped_a_mask = np.ones(len(a_commands), dtype=bool)
    skipped_a_mask[alignment[:, 0]] = 0
    skipped_a_mask = np.arange(len(a_commands))[skipped_a_mask]
    aligned_commands.extend(
        ((i,
          ) + a_commands[i],
         None) for i in skipped_a_mask)
    # add unmatched commands from second commit
    skipped_b_mask = np.ones(len(b_commands), dtype=bool)
    skipped_b_mask[alignment[:, 1]] = 0
    skipped_b_mask = np.arange(len(b_commands))[skipped_b_mask]
    aligned_commands.extend(
        (None,
         (j,
          ) + b_commands[j]) for j in skipped_b_mask)
    return aligned_commands


def _file_offsets_from_aligned_commands(
        is_left: bool,
        aligned_commands: AlignedCommands) -> Dict[str,
                                                   int]:
    file_offsets: Dict[str,
                       int] = {}
    for a, b in aligned_commands:
        if is_left:
            indexed_command = a
        else:
            indexed_command = b
        if indexed_command is not None:
            idx, filename, _ = indexed_command
        else:
            continue
        try:
            offset = file_offsets[filename]
        except KeyError:
            offset = idx
        file_offsets[filename] = min(idx, offset)
    return file_offsets


left_file_offsets_from_aligned_commands = partial(
    _file_offsets_from_aligned_commands,
    True)
"""
Get offsets of files from left items in pairs of aligned commands.
"""

right_file_offsets_from_aligned_commands = partial(
    _file_offsets_from_aligned_commands,
    False)
"""
Get offsets of files from right items in pairs of aligned commands.
"""


def _aligned_commands_to_dict(
    is_left: bool,
    aligned_commands: AlignedCommands
) -> Dict[str,
          Dict[int,
               Tuple[VernacCommandData,
                     Optional[IndexedCommand]]]]:
    a_file_offsets = _file_offsets_from_aligned_commands(
        is_left,
        aligned_commands,
    )
    b_file_offsets = _file_offsets_from_aligned_commands(
        not is_left,
        aligned_commands,
    )
    result: Dict[str,
                 Dict[int,
                      Tuple[VernacCommandData,
                            Optional[IndexedCommand]]]] = {}
    for a, b in aligned_commands:
        if not is_left:
            b, a = a, b
        if a is None:
            continue
        else:
            aidx, filename, acmd = a
            if b is not None:
                bidx, bfilename, bcmd = b
                b = (bidx - b_file_offsets[bfilename], bfilename, bcmd)
            file_commands = result.setdefault(filename, dict())
            file_commands[aidx - a_file_offsets[filename]] = (acmd, b)
    return result


left_aligned_commands_to_dict = partial(_aligned_commands_to_dict, True)
"""
Map left filenames to file-local indices and aligned commands.
"""

right_aligned_commands_to_dict = partial(_aligned_commands_to_dict, False)
"""
Map right filenames to file-local indices and aligned commands.
"""


def default_align(a: ProjectCommitData, b: ProjectCommitData) -> Assignment:
    """
    Compute the default alignment algorithm.

    Performs a bipartite assignment with a normalized, thresholded edit
    distance.
    Aligned pairs whose distance matches or exceeds the threshold are
    unmatched prior to returning the result.

    See Also
    --------
    default_command_distance : A normalized, thresholded edit distance.
    """
    return assign_commits(a, b, default_command_distance, 0.4)
