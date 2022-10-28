"""
Tools for aligning the same proofs across commits.
"""

from typing import List

from numpy import cumsum

from prism.data.build_cache import ProjectCommitData, VernacSentence
from prism.util.alignment import fast_edit_distance, lazy_align


def normalized_string_alignment(a: str, b: str):
    """
    Find the cost of aligning two strings.

    Returns a value independent of the length of the strings, where 0.0
    is the best possible alignment (a==b) and 1.0 is the worst possible
    alignment.
    """
    cost, _ = fast_edit_distance(a, b, return_cost=True)
    return cost / max(len(a), len(b))


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
        y: normalized_string_alignment(a[x].text,
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
