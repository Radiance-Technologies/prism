"""
Object copying protocols and utilities.
"""

from typing import Protocol, TypeVar, runtime_checkable

_T = TypeVar('_T', bound='ShallowCopy')


@runtime_checkable
class ShallowCopy(Protocol):
    """
    A protocol for customized shallow copies.
    """

    def shallow_copy(self: _T) -> _T:
        """
        Get a shallow copy of this structure and its fields.

        The exact depth of the copy depends on the implementation.
        """
        ...
