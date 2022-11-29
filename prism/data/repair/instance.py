"""
Defines representations of repair instances (or examples).
"""

from dataclasses import dataclass
from typing import Optional, Set

from prism.language.gallina.analyze import SexpInfo
from prism.util.diff import GitDiff
from prism.util.opam import OpamSwitch
from prism.util.radpytools.dataclasses import default_field


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
class ErrorInstance:
    """
    A concise example of an error in its most raw and unprocessed form.
    """

    project_name: str
    """
    An identifier that uniquely determines the project and is implicitly
    linked to a Git repository through some external correspondence.
    """
    initial_state: ProjectRepoState
    """
    An initial project state.

    An example of the project, nominally taken to be prior to a change
    that introduced a broken proof or other bug.
    """
    change: GitDiff
    """
    A refactor or other change that introduces an error when applied to
    the initial state.

    If the diff is empty, then `initial_state` is understood to be
    broken.
    """
    error_location: Set[SexpInfo.Loc] = default_field(set())
    """
    A precise location for the error(s).

    This field allows one to avoid needing to attempt compilation of the
    project to identify the error(s).
    In addition, it allows an `ErrorInstance` to focus on a subset of
    errors in the event that the `change` induces multiple independent
    errors.
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
    """

    error: ErrorInstance
    """
    An erroneous project state.
    """
    repaired_state: ProjectRepoState
    """
    A repaired proof state.

    An example of the project after an error induced by the change has
    been fixed.
    """
