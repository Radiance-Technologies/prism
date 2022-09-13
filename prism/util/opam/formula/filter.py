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
    LogOp,
    RelOp,
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

        Notes
        -----
        This function roughly corresponds to
        ``opam/src/format/opamFilter.ml:eval``.
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
        begpos = pos
        try:
            formula, pos = FilterAtom._chain_parse(input, pos)
        except ParseError:
            try:
                formula, pos = ParensF._chain_parse(input, pos)
            except ParseError:
                try:
                    formula, pos = NotF._chain_parse(input, pos)
                except ParseError:
                    formula, pos = IsDefined._chain_parse(input, pos)
        # attempt some left recursion
        # lookback to check that the previous term is not a negation
        # or definition check
        prev = cls._lookback(input, begpos, 1)[0]
        if prev != "!" and prev != "?":
            try:
                formula, pos = cls._lookahead_parse(begpos, formula, input, pos)
            except ParseError:
                pass
        return formula, pos

    @classmethod
    def _lookahead_parse(
            cls,
            begpos: int,
            left: 'Filter',
            input: str,
            pos: int) -> Tuple['Filter',
                               int]:
        """
        Parse a binary relation by speculatively looking ahead.
        """
        try:
            op, pos = LogOp._chain_parse(input, pos)
        except ParseError:
            try:
                op, pos = RelOp._chain_parse(input, pos)
            except ParseError:
                formula = left
                op = None
                Binary = None
            else:
                Binary = RelationalF
        else:
            Binary = LogicalF
        if op is not None:
            assert Binary is not None
            try:
                right, pos = Filter._chain_parse(input, pos)
            except ParseError as e:
                raise ParseError(Binary, input[begpos :]) from e
            else:
                formula = Binary(left, op, right)
        return formula, pos


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

    def evaluate(  # noqa: D102
            self,
            variables: Optional[AssignedVariables] = None
    ) -> Value:
        left_evaluated = self.left.evaluate(variables)
        logop = self.logop
        if isinstance(left_evaluated,
                      bool) and (left_evaluated and logop == LogOp.OR
                                 or not left_evaluated and logop == LogOp.AND):
            return left_evaluated
        right_evaluated = self.right.evaluate(variables)
        if isinstance(right_evaluated,
                      bool) and (right_evaluated and logop == LogOp.OR
                                 or not right_evaluated and logop == LogOp.AND):
            return right_evaluated
        if left_evaluated is None or right_evaluated is None:
            return None
        return logop.evaluate(
            value_to_bool(left_evaluated),
            value_to_bool(right_evaluated))

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
class IsDefined(Filter):
    """
    A test for whether a filter is defined.
    """

    formula: Filter

    def __str__(self) -> str:  # noqa: D105
        return f"?{self.formula}"

    def evaluate(  # noqa: D102
            self,
            variables: Optional[AssignedVariables] = None
    ) -> Value:
        return self.formula.evaluate(variables) is not None

    def simplify(  # noqa: D102
        self,
        variables: Optional[AssignedVariables] = None
    ) -> Union[bool,
               'IsDefined']:
        formula_simplified = self.formula.simplify(variables)
        if isinstance(formula_simplified, Filter):
            return type(self)(formula_simplified)
        else:
            return formula_simplified is not None

    @classmethod
    def _chain_parse(cls, input: str, pos: int) -> Tuple['IsDefined', int]:
        begpos = pos
        pos = cls._expect(input, pos, "?", begpos)
        pos = cls._lstrip(input, pos)
        formula, pos = cls.formula_type()._chain_parse(input, pos)
        return cls(formula), pos


@dataclass(frozen=True)
class ParensF(Parens[Filter], Filter):
    """
    A parenthetical around a package formula.
    """

    @property
    def variables(self) -> List[str]:  # noqa: D102
        return self.formula.variables

    def evaluate(  # noqa: D102
            self,
            variables: Optional[AssignedVariables] = None
    ) -> Value:
        return self.formula.evaluate(variables)

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
        """
        Parse a filter atom.

        A filter atom has the following grammar::

            <FilterAtom> ::= <varident>
                           | <string>
                           | <int>
                           | <bool>
        """
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
