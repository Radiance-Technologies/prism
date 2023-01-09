"""
Tools for aligning the same proofs across commits.
"""

import enum
import math
import warnings
from typing import Callable, Dict, List, Optional, Tuple, TypeVar, Union

import numpy as np
from leven import levenshtein

from prism.data.build_cache import (
    ProjectCommitData,
    VernacCommandData,
    VernacSentence,
)
from prism.data.repair.diff import commands_in_diff
from prism.util.alignment import Alignment, lazy_align
from prism.util.diff import GitDiff
from prism.util.iterable import fast_contains

T = TypeVar('T')


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


def normalized_edit_distance(a: str, b: str, norm: Norm = Norm.MAX) -> float:
    """
    Find the cost of aligning two strings.

    Returns a value independent of the length of the strings, where 0.0
    is the best possible alignment (a==b) and 1.0 is the worst possible
    alignment.
    """
    return norm.apply(levenshtein, a, b, len)


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
        b: ProjectCommitData) -> np.ndarray:
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
    np.ndarray
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
                                               b_sentences))))
        # seek to the right part of the alignment
        a_offset = a_file_offsets[f]
        b_offset = b_file_offsets[f]
        aligned_sentences += np.resize(
            np.array([a_offset,
                      b_offset]),
            aligned_sentences.shape)
        aligned_files.append(aligned_sentences)
    alignment = np.concatenate(aligned_files, axis=0)
    return alignment


def _compute_diff_alignment(
    a: ProjectCommitData,
    b: ProjectCommitData,
    diff: GitDiff,
    a_indices_in_diff: Dict[str,
                            List[int]],
    b_indices_in_diff: Dict[str,
                            List[int]],
    align: Callable[[ProjectCommitData,
                     ProjectCommitData],
                    np.ndarray]
) -> np.ndarray:
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
    align : Callable[[ProjectCommitData, ProjectCommitData], np.ndarray]
        An alignment algorithm that will be applied to commands that
        appear in the provided `diff`.

    Returns
    -------
    np.ndarray
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
            k: [v[i] for i in a_indices_in_diff[k]] for k,
            v in a.command_data.items()
        },
        a.file_dependencies,
        a.environment,
        a.build_result)
    b_in_diff = ProjectCommitData(
        b.project_metadata,
        {
            k: [v[i] for i in b_indices_in_diff[k]] for k,
            v in b.command_data.items()
        },
        b.file_dependencies,
        b.environment,
        b.build_result)
    # rename files in b to match those renamed in a
    rename_map: Dict[str,
                     str] = {k: k for k in b.command_data.keys()}
    for change in diff.changes:
        if change.is_rename:
            rename_map[change.after_filename] = change.before_filename
    b_in_diff.command_data = {
        rename_map[k]: v for k,
        v in b_in_diff.command_data.items()
    }
    if b_in_diff.file_dependencies is not None:
        b_in_diff.file_dependencies = {
            rename_map[k]: [rename_map[f] for f in v] for k,
            v in b_in_diff.file_dependencies.items()
        }
    assert b_in_diff.files == [rename_map[f] for f in b.files]
    # calculate alignment only for those items that are known to have
    # changed
    diff_alignment = align(a_in_diff, b_in_diff)
    return diff_alignment


def align_commits(
    a: ProjectCommitData,
    b: ProjectCommitData,
    diff: GitDiff,
    align: Callable[[ProjectCommitData,
                     ProjectCommitData],
                    np.ndarray]
) -> np.ndarray:
    """
    Align two `ProjectCommit` based on the provided alignment algorithm.

    Parameters
    ----------
    a, b : ProjectCommitData
        Command data extracted from two commits of a project.
    diff : GitDiff
        A precomputed diff between the commits represented by `a` and
        `b`.
    align : Callable[[ProjectCommitData, ProjectCommitData], np.ndarray]
        An alignment algorithm that will be applied to commands that
        appear in the provided `diff`.

    Returns
    -------
    np.ndarray
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
            np.asarray(v) + a_file_offsets[k] for k,
            v in a_indices_in_diff.items()
        ],
        axis=0)
    # get final indices of changed elements of b
    changed_b_indices = np.concatenate(
        [
            np.asarray(v) + b_file_offsets[k] for k,
            v in b_indices_in_diff.items()
        ],
        axis=0)
    # get final indices of unchanged elements of a
    unchanged_a_indices = np.concatenate(
        [
            np.asarray(v) + a_file_offsets[k] for k,
            v in a_indices_not_in_diff.items()
        ],
        axis=0)
    # get final indices of unchanged elements of b
    unchanged_b_indices = np.concatenate(
        [
            np.asarray(v) + b_file_offsets[k] for k,
            v in b_indices_not_in_diff.items()
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
    no_diff_alignment: np.ndarray = np.stack(
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


AlignedCommands = List[Union[Tuple[Tuple[str,
                                         VernacCommandData],
                                   Optional[Tuple[str,
                                                  VernacCommandData]]],
                             Tuple[Optional[Tuple[str,
                                                  VernacCommandData]],
                                   Tuple[str,
                                         VernacCommandData]]]]
"""
A list of pairs of aligned commands where ``None`` in any pair indicates
that a command has no aligned partner (in other words, the command was
either added or dropped between the commits).
"""


def get_aligned_commands(
        a: ProjectCommitData,
        b: ProjectCommitData,
        alignment: np.ndarray) -> AlignedCommands:
    """
    Get the aligned command sequences of two commits.

    Parameters
    ----------
    a, b : ProjectCommitData
        Command data extracted from two commits of a project.
    alignment : np.ndarray
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
    aligned_commands: AlignedCommands = []
    a_commands = a.commands
    b_commands = b.commands
    if np.any(alignment < 0 & alignment < (len(a_commands), len(b_commands))):
        raise IndexError(
            "Alignment indices are out of bounds for the given projects. "
            f"Expected values in the ranges (0, {len(a_commands)}) and "
            f"(0, {len(b_commands)}), respectively, but got values in the ranges "
            f"({np.min(alignment[:,0])}, {np.max(alignment[:,0])}) and "
            f"({np.min(alignment[:,1])}, {np.max(alignment[:,1])})")
    align_idx = 0
    j = 0
    for i, acmd in enumerate(a_commands):
        while j < alignment[align_idx, 1]:
            aligned_commands.append((None, b_commands[j]))
            j += 1
        if i < alignment[align_idx, 0]:
            aligned_commands.append((acmd, None))
        else:
            assert (i, j) == tuple(aligned_commands[align_idx])
            aligned_commands.append((acmd, b_commands[j]))
    return aligned_commands
