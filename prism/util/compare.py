"""
Defines utilities for comparisons.
"""
from functools import total_ordering
from typing import Any, Protocol, runtime_checkable


@total_ordering
class Bottom:
    """
    A value that is less than any other.

    A generalization of negative infinity to any type.
    """

    def __eq__(self, other: Any) -> bool:  # noqa: D105
        if isinstance(other, Bottom):
            return True
        else:
            return False

    def __gt__(self, _: Any) -> bool:  # noqa: D105
        return False


@runtime_checkable
class Comparable(Protocol):
    """
    A protocol for comparable objects.

    This class can be used with `isinstance` checks and ensures
    compatibility with builtin functions based on comparisons, which
    exclusively use the less-than operator.
    """

    def __lt__(self, other: Any) -> bool:  # noqa: D105
        ...


@runtime_checkable
class Eq(Protocol):
    """
    A protocol for objects implementing equality comparisons.

    This class can be used with `isinstance` checks.
    """

    def __eq__(self, other: Any) -> bool:  # noqa: D105
        ...


@total_ordering
class Top:
    """
    A value that is greater than any other.

    A generalization of positive infinity to any type.
    """

    def __eq__(self, other: Any) -> bool:  # noqa: D105
        if isinstance(other, Top):
            return True
        else:
            return False

    def __lt__(self, _: Any) -> bool:  # noqa: D105
        return False
