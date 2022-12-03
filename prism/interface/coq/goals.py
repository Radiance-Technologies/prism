"""
Abstractions of Coq goals and hypotheses.
"""
import enum
from dataclasses import dataclass
from itertools import chain
from typing import Dict, List, Optional, Set, Tuple, Union

from prism.util.radpytools.dataclasses import default_field


@dataclass
class Hypothesis:
    """
    An hypothesis.

    Notes
    -----
    This class loosely corresponds to the ``hyp`` type defined in
    ``coq-serapi/serapi/serapi_goals.mli``.
    """

    idents: List[str]
    """
    Identifiers within the hypothesis.
    """
    term: Optional[str]
    """
    The value assigned to each identifier, if any.
    """
    # QUESTION (AG): Is there a one-to-one mapping between terms and
    # identifiers? I'm not sure how there can be multiple of these since
    # the field arises from an `option` in serapi_goals.mli.
    type: str
    """
    The type of each identifier.
    """
    sexp: str
    """
    The serialization of the identifier's Coq kernel type.
    """

    def __hash__(self) -> int:  # noqa: D105
        return hash((tuple(self.idents), self.term, self.type))

    def __str__(self) -> str:
        """
        Pretty-print the hypothesis similar to its form in CoqIDE.
        """
        value = f':= {self.term}' if self.term is not None else ""
        return f"{','.join(self.idents)} {value} : {self.type}"


@dataclass
class Goal:
    """
    A goal of a proof.

    Notes
    -----
    This class loosely corresponds to the ``reified_goal`` type defined
    in ``coq-serapi/serapi/serapi_goals.mli``.
    """

    id: int
    """
    A unique identifier of the goal.
    """
    type: str
    """
    The type of the goal.

    In essence, a statement of the goal itself.
    """
    sexp: str
    """
    The serialization of the goal's Coq kernel type.
    """
    hypotheses: List[Hypothesis]
    """
    A list of hypotheses pertaining to this goal.
    """

    def __hash__(self) -> int:  # noqa: D105
        return hash((self.id, self.type, tuple(self.hypotheses)))

    def __str__(self) -> str:
        """
        Pretty-print the goal similar to its form in CoqIDE.
        """
        hypotheses = '\n'.join([str(h) for h in self.hypotheses])
        return '\n'.join(
            [hypotheses,
             '______________________________________',
             self.type])


class GoalType(enum.Enum):
    """
    Enumerate the types of goals one may encounter.
    """

    FOREGROUND = enum.auto()
    BACKGROUND = enum.auto()
    SHELVED = enum.auto()
    ABANDONED = enum.auto()


GoalIndex = Tuple[int, int, bool]
"""
The index of a goal in a `Goals` field.

For all fields except `background_goals`, the first and last element of
an index are ``0`` and ``True``, respectively.
Otherwise, these indices give the depth in the background goals stack
and whether it is in the left or right list at the given depth.
The middle index gives the index of a goal in an actual list of goals.
"""


@dataclass
class Goals:
    """
    The collection of unfinished goals within the current context.

    Notes
    -----
    This class loosely corresponds to the ``ser_goals`` type defined in
    ``coq-serapi/serapi/serapi_goals.mli``.
    """

    foreground_goals: List[Goal] = default_field([])
    # TODO (AG): Figure out the meaning of the left versus right goals.
    background_goals: List[Tuple[List[Goal], List[Goal]]] = default_field([])
    shelved_goals: List[Goal] = default_field([])
    abandoned_goals: List[Goal] = default_field([])

    @property
    def is_empty(self) -> bool:
        """
        Return True if there are no goals, False otherwise.
        """
        return not (
            self.foreground_goals or self.background_goals or self.shelved_goals
            or self.abandoned_goals)

    def get(
        self,
        goal_type: GoalType,
        idx: Optional[int] = None,
        depth: int = 0,
        is_left: bool = True,
    ) -> Union[Goal,
               List[Goal]]:
        """
        Get a goal or goals of a desired type out of the structure.

        Parameters
        ----------
        goal_type : GoalType
            The type of desired goal or goals.
        idx : Optional[int], optional
            The index of a goal in its respective type's list, by
            default None.
            If None, then all goals of the requested type, depth, and
            parity are returned.
        depth : int, optional
            The depth of a background goal, by default 0.
            Ignored if `goal_type` is not `GoalType.BACKGROUND`.
        is_left : bool, optional
            The parity of a background goal, by default True.
            Ignored if `goal_type` is not `GoalType.BACKGROUND`.

        Returns
        -------
        Union[Goal, List[Goal]]
            The requested goal or goals.
        """
        if goal_type == GoalType.FOREGROUND:
            goals = self.foreground_goals
        elif goal_type == GoalType.BACKGROUND:
            (left_goal_stack, right_goal_stack) = self.background_goals[depth]
            if is_left:
                goals = left_goal_stack
            else:
                goals = right_goal_stack
        elif goal_type == GoalType.SHELVED:
            goals = self.shelved_goals
        else:
            assert goal_type == GoalType.ABANDONED
            goals = self.abandoned_goals
        if idx is not None:
            return goals[idx]
        else:
            return goals

    def goal_index_map(self) -> Dict[Goal, Set[Tuple[GoalType, GoalIndex]]]:
        """
        Map these goals to their type and index.

        Returns
        -------
        Dict[Goal, Set[Tuple[GoalType, GoalIndex]]]
            A map from each goal to its `GoalType` and index within the
            `Goals` structure.
            The possibility of the same goal appearing in multiple
            indices is supported but not expected to occur in practice.
        """
        result = {}
        for (goal_type,
             egs) in ((GoalType.FOREGROUND,
                       [(0,
                         (self.foreground_goals,
                          []))]),
                      (GoalType.BACKGROUND,
                       enumerate(self.background_goals)),
                      (GoalType.SHELVED,
                       [(0,
                         (self.shelved_goals,
                          []))]),
                      (GoalType.ABANDONED,
                       [(0,
                         (self.abandoned_goals,
                          []))])):
            for gs_idx, (lgs, rgs) in egs:
                for g_idx, g in enumerate(lgs):
                    locations = result.setdefault(g, set())
                    locations.add((goal_type, (gs_idx, g_idx, True)))
                for g_idx, g in enumerate(rgs):
                    locations = result.setdefault(g, set())
                    locations.add((goal_type, (gs_idx, g_idx, False)))
        return result

    def insert(
            self,
            goal: Goal,
            goal_type: GoalType,
            goal_index: GoalIndex) -> None:
        """
        Add a new goal to the structure at a given index.

        Parameters
        ----------
        goal : Goal
            A goal.
        goal_type : GoalType
            The type of the goal.
        goal_index : GoalIndex
            The index at which the goal should be inserted.
        """
        (depth, idx, is_left) = goal_index
        try:
            goals = self.get(goal_type, depth=depth, is_left=is_left)
        except IndexError:
            # extend depth
            left_goal_stack = []
            right_goal_stack = []
            self.background_goals.append((left_goal_stack, right_goal_stack))
            if is_left:
                goals = left_goal_stack
            else:
                goals = right_goal_stack
        goals.insert(idx, goal)

    def pop(self, goal_type: GoalType, goal_index: GoalIndex) -> Goal:
        """
        Remove and return a goal from the structure.

        Parameters
        ----------
        goal_type : GoalType
            The type of the goal.
        goal_index : GoalIndex
            The index at which the goal should be inserted.

        Returns
        -------
        Goal
            The removed goal.
        """
        (depth, idx, is_left) = goal_index
        goals = self.get(goal_type, depth=depth, is_left=is_left)
        popped_goal = goals.pop(idx)
        if goal_type == GoalType.BACKGROUND:
            (left_goal_stack, right_goal_stack) = self.background_goals[depth]
            if not left_goal_stack and not right_goal_stack:
                self.background_goals.pop(depth)
        return popped_goal

    def shallow_copy(self) -> 'Goals':
        """
        Get a shallow copy of this structure and its fields.
        """
        return Goals(
            list(self.foreground_goals),
            [
                (list(left),
                 list(right)) for left,
                right in self.background_goals
            ],
            list(self.shelved_goals),
            list(self.abandoned_goals))


# second Tuple is actually variadic but skipped to avoid triggering
# bug in seutil.io.deserialize
AddedGoal = Tuple[Goal, Tuple[Tuple[GoalType, GoalIndex]]]
RemovedGoal = Tuple[GoalType, GoalIndex]
MovedGoal = Tuple[Tuple[GoalType, GoalIndex], Tuple[GoalType, GoalIndex]]


@dataclass
class GoalsDiff:
    """
    A compact diff between two `Goals` data structures.
    """

    added_goals: Set[AddedGoal] = default_field(set())
    removed_goals: Set[RemovedGoal] = default_field(set())
    moved_goals: Set[MovedGoal] = default_field(set())

    @property
    def is_empty(self) -> bool:
        """
        Return True if the diff contains no changes, False otherwise.
        """
        return not (self.added_goals or self.removed_goals or self.moved_goals)

    def patch(self, before: Goals) -> Goals:
        """
        Apply this diff to some initial goals.

        Parameters
        ----------
        before : Goals
            A set of goals, presumed to be the initial goals used to
            compute this diff.

        Returns
        -------
        after : Goals
            The changed goals after the diff has been applied.
        """
        # make shallow copy to allow in-place modifications
        after = before.shallow_copy()
        # decompose moves into removals and additions
        # (with removals as moves with None added)
        # apply moves/removes in descending order according to index
        sorted_removals = sorted(
            chain(((rg,
                    None) for rg in self.removed_goals),
                  self.moved_goals),
            key=lambda k: k[0][1],
            reverse=True)
        added_goals: List[Tuple[Goal, GoalType, GoalIndex]] = []
        for ((removed_goal_type,
              removed_goal_index),
             added_goal_location) in sorted_removals:
            removed_goal = after.pop(removed_goal_type, removed_goal_index)
            if added_goal_location is not None:
                added_goals.append((removed_goal, *added_goal_location))
        # then apply all additions in ascending order
        for goal, locations in self.added_goals:
            for goal_type, goal_index in locations:
                added_goals.append((goal, goal_type, goal_index))
        sorted_additions = sorted(added_goals, key=lambda k: k[2])
        for (goal, goal_type, goal_index) in sorted_additions:
            after.insert(goal, goal_type, goal_index)
        return after

    @classmethod
    def compute_diff(cls, before: Goals, after: Goals) -> 'GoalsDiff':
        """
        Compute the diff between two goals structures.

        Parameters
        ----------
        before : Goals
            The goals before a hypothetical change.
        after : Goals
            The goals after a hypothetical change.

        Returns
        -------
        GoalsDiff
            The diff that, when applied to the `before` goals yields the
            `after` goals.
        """
        diff = GoalsDiff()
        after_map = after.goal_index_map()
        for bg, bg_index in before.goal_index_map().items():
            try:
                ag_index = after_map.pop(bg)
            except KeyError:
                diff.removed_goals.update(bg_index)
            else:
                # naive alignment
                for bidx in bg_index:
                    try:
                        aidx = ag_index.pop()
                    except KeyError:
                        diff.removed_goals.add(bidx)
                    else:
                        diff.moved_goals.add((bidx, aidx))
        # anything not popped must have been added
        for ag, ag_index in after_map.items():
            diff.added_goals.add((ag, tuple(ag_index)))
        return diff
