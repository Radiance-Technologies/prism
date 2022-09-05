"""
Defines classes for parsing and expressing version constraints.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import partial
from typing import Iterable, List, Optional, Tuple, Type, Union

from prism.util.opam.version import Version
from prism.util.parse import Parseable, ParseError

from .common import (
    AssignedVariables,
    LogOp,
    RelOp,
    value_to_bool,
    value_to_string,
)
from .filter import Filter
from .logical import Logical
from .parens import Parens


class VersionFormula(Parseable, ABC):
    """
    A formula expressing constraints on a package version.

    Filtered version formulas are not yet supported, i.e.,
    https://opam.ocaml.org/doc/Manual.html#Filtered-package-formulas,
    except for basic atomic filters.
    """

    # TODO: let version formulas evaluate to empty, which means they
    # are not applied in package formulas

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
    def is_satisfied(
            self,
            version: Version,
            variables: Optional[AssignedVariables] = None) -> bool:
        """
        Return whether the given version/variables satisfy this formula.
        """
        ...

    def filter(
            self,
            versions: Iterable[Version],
            variables: Optional[AssignedVariables] = None) -> List[Version]:
        """
        Filter the given versions according to the constraint.

        Returns only those versions that satisfied the constraint in the
        order of their iteration.
        """
        if variables is None:
            variables = {}
        return list(
            filter(partial(self.is_satisfied,
                           variables=variables),
                   versions))

    @abstractmethod
    def simplify(
        self,
        version: Optional[Version],
        variables: Optional[AssignedVariables] = None
    ) -> Union[bool,
               'VersionFormula']:
        """
        Substitute the given version and variables into the formula.

        If the version is None, the formula may still be simplified and
        even evaluate to True or False through variable substitutions.
        """
        ...

    @classmethod
    def _chain_parse(cls, input: str, pos: int) -> Tuple['VersionFormula', int]:
        begpos = pos
        try:
            formula, pos = FilterConstraint._chain_parse(input, pos)
        except ParseError:
            try:
                formula, pos = VersionConstraint._chain_parse(input, pos)
            except ParseError:
                try:
                    formula, pos = ParensVF._chain_parse(input, pos)
                except ParseError:
                    formula, pos = Not._chain_parse(input, pos)
        # attempt some left recursion
        # lookback to check that the previous term is not a negation
        if cls._lookback(input, begpos, 1)[0] != "!":
            left = formula
            try:
                logop, pos = LogOp._chain_parse(input, pos)
            except ParseError:
                pass
            else:
                try:
                    right, pos = VersionFormula._chain_parse(input, pos)
                except ParseError as e:
                    raise ParseError(LogicalVF, input[begpos :]) from e
                else:
                    formula = LogicalVF(left, logop, right)
        return formula, pos


@dataclass(frozen=True)
class LogicalVF(Logical[VersionFormula], VersionFormula):
    """
    A logical combination of two version formulae.
    """

    @property
    def variables(self) -> List[str]:  # noqa: D102
        variables = []
        variables.extend(self.left.variables)
        variables.extend(self.right.variables)
        return variables

    @classmethod
    def formula_type(cls) -> Type[VersionFormula]:  # noqa: D102
        return VersionFormula


@dataclass(frozen=True)
class Not(VersionFormula):
    """
    A logical negation of a version formula.
    """

    formula: VersionFormula

    def __str__(self) -> str:  # noqa: D105
        return f"!{self.formula}"

    @property
    def variables(self) -> List[str]:  # noqa: D102
        return self.formula.variables

    def is_satisfied(
            self,
            version: Version,
            variables: Optional[AssignedVariables] = None) -> bool:
        """
        Test whether the version does not satisfy the internal formula.
        """
        return not self.formula.is_satisfied(version, variables)

    def simplify(
            self,
            version: Optional[Version],
            variables: Optional[AssignedVariables] = None) -> Union[bool,
                                                                    'Not']:
        """
        Substitute the given version and variables and simplify.
        """
        formula_simplified = self.formula.simplify(version, variables)
        if isinstance(formula_simplified, bool):
            return not formula_simplified
        else:
            return type(self)(formula_simplified)

    @classmethod
    def _chain_parse(cls, input: str, pos: int) -> Tuple['Not', int]:
        begpos = pos
        pos = cls._expect(input, pos, "!", begpos)
        pos = cls._lstrip(input, pos)
        formula, pos = VersionFormula._chain_parse(input, pos)
        return cls(formula), pos


@dataclass(frozen=True)
class ParensVF(Parens[VersionFormula], VersionFormula):
    """
    A parenthetical around a package formula.
    """

    @property
    def variables(self) -> List[str]:  # noqa: D102
        return self.formula.variables

    @classmethod
    def formula_type(cls) -> Type[VersionFormula]:  # noqa: D102
        return VersionFormula


@dataclass(frozen=True)
class VersionConstraint(VersionFormula):
    """
    A constraint relative to a specific version.
    """

    relop: RelOp
    version: Version

    def __str__(self) -> str:  # noqa: D105
        return f'{self.relop} "{self.version}"'

    @property
    def variables(self) -> List[str]:  # noqa: D102
        return []

    def is_satisfied(
            self,
            version: Version,
            variables: Optional[AssignedVariables] = None) -> bool:
        """
        Test whether the version satisfies the binary relation.
        """
        return self.relop(version, self.version)

    def simplify(
        self,
        version: Optional[Version],
        variables: Optional[AssignedVariables] = None
    ) -> Union[bool,
               'VersionConstraint']:
        """
        Test whether the version satisfies the binary relation.

        If the version is not None, a Boolean will be returned.
        Otherwise, this instance is returned.
        """
        if version is not None:
            return self.is_satisfied(version)
        else:
            return self

    @classmethod
    def _chain_parse(cls,
                     input: str,
                     pos: int) -> Tuple['VersionConstraint',
                                        int]:
        """
        Parse a version constraint.

        A version constraint has the following grammar::

            <VersionConstraint> ::= <RelOp> <Version>
        """
        relop, pos = RelOp._chain_parse(input, pos)
        pos = cls._lstrip(input, pos)
        version, pos = Version._chain_parse(input, pos, require_quotes=True)
        pos = cls._lstrip(input, pos)
        return cls(relop, version), pos


@dataclass(frozen=True)
class FilterVF(VersionFormula):
    """
    A raw filter.
    """

    filter: Filter

    def __str__(self) -> str:  # noqa: D105
        return f"{self.filter}"

    @property
    def variables(self) -> List[str]:  # noqa: D102
        return self.filter.variables

    def is_satisfied(  # noqa: D102
            self,
            version: Version,
            variables: Optional[AssignedVariables] = None) -> bool:
        return value_to_bool(self.filter.evaluate(variables))

    def simplify(  # noqa: D102
        self,
        version: Optional[Version],
        variables: Optional[AssignedVariables] = None
    ) -> Union[bool,
               'VersionFormula']:
        simplified_filter = type(self)(self.filter.simplify(variables))
        if isinstance(simplified_filter, Filter):
            return type(self)(simplified_filter)
        else:
            return value_to_bool(simplified_filter)


@dataclass(frozen=True)
class FilterConstraint(VersionFormula):
    """
    A constraint relative to a specific filter.
    """

    relop: RelOp
    filter: Filter

    def __str__(self) -> str:  # noqa: D105
        return f'{self.relop} {self.filter}'

    @property
    def variables(self) -> List[str]:  # noqa: D102
        return self.filter.variables

    def is_satisfied(
            self,
            version: Version,
            variables: Optional[AssignedVariables] = None) -> bool:
        """
        Test whether the version satisfies the binary relation.
        """
        target = value_to_string(self.filter.evaluate(variables))
        target = Version.parse(target, check_syntax=False, require_quotes=False)
        return self.relop(version, target)

    def simplify(
        self,
        version: Optional[Version],
        variables: Optional[AssignedVariables] = None
    ) -> Union[bool,
               'VersionConstraint']:
        """
        Test whether the version satisfies the binary relation.

        If the version is not None, a Boolean will be returned.
        Otherwise, this instance is returned.
        """
        simplified_filter = self.filter.simplify(variables)
        simplified = type(self)(self.relop, simplified_filter)
        if version is not None and not isinstance(simplified_filter, Filter):
            return simplified.is_satisfied(version, variables)
        else:
            return simplified

    @classmethod
    def _chain_parse(cls,
                     input: str,
                     pos: int) -> Tuple['VersionConstraint',
                                        int]:
        """
        Parse a version constraint.

        A version constraint has the following grammar::

            <FilterConstraint> ::= <RelOp> <Filter>
        """
        relop, pos = RelOp._chain_parse(input, pos)
        pos = cls._lstrip(input, pos)
        filter, pos = Filter._chain_parse(input, pos)
        pos = cls._lstrip(input, pos)
        return cls(relop, filter), pos
