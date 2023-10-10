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
