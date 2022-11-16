"""
Complementary module to `prism.util.compare`.
"""
from typing import TypeVar

T = TypeVar('T')


def identity(x: T) -> T:
    """
    Perform the identity function; return the input unchanged.

    Equivalent to ``lambda x: x``.
    """
    return x


class Identity:
    """
    Objects that always test True for equality.
    """

    def __eq__(self, __o: object) -> bool:  # noqa: D105
        return True

    def __str__(self) -> str:
        """
        Present as an asterisk, akin to a pattern that matches anything.
        """
        return '*'
