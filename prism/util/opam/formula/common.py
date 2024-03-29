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
Provides utilities for working with OCaml package constraints.
"""

import enum
import re
from typing import (
    Any,
    Dict,
    Mapping,
    Optional,
    Protocol,
    Tuple,
    TypeVar,
    Union,
    runtime_checkable,
)

from prism.util.abc_enum import ABCEnumMeta
from prism.util.parse import Parseable, ParseError

# See https://opam.ocaml.org/doc/Manual.html#General-syntax
_letter_syntax: re.Pattern = re.compile("[a-zA-Z]")
_digit_syntax: re.Pattern = re.compile("[0-9]")
_int_syntax: re.Pattern = re.compile(rf"\-?{_digit_syntax.pattern}+")
_bool_syntax: re.Pattern = re.compile("true|false")
_string_syntax: re.Pattern = re.compile(r'"([^\s"]+)"|"""(\S*)"""')
_empty_string_syntax: re.Pattern = re.compile('""')
_identchar_syntax: re.Pattern = re.compile(
    rf"(?:{_letter_syntax.pattern}|{_digit_syntax.pattern}|\-|_|\+)")
_ident_syntax: re.Pattern = re.compile(
    f"{_identchar_syntax.pattern}*[a-zA-Z]{_identchar_syntax.pattern}*")
_varident_syntax: re.Pattern = re.compile(
    ''.join(
        [
            "(?:",
            f"(?:{_ident_syntax.pattern}|_)",
            r"(?:\+",
            f"(?:{_ident_syntax.pattern}|_))*:",
            f")?{_ident_syntax.pattern}"
        ]))


class LogOp(Parseable, enum.Enum, metaclass=ABCEnumMeta):
    """
    A logical binary relation (namely conjunction and disjunction).
    """

    AND = enum.auto()
    OR = enum.auto()

    def __call__(self, left: Any, right: Any) -> bool:
        """
        Apply the operator.
        """
        return self.evaluate(left, right)

    def __str__(self) -> str:  # noqa: D105
        if self == LogOp.AND:
            result = "&"
        elif self == LogOp.OR:
            result = "|"
        return result

    def evaluate(self, left: Any, right: Any) -> bool:
        """
        Evaluate the arguments according to this logical operator.
        """
        if self == LogOp.AND:
            result = left and right
        elif self == LogOp.OR:
            result = left or right
        return result

    @classmethod
    def _chain_parse(cls, input: str, pos: int) -> Tuple['LogOp', int]:
        try:
            result = cls(input[pos])
        except (ValueError, IndexError) as e:
            raise ParseError(cls, input[pos :]) from e
        pos = cls._lstrip(input, pos + 1)
        return result, pos

    @classmethod
    def _missing_(cls, value: Any) -> 'LogOp':
        result = None
        if isinstance(value, str):
            if value == "&":
                result = LogOp.AND
            elif value == "|":
                result = LogOp.OR
        if result is None:
            result = super()._missing_(value)
        return result


class RelOp(Parseable, enum.Enum, metaclass=ABCEnumMeta):
    """
    A comparison-based binary relation operator.
    """

    EQ = enum.auto()
    NEQ = enum.auto()
    LT = enum.auto()
    LEQ = enum.auto()
    GT = enum.auto()
    GEQ = enum.auto()

    def __call__(self, left: Any, right: Any) -> bool:
        """
        Apply the operator.
        """
        return self.evaluate(left, right)

    def __str__(self) -> str:  # noqa: D105
        if self == RelOp.EQ:
            result = "="
        elif self == RelOp.NEQ:
            result = "!="
        elif self == RelOp.LT:
            result = "<"
        elif self == RelOp.LEQ:
            result = "<="
        elif self == RelOp.GT:
            result = ">"
        elif self == RelOp.GEQ:
            result = ">="
        return result

    def evaluate(self, left: Any, right: Any) -> bool:
        """
        Evaluate the arguments according to this relational operator.
        """
        if self == RelOp.EQ:
            result = left == right
        elif self == RelOp.NEQ:
            result = left != right
        elif self == RelOp.LT:
            result = left < right
        elif self == RelOp.LEQ:
            result = left <= right
        elif self == RelOp.GT:
            result = left > right
        elif self == RelOp.GEQ:
            result = left >= right
        return result

    @classmethod
    def _chain_parse(cls, input: str, pos: int) -> Tuple['RelOp', int]:
        op = input[pos : pos + 2]
        if len(op) == 2 and op[1] != "=":
            op = op[0]
        try:
            result = cls(op)
        except ValueError as e:
            raise ParseError(cls, input[pos :]) from e
        pos = cls._lstrip(input, pos + len(op))
        return result, pos

    @classmethod
    def _missing_(cls, value: Any) -> 'RelOp':
        result = None
        if isinstance(value, str):
            if value == "=":
                result = RelOp.EQ
            elif value == "!=":
                result = RelOp.NEQ
            elif value == "<":
                result = RelOp.LT
            elif value == "<=":
                result = RelOp.LEQ
            elif value == ">":
                result = RelOp.GT
            elif value == ">=":
                result = RelOp.GEQ
        if result is None:
            result = super()._missing_(value)
        return result


Value = Optional[Union[bool, str]]
"""
The result of reducing a filter.
"""


@runtime_checkable
class Formula(Protocol):
    """
    A protocol for satisfiable Boolean formulas.
    """

    def is_satisfied(
            self,
            *objects: Tuple[Any,
                            ...],
            **kwargs: Dict[str,
                           Any]) -> bool:
        """
        Test whether the objects satisfy the constraints of the formula.

        Returns
        -------
        bool
            True if the formula is satisfied (i.e., it simplifies to a
            True value after substituting the given objects), False
            otherwise.
        """
        ...

    def simplify(self,
                 *objects: Tuple[Any,
                                 ...],
                 **kwargs: Dict[str,
                                Any]) -> Union[Value,
                                               'Formula']:
        """
        Substitute the given objects into the formula and simplify it.

        Returns
        -------
        Union[bool, Formula]
            The simplified formula.
        """
        ...


class Variable(str):
    """
    A variable.
    """

    pass


AssignedVariables = Mapping[str, Union[bool, int, str]]

FormulaT = TypeVar('FormulaT', 'Formula', Parseable)


def value_to_bool(v: Value) -> bool:
    """
    Cast a `Value` to a Boolean.

    Notes
    -----
    Based on ``opam/src/format/opamFilter.ml:value_bool`` with a default
    of False.
    """
    if v is None:
        return False
    elif isinstance(v, str):
        if v == "true":
            return True
        else:
            return False
    else:
        return v


def value_to_string(v: Value) -> str:
    """
    Cast a `Value` to a string (e.g., for version-order comparisons).

    Notes
    -----
    Based on ``opam/src/format/opamFilter.ml:value_string`` with a
    default of the empty string.
    """
    if v is None:
        return ""
    elif isinstance(v, bool):
        if v:
            return "true"
        else:
            return "false"
    else:
        return v
