"""
Provides general-purpose exception utilities.
"""

import copy
from dataclasses import dataclass
from typing import Generic, NoReturn, Optional, TypeVar

T = TypeVar('T')


@dataclass
class Except(Generic[T]):
    """
    A (return) value paired with an exception for delayed handling.
    """

    value: Optional[T]
    """
    A return value preempted by an exception.

    If None, then the exception was likely raised before any return
    value was computed.
    If not None, then the value may or may not be complete.
    """
    exception: Exception
    """
    An exception raised during the computation of `value`.
    """
    trace: str
    """
    The stack trace of the exception.
    """

    def __post_init__(self):
        """
        Copy the exception object, deleting the traceback.
        """
        self.exception = copy.copy(self.exception)


def raise_(exc: Exception) -> NoReturn:
    """
    Raise the given exception.

    Useful for raising exceptions in lambda functions.
    """
    raise exc
