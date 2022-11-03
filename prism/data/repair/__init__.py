"""
Stubs for picking repair implementations.
"""

from prism.data.build_cache import ProjectCommitData

from .align import align_commits as dyn_align_commits


def align_commits(
        a: ProjectCommitData,
        b: ProjectCommitData,
        aligner=dyn_align_commits):
    """
    Aligns two ProjectCommitDatas textually.

    This is a stub that chooses the actual underlying implementation.
    """
    return aligner(a, b)
