"""
Defines classes for parsing and expressing version constraint filters.
"""

import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Tuple, Type, Union

from prism.util.opam.formula.negate import Not
from prism.util.opam.formula.relational import Relational
from prism.util.opam.version import Version
from prism.util.parse import Parseable, ParseError

from .common import (
    AssignedVariables,
    Value,
    Variable,
    _bool_syntax,
    _int_syntax,
    _string_syntax,
    _varident_syntax,
    value_to_bool,
    value_to_string,
)
from .logical import Logical
from .parens import Parens


@dataclass(frozen=True)
class Filter(Parseable, ABC):
    """
    A parameterized formula expressing constraints on a package version.

    See https://opam.ocaml.org/doc/Manual.html#Filters for more
    information.
    """

    def __contains__(  # noqa: D105
        self,
        version: Union[Version,
                       Tuple[Version,
                             AssignedVariables]]
    ) -> bool:
        if isinstance(version, tuple):
            variables = version[1]
            version = version[0]
        else:
            variables = None
        return self.is_satisfied(version, variables)

    @property
    @abstractmethod
    def variables(self) -> List[str]:
        """
        Get a list of the variable names that appear in this formula.
        """
        ...

    @abstractmethod
    def evaluate(self, variables: Optional[AssignedVariables] = None) -> Value:
        """
        Evaluate the filter with the given variables.

        The filter may evaluate to a Boolean, a string, or an undefined
        (None) value.
        """
        ...

    def is_satisfied(
            self,
            variables: Optional[AssignedVariables] = None) -> bool:
        """
        Return whether the given version/variables satisfy this formula.
        """
        return value_to_bool(self.evaluate(self, variables))

    @abstractmethod
    def simplify(
        self,
        variables: Optional[AssignedVariables] = None) -> Union[Value,
                                                                'Filter']:
        """
        Evaluate the filter but keep undefined variables intact.
        """
        ...

    @classmethod
    def _chain_parse(cls, input: str, pos: int) -> Tuple['Filter', int]:
        raise NotImplementedError()


@dataclass(frozen=True)
class LogicalF(Logical[Filter], Filter):
    """
    A logical combination of two filters.
    """

    @property
    def variables(self) -> List[str]:  # noqa: D102
        variables = []
        variables.extend(self.left.variables)
        variables.extend(self.right.variables)
        return variables

    @classmethod
    def formula_type(cls) -> Type[Filter]:  # noqa: D102
        return Filter


@dataclass(frozen=True)
class NotF(Not[Filter], Filter):
    """
    A logical negation of a filter.
    """

    @property
    def variables(self) -> List[str]:  # noqa: D102
        return self.formula.variables

    def evaluate(  # noqa: D102
            self,
            variables: Optional[AssignedVariables] = None
    ) -> Value:
        # imitate behavior of opam/src/format/opamFilter.ml:logop1
        evaluated = self.formula.evaluate(variables)
        if evaluated is None:
            return None
        elif isinstance(evaluated, bool):
            return not evaluated
        else:
            warnings.warn(f"!({evaluated}) is undefined")
            return None

    @classmethod
    def formula_type(cls) -> Type[Filter]:  # noqa: D102
        return Filter


@dataclass(frozen=True)
class ParensF(Parens[Filter], Filter):
    """
    A parenthetical around a package formula.
    """

    @property
    def variables(self) -> List[str]:  # noqa: D102
        return self.formula.variables

    @classmethod
    def formula_type(cls) -> Type[Filter]:  # noqa: D102
        return Filter


@dataclass(frozen=True)
class RelationalF(Relational[Filter], Filter):
    """
    A binary relation between two filters.
    """

    @property
    def variables(self) -> List[str]:  # noqa: D102
        variables = []
        variables.extend(self.left.variables)
        variables.extend(self.right.variables)
        return variables

    def evaluate(  # noqa: D102
            self,
            variables: Optional[AssignedVariables] = None
    ) -> Value:
        left = self.left.evaluate(variables)
        right = self.right.evaluate(variables)
        if left is None or right is None:
            result = None
        else:
            left = Version.parse(
                value_to_string(left),
                check_syntax=False,
                require_quotes=False)
            right = Version.parse(
                value_to_string(right),
                check_syntax=False,
                require_quotes=False)
            result = self.relop(left, right)
        return result

    def simplify(  # noqa: D102
        self,
        variables: Optional[AssignedVariables] = None
    ) -> Union[Value,
               'RelationalF']:
        left = self.left.simplify(variables)
        right = self.right.simplify(variables)
        if left is None or right is None:
            result = None
        elif isinstance(left, Filter):
            if not isinstance(right, Filter):
                right = FilterAtom(right)
            result = type(self)(left, self.relop, right)
        elif isinstance(right, Filter):
            left = FilterAtom(left)
            result = type(self)(left, self.relop, right)
        else:
            left = Version.parse(
                value_to_string(left),
                check_syntax=False,
                require_quotes=False)
            right = Version.parse(
                value_to_string(right),
                check_syntax=False,
                require_quotes=False)
            result = self.relop(left, right)
        return result

    @classmethod
    def formula_type(cls) -> Type[Filter]:  # noqa: D102
        return Filter


@dataclass(frozen=True)
class FilterAtom(Filter):
    """
    An atom (terminal) in a filter formula.
    """

    term: Union[Variable, str, int, bool]

    def __str__(self) -> str:
        """
        Print the atom.
        """
        return str(self.term)

    @property
    def variables(self) -> List[str]:  # noqa: D102
        if isinstance(self.term, Variable):
            return [self.term]
        else:
            return []

    def evaluate(  # noqa: D102
            self,
            variables: Optional[AssignedVariables] = None
    ) -> Value:
        simplified = self.simplify(variables)
        if isinstance(simplified, FilterAtom):
            return None
        else:
            return simplified

    def simplify(  # noqa: D102
        self,
        variables: Optional[AssignedVariables] = None) -> Union[Value,
                                                                'FilterAtom']:
        if isinstance(self.term, Variable):
            if variables is None:
                return self
            try:
                value = variables[self.term]
            except KeyError:
                return self
            else:
                if isinstance(value, bool):
                    return value
                else:
                    return str(value)
        elif isinstance(self.term, bool):
            return self.term
        else:
            return str(self.term)

    @classmethod
    def _chain_parse(cls, input: str, pos: int) -> Tuple['FilterAtom', int]:
        term = input[pos :]
        match = _bool_syntax.match(term)
        for (regex,
             p) in [(_bool_syntax,
                     bool),
                    (_int_syntax,
                     int),
                    (_string_syntax,
                     str),
                    (_varident_syntax,
                     Variable)]:
            match = regex.match(term)
            if match is not None:
                parser = p
        if match is None:
            raise ParseError(FilterAtom, term)
        else:
            term = parser(term[: match.end()])
            pos += match.end()
        pos = cls._lstrip(input, pos)
        return cls(term), pos
