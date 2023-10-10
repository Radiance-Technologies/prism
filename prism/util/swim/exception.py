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
Custom exceptions related to switch management.
"""

from typing import Tuple

from prism.util.opam.formula import PackageFormula


class UnsatisfiableConstraints(Exception):
    """
    For when a switch cannot be retrieved for given package constraints.
    """

    def __init__(self, formula: PackageFormula) -> None:
        self.unsatisfiable = formula

    def __reduce__(self) -> Tuple[type, Tuple[PackageFormula]]:  # noqa: D105
        return UnsatisfiableConstraints, (self.unsatisfiable,)

    def __str__(self) -> str:
        """
        Show the unsatisfiable constraints.
        """
        return str(self.unsatisfiable)
