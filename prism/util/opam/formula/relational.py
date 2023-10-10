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
Defines a generic class for binary relational formulas.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Tuple, Type, Union

from .binary import Binary
from .common import FormulaT, RelOp, Value


@dataclass(frozen=True)
class Relational(Binary[FormulaT, RelOp], ABC):
    """
    A binary (comparison) relation between two formulae.
    """

    @property
    def relop(self) -> RelOp:
        """
        Get the binary relational operator.
        """
        return self.op

    def is_satisfied(
            self,
            *objects: Tuple[Any,
                            ...],
            **kwargs: Dict[str,
                           Any]) -> bool:
        """
        Reduce the relational formula to a Boolean.
        """
        ...

    def simplify(
        self,
        *objects: Tuple[Any,
                        ...],
        **kwargs: Dict[str,
                       Any]) -> Union[Value,
                                      'Relational[FormulaT]',
                                      FormulaT]:
        """
        Simplify the relational formula.
        """
        ...

    @classmethod
    @abstractmethod
    def formula_type(cls) -> Type[FormulaT]:
        """
        Get the type of relational formula.
        """
        ...
