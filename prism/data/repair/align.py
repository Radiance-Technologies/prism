"""
Tools for aligning the same proofs across commits.
"""

import enum
import math
from typing import Callable, List, Optional, TypeVar

from numpy import cumsum

from prism.data.build_cache import ProjectCommitData, VernacSentence
from prism.util.alignment import fast_edit_distance, lazy_align

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


def normalized_edit_distance(a: str, b: str, norm: Norm) -> float:
    """
    Find the cost of aligning two strings.

    Returns a value independent of the length of the strings, where 0.0
    is the best possible alignment (a==b) and 1.0 is the worst possible
    alignment.
    """
    return norm.apply(
        lambda a,
        b: fast_edit_distance(a,
                              b,
                              return_cost=True)[0],
        a,
        b,
        len)


def file_alignment(a: List[VernacSentence], b: List[VernacSentence]):
    """
    Align two lists of VernacSentences.

    Returns a list of tuples of optional integers.

    (1,1) matches the first element of `a`
    to the first element of `b`.

    (1,None) matches the first element of `a`
    to no element of `b`, skipping it.

    All elements of `a` and `b` are considered once,
    in order.

    Uses only the plaintext of the VernacSentences
    to do the alignment.

    WARNING: This function contains a hyperparameter,
    described below.
    """
    return lazy_align(
        range(len(a)),
        range(len(b)),
        lambda x,
        y: normalized_edit_distance(a[x].text,
                                    b[y].text),
        lambda x: 0.1)
    # the last, fixed value is a hyperparameter tradeoff
    # between skipping and mis-matching: a value of 1.0
    # always mismatches and a value of 0.0 always skips.


def align_commits(a: ProjectCommitData, b: ProjectCommitData):
    """
    Align two ProjectCommits.

    Returns a list of tuples of optional integers.

    (1,1) matches the first element of
    the first file of `a` to the first
    element of the first file of `b`.

    This function does not produces skipped
    alignment pairs-- they will simply not
    show up in the output.

    All VernacSentences of `a` and `b` are
    considered once, but not necessarily in
    order, since `a` and `b` do not
    necessarily list matching files in
    the same order!
    """
    # only attempt to align files present in both roots.
    alignable_files = a.command_data.keys() & b.command_data.keys()
    aligned_files = {}

    alignment = []

    a_indexes = [0] + list(
        cumsum([len(x) for x in a.command_data.values()])[:-1])
    b_indexes = [0] + list(
        cumsum([len(x) for x in b.command_data.values()])[:-1])

    for f in alignable_files:
        a_sentences = [x.command for x in a.command_data[f]]
        b_sentences = [x.command for x in b.command_data[f]]
        aligned_files[f] = list(
            filter(
                lambda x: x[0] is not None and x[1] is not None,
                file_alignment(a_sentences,
                               b_sentences)))
        # seek to the right part of the alignment
        left_acc = a_indexes[list(a.command_data.keys()).index(f)]
        right_acc = b_indexes[list(b.command_data.keys()).index(f)]
        if f in aligned_files:
            for (x, y) in aligned_files[f]:
                if (x is not None and y is not None):
                    alignment.append((x + left_acc, y + right_acc))

    return alignment
