"""
Tools for aligning the same proofs across commits.
"""

import enum
import math
from typing import Callable, List, Optional, Tuple, TypeVar

from leven import levenshtein
from numpy import cumsum

from prism.data.build_cache import ProjectCommitData, VernacSentence
from prism.util.alignment import Alignment, lazy_align

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
        For example, ``(1,1)`` matches the first element of `a` to the
        first element of `b`.
        Alternatively, ``(1,None)`` matches the first element of `a` to
        no element of `b`, skipping it.
    """
    return lazy_align(
        range(len(a)),
        range(len(b)),
        lambda x,
        y: normalized_edit_distance(a[x].text,
                                    b[y].text),
        lambda _: alpha)


def align_commits_per_file(a: ProjectCommitData,
                           b: ProjectCommitData) -> List[Tuple[int,
                                                               int]]:
    """
    Align two `ProjectCommit` based on matching files.

    Aligns sentences in files pairwise based on file names.
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
    List[Tuple[int, int]]
        A list of pairs of integers indicating the indices of aligned
        sentences between each commit with sentences enumerated over all
        matching files in `a` and `b` in the order dictated by `a`.
        For example, ``(1,1)`` matches the first element of the first
        file of `a` to the first element of the matching file of `b`.
        This function does not produce skipped alignment pairs--they
        will simply not show up in the output.

    Raises
    ------
    ValueError
        If `a` and `b` belong to different projects.
    """
    if a.project_metadata.project_name != b.project_metadata.project_name:
        raise ValueError(
            "Cannot align files from different projects: "
            f"{a.project_metadata.project_name} and {b.project_metadata.project_name}"
        )

    # only attempt to align files present in both roots.
    alignable_files = a.command_data.keys() & b.command_data.keys()
    aligned_files = {}

    alignment = []

    a_indexes = [0] + list(
        cumsum([len(x) for x in a.command_data.values()])[:-1])
    b_indexes = [0] + list(
        cumsum([len(x) for x in b.command_data.values()])[:-1])

    for f in a.files:
        if f not in alignable_files:
            continue
        a_sentences = [x.command for x in a.command_data[f]]
        b_sentences = [x.command for x in b.command_data[f]]
        aligned_files[f] = list(
            filter(
                lambda x: x[0] is not None and x[1] is not None,
                order_preserving_alignment(a_sentences,
                                           b_sentences)))
        # seek to the right part of the alignment
        left_acc = a_indexes[list(a.command_data.keys()).index(f)]
        right_acc = b_indexes[list(b.command_data.keys()).index(f)]
        if f in aligned_files:
            for (x, y) in aligned_files[f]:
                if (x is not None and y is not None):
                    alignment.append((x + left_acc, y + right_acc))

    return alignment
