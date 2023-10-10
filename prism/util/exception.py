#
# Copyright (c) 2023 Radiance Technologies, Inc.
#
# This file is part of PRISM
# (see https://github.com/orgs/Radiance-Technologies/prism).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program. If not, see
# <http://www.gnu.org/licenses/>.
#
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
