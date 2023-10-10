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
Defines a generic class for negations of formulas.
"""

import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Generic, Tuple, Type, Union

from prism.util.parse import Parseable

from .common import FormulaT, Value


@dataclass(frozen=True)
class Not(Parseable, Generic[FormulaT], ABC):
    """
    A logical negation of a formula.
    """

    formula: FormulaT

    def __str__(self) -> str:  # noqa: D105
        return f"!{self.formula}"

    def is_satisfied(
            self,
            *objects: Tuple[Any,
                            ...],
            **kwargs: Dict[str,
                           Any]) -> bool:
        """
        Test whether the version does not satisfy the internal formula.
        """
        return not self.formula.is_satisfied(*objects, **kwargs)

    def simplify(self,
                 *objects: Tuple[Any,
                                 ...],
                 **kwargs: Dict[str,
                                Any]) -> Union[Value,
                                               'Not']:
        """
        Substitute the given version and variables and simplify.
        """
        formula_simplified = self.formula.simplify(*objects, **kwargs)
        if isinstance(formula_simplified, type(self).formula_type()):
            return type(self)(formula_simplified)
        elif isinstance(formula_simplified, bool):
            return not formula_simplified
        else:
            warnings.warn(f"!({formula_simplified}) is undefined")
            return None

    @classmethod
    def _chain_parse(cls, input: str, pos: int) -> Tuple['Not', int]:
        begpos = pos
        pos = cls._expect(input, pos, "!", begpos)
        pos = cls._lstrip(input, pos)
        formula, pos = cls.formula_type()._chain_parse(input, pos)
        return cls(formula), pos

    @classmethod
    @abstractmethod
    def formula_type(cls) -> Type[FormulaT]:
        """
        Get the type of logical formula.
        """
        ...
