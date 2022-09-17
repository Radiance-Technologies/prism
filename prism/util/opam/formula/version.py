"""
Defines classes for parsing and expressing version constraints.
"""

import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import partial
from typing import Iterable, List, Optional, Set, Tuple, Type, Union

from prism.util.opam.formula.negate import Not
from prism.util.opam.version import Version
from prism.util.parse import Parseable, ParseError

from .common import (
    AssignedVariables,
    LogOp,
    RelOp,
    value_to_bool,
    value_to_string,
)
from .filter import Filter, FilterAtom
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
    def variables(self) -> Set[str]:
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

    def filter_versions(
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
            variables: Optional[AssignedVariables] = None,
            evaluate_filters: bool = False) -> Union[bool,
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
            formula, pos = FilterVF._chain_parse(input, pos)
        except ParseError:
            try:
                formula, pos = VersionConstraint._chain_parse(input, pos)
            except ParseError:
                try:
                    formula, pos = FilterConstraint._chain_parse(input, pos)
                except ParseError:
                    try:
                        formula, pos = ParensVF._chain_parse(input, pos)
                    except ParseError:
                        formula, pos = NotVF._chain_parse(input, pos)
        # attempt some left recursion
        # lookback to check that the previous term is not a negation
        if cls._lookback(input, begpos, 1)[0] != "!":
            try:
                formula, pos = cls._lookahead_parse(begpos, formula, input, pos)
            except ParseError:
                pass
        return formula, pos

    @classmethod
    def _lookahead_parse(
            cls,
            begpos: int,
            left: 'VersionFormula',
            input: str,
            pos: int) -> Tuple['VersionFormula',
                               int]:
        """
        Parse a binary relation by speculatively looking ahead.
        """
        try:
            logop, pos = LogOp._chain_parse(input, pos)
        except ParseError:
            formula = left
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
    def variables(self) -> Set[str]:  # noqa: D102
        variables = self.left.variables.union(self.right.variables)
        return variables

    def simplify(
            self,
            version: Optional[Version],
            variables: Optional[AssignedVariables] = None,
            evaluate_filters: bool = False) -> Union[bool,
                                                     VersionFormula]:
        """
        Simplify the logical formula.

        Note that an undefined filter prohibits simplification of
        versions bound to the filter's resolution. In other words, if a
        logical operator is applied to a filter, then versions in the
        other branch of the logical formula cannot be simplified unless
        the filter is defined. Otherwise, one may receive incorrect
        results when testing the simplified formula for satisfaction.
        """
        # NOTE: this is mainly necessary because we used None to reflect
        # undefined filter formulas versus a wrapper around the
        # undefined formula as in the source OCaml.
        if evaluate_filters or self.logop == LogOp.OR:
            return super().simplify(version, variables, evaluate_filters=True)
        else:
            # filters that retain undefined variables cannot be
            # simplified away
            if (isinstance(self.left,
                           (FilterVF,
                            FilterConstraint)) and self.left.variables):
                left_simplified = self.left.simplify(
                    version,
                    variables,
                    evaluate_filters=False)
                if isinstance(left_simplified, (FilterVF, FilterConstraint)):
                    # still a filter with undefined variables,
                    # cannot remove logop
                    return type(self)(
                        left_simplified,
                        self.logop,
                        self.right.simplify(
                            None,
                            variables,
                            evaluate_filters=False))
                else:
                    # filter is defined
                    if isinstance(left_simplified, (bool, int, str)):
                        # ensure formula is well-typed
                        left_simplified = FilterVF(FilterAtom(left_simplified))
                    return type(self)(left_simplified,
                                      self.logop,
                                      self.right).simplify(
                                          version,
                                          variables,
                                          evaluate_filters=False)
            elif (isinstance(self.right,
                             (FilterVF,
                              FilterConstraint)) and self.right.variables):
                right_simplified = self.right.simplify(
                    version,
                    variables,
                    evaluate_filters=False)
                if isinstance(right_simplified, (FilterVF, FilterConstraint)):
                    # still a filter with undefined variables,
                    # cannot remove logop
                    return type(self)(
                        self.left.simplify(
                            None,
                            variables,
                            evaluate_filters=False),
                        self.logop,
                        right_simplified)
                else:
                    # filter is defined
                    if isinstance(right_simplified, (bool, int, str)):
                        # ensure formula is well-typed
                        right_simplified = FilterVF(
                            FilterAtom(right_simplified))
                    return type(self)(self.left,
                                      self.logop,
                                      right_simplified).simplify(
                                          version,
                                          variables,
                                          evaluate_filters=False)
            else:
                return super().simplify(
                    version,
                    variables,
                    evaluate_filters=False)

    @classmethod
    def formula_type(cls) -> Type[VersionFormula]:  # noqa: D102
        return VersionFormula


@dataclass(frozen=True)
class NotVF(Not[VersionFormula], VersionFormula):
    """
    A logical negation of a version formula.
    """

    @property
    def variables(self) -> Set[str]:  # noqa: D102
        return self.formula.variables

    @classmethod
    def formula_type(cls) -> Type[VersionFormula]:  # noqa: D102
        return VersionFormula


@dataclass(frozen=True)
class ParensVF(Parens[VersionFormula], VersionFormula):
    """
    A parenthetical around a package formula.
    """

    @property
    def variables(self) -> Set[str]:  # noqa: D102
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
    def variables(self) -> Set[str]:  # noqa: D102
        return set()

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
            variables: Optional[AssignedVariables] = None,
            evaluate_filters: bool = False) -> Union[bool,
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
    def variables(self) -> Set[str]:  # noqa: D102
        return self.filter.variables

    def is_satisfied(  # noqa: D102
            self,
            version: Version,
            variables: Optional[AssignedVariables] = None) -> bool:
        return value_to_bool(self.filter.evaluate(variables))

    def simplify(  # noqa: D102
        self,
        version: Optional[Version],
        variables: Optional[AssignedVariables] = None,
        evaluate_filters : bool = False
    ) -> Union[bool,
               'FilterVF']:
        if evaluate_filters:
            return self.is_satisfied(version, variables)
        else:
            simplified_filter = self.filter.simplify(variables)
            if isinstance(simplified_filter, Filter):
                return type(self)(simplified_filter)
            else:
                return value_to_bool(simplified_filter)

    @classmethod
    def _chain_parse(cls,
                     input: str,
                     pos: int) -> Tuple['FilterConstraint',
                                        int]:
        """
        Parse a filter constraint.

        A filter constraint has the following grammar::

            <FilterConstraint> ::= <RelOp> <Filter>
        """
        filter, pos = Filter._chain_parse(input, pos)
        return cls(filter), pos


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
    def variables(self) -> Set[str]:  # noqa: D102
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
            variables: Optional[AssignedVariables] = None,
            evaluate_filters: bool = False) -> Union[bool,
                                                     VersionFormula]:
        """
        Test whether the version satisfies the binary relation.

        If the version is not None, a Boolean will be returned.
        Otherwise, this instance is returned.
        """
        if evaluate_filters:
            simplified_filter = self.filter.evaluate(variables)
        else:
            simplified_filter = self.filter.simplify(variables)
        if isinstance(simplified_filter, Filter):
            simplified = type(self)(self.relop, simplified_filter)
        else:
            try:
                version = Version.parse(value_to_string(simplified_filter))
            except ParseError:
                warnings.warn(f"Ignoring version constraint {self}")
                simplified = False
            else:
                simplified = VersionConstraint(self.relop, version)
        if version is not None:
            simplified = simplified.is_satisfied(version, variables)
        return simplified

    @classmethod
    def _chain_parse(cls,
                     input: str,
                     pos: int) -> Tuple['FilterConstraint',
                                        int]:
        """
        Parse a filter constraint.

        A filter constraint has the following grammar::

            <FilterConstraint> ::= <RelOp> <Filter>
        """
        relop, pos = RelOp._chain_parse(input, pos)
        pos = cls._lstrip(input, pos)
        filter, pos = Filter._chain_parse(input, pos)
        pos = cls._lstrip(input, pos)
        return cls(relop, filter), pos
