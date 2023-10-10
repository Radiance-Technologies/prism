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
