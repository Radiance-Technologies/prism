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
