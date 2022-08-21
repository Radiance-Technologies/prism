"""
Provides utilities for working with OCaml package constraints.
"""

import enum
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import partialmethod
from typing import (
    Any,
    Generic,
    Iterable,
    List,
    Mapping,
    Optional,
    Protocol,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from prism.util.abc_enum import ABCEnumMeta
from prism.util.parse import Parseable, ParseError

from .version import Version

# See https://opam.ocaml.org/doc/Manual.html#General-syntax
_letter_syntax: re.Pattern = re.compile("[a-zA-Z]")
_digit_syntax: re.Pattern = re.compile("[0-9]")
_int_syntax: re.Pattern = re.compile(rf"\-?{_digit_syntax.pattern}+")
_bool_syntax: re.Pattern = re.compile("true|false")
_string_syntax: re.Pattern = re.compile('"(.*)"|"""(.*)"""')
_identchar_syntax: re.Pattern = re.compile(
    rf"({_letter_syntax.pattern}|{_digit_syntax.pattern}|\-|_)")
_ident_syntax: re.Pattern = re.compile(
    f"{_identchar_syntax.pattern}*[a-zA-Z]{_identchar_syntax.pattern}*")
_varident_syntax: re.Pattern = re.compile(
    ''.join(
        [
            "(",
            f"({_ident_syntax.pattern}|_)",
            r"(\+",
            f"({_ident_syntax.pattern}|_))*:",
            f")?{_ident_syntax.pattern}"
        ]))


class LogOp(Parseable, enum.Enum, metaclass=ABCEnumMeta):
    """
    A logical binary relation (namely conjunction and disjunction).
    """

    AND = enum.auto()
    OR = enum.auto()

    def __str__(self) -> str:  # noqa: D105
        if self == LogOp.AND:
            result = "&"
        elif self == LogOp.OR:
            result = "|"
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

    @classmethod
    def _chain_parse(cls, input: str, pos: int) -> Tuple['RelOp', int]:
        input = input[pos : pos + 2]
        if len(input) == 2 and input[1] != "=":
            input = input[0]
        try:
            result = cls(input)
        except ValueError as e:
            raise ParseError(cls, input[pos :]) from e
        pos = cls._lstrip(input, pos + len(input))
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


class Formula(Protocol):
    """
    A protocol for satisfiable Boolean formulas.
    """

    def is_satisfied(self, *objects: Tuple[Any, ...]) -> bool:
        """
        Test whether the objects satisfy the constraints of the formula.
        """
        ...


class Variable(str):
    """
    A variable.
    """

    pass


class VersionFormula(Parseable, ABC):
    """
    A formula expressing constraints on a package version.

    Filtered version formulas are not yet supported, i.e.,
    https://opam.ocaml.org/doc/Manual.html#Filtered-package-formulas,
    except for basic atomic filters.
    """

    def __contains__(self, version: Version) -> bool:  # noqa: D105
        return self.is_satisfied(version)

    @abstractmethod
    def is_satisfied(self, version: Version) -> bool:
        """
        Return whether the given version is_satisfied this formula.
        """
        ...

    def filter(self, versions: Iterable[Version]) -> List[Version]:
        """
        Filter the given versions according to the constraint.

        Returns only those versions that satisfied the constraint in the
        order of their iteration.
        """
        return list(filter(self.is_satisfied, versions))

    @classmethod
    def _chain_parse(cls, input: str, pos: int) -> Tuple['VersionFormula', int]:
        begpos = pos
        try:
            formula, pos = FilterAtom._chain_parse(input, pos)
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


FormulaT = TypeVar('FormulaT', 'Formula', Parseable)


@dataclass(frozen=True)
class Logical(Parseable, Generic[FormulaT], ABC):
    """
    A logical combination of two version formulae.
    """

    left: FormulaT
    logop: LogOp
    right: FormulaT

    def __post_init__(self) -> None:
        """
        Ensure conjunction has higher precedence than disjunction.
        """
        cls = type(self)
        left = self.left
        logop = self.logop
        right = self.right
        if isinstance(left,
                      Logical) and (logop == LogOp.AND or logop == LogOp.OR
                                    and left.logop == LogOp.OR):
            # A | B & C incorrectly represented as (A | B) & C
            # or
            # A & B & C inefficiently represented as (A & B) & C
            # or
            # A | B | C inefficiently represented as (A | B) | C
            # (less efficient short-circuiting during evaluations)
            # Pivot!
            object.__setattr__(self, 'left', left.left)
            object.__setattr__(self, 'logop', left.logop)
            object.__setattr__(self, 'right', cls(left.right, logop, right))
            self.__post_init__()
        elif isinstance(
                right,
                Logical
        ) and self.logop == LogOp.AND and self.right.logop == LogOp.OR:
            # A & B | C incorrectly represented as A & (B | C)
            # Pivot!
            object.__setattr__(self, 'left', cls(left, logop, right.left))
            object.__setattr__(self, 'logop', right.logop)
            object.__setattr__(self, 'right', right.right)
            self.__post_init__()

    def __str__(self) -> str:  # noqa: D105
        return f"{self.left} {self.logop} {self.right}"

    def _to_list(
        self,
        op: LogOp,
        preceding: Optional[List['Logical[FormulaT]']] = None
    ) -> List['Logical[FormulaT]']:
        """
        Return an equivalent list implicitly joined by `LogOp`s.

        See Also
        --------
        to_conjunctive_list, to_disjunctive_list : For public APIs.
        """
        if preceding is None:
            preceding = []
        if self.logop == op:
            # by construction, there will not be any AND clauses to the
            # left
            preceding.append(self.left)
            if isinstance(self.right, Logical):
                self.right._to_list(op, preceding)
            else:
                preceding.append(self.right)
        return preceding

    def is_satisfied(self, objects: Any) -> bool:
        """
        Perform logical conjunction/disjunction on the paired formulae.
        """
        if self.left.is_satisfied(objects):
            return self.logop == LogOp.OR or self.right.is_satisfied(objects)
        else:
            return self.logop == LogOp.OR and self.right.is_satisfied(objects)

    to_conjunctive_list = partialmethod(_to_list, op=LogOp.AND)
    """
    Return an equivalent list implicitly joined by AND operators.

    Parameters
    ----------
    conjunctives : Optional[List['Logical[FormulaT]']], optional
        A preceding list of formulas, by default None.
        The list is modified in-place.

    Returns
    -------
    List['Logical[FormulaT]']
        The list of implicitly joined formulas.
        If `conjunctives` was provided, then it is returned.
    """

    to_disjunctive_list = partialmethod(_to_list, op=LogOp.OR)
    """
    Return an equivalent list implicitly joined by OR operators.

    Parameters
    ----------
    disjunctives : Optional[List['Logical[FormulaT]']], optional
        A preceding list of formulas, by default None.
        The list is modified in-place.

    Returns
    -------
    List['Logical[FormulaT]']
        The list of implicitly joined formulas.
        If `disjunctives` was provided, then it is returned.
    """

    @classmethod
    def _chain_parse(cls,
                     input: str,
                     pos: int) -> Tuple['Logical[FormulaT]',
                                        int]:
        """
        Parse a binary logical combination of package formulae.

        A logical combination matches the following grammar::

            <Logical> ::= <Formula> <LogOp> <Formula>
        """
        left, pos = cls.formula_type()._chain_parse(input, pos)
        pos = cls._lstrip(input, pos)
        logop, pos = LogOp._chain_parse(input, pos)
        pos = cls._lstrip(input, pos)
        right, pos = cls.formula_type()._chain_parse(input, pos)
        return cls(left, logop, right), pos

    @classmethod
    @abstractmethod
    def formula_type(cls) -> Type[FormulaT]:
        """
        Get the type of logical formula.
        """
        ...


@dataclass(frozen=True)
class Parens(Parseable, Generic[FormulaT], ABC):
    """
    A parenthetical around a package formula.
    """

    formula: FormulaT

    def __str__(self) -> str:  # noqa: D105
        return f"({self.formula})"

    def is_satisfied(self, objects: Any) -> bool:
        """
        Test whether the objects satisfy the internal formula.
        """
        return self.formula.is_satisfied(objects)

    @classmethod
    def _chain_parse(cls,
                     input: str,
                     pos: int) -> Tuple['Parens[FormulaT]',
                                        int]:
        """
        Parse a parenthesized version formula.

        A parenthesized formula has the following grammar::

            <ParensVF> ::= ( <VersionFormula> )
        """
        begpos = pos
        pos = cls._expect(input, pos, "(", begpos)
        pos = cls._lstrip(input, pos)
        try:
            formula, pos = cls.formula_type()._chain_parse(input, pos)
        except IndexError:
            raise ParseError(cls, input[begpos :])
        pos = cls._lstrip(input, pos)
        pos = cls._expect(input, pos, ")", begpos)
        pos = cls._lstrip(input, pos)
        return cls(formula), pos

    @classmethod
    @abstractmethod
    def formula_type(cls) -> Type[FormulaT]:
        """
        Get the type of parenthetical formula.
        """
        ...


@dataclass(frozen=True)
class FilterAtom(VersionFormula):
    """
    Placeholder for full filter functionality.

    See https://opam.ocaml.org/doc/Manual.html#Filters for more
    information.
    """

    term: Union[Variable, str, int, bool]

    def __str__(self) -> str:
        """
        Print the atom.
        """
        return str(self.term)

    def is_satisfied(self, version: Version) -> bool:
        """
        Return False.

        Placeholder, equivalent to treating all filters as undefined.
        """
        return False

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
        return FilterAtom(term), pos


@dataclass(frozen=True)
class LogicalVF(Logical[VersionFormula], VersionFormula):
    """
    A logical combination of two version formulae.
    """

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

    def is_satisfied(self, version: Version) -> bool:
        """
        Test whether the version does not satisfy the internal formula.
        """
        return not self.formula.is_satisfied(version)

    @classmethod
    def _chain_parse(cls, input: str, pos: int) -> Tuple['Not', int]:
        begpos = pos
        pos = cls._expect(input, pos, "!", begpos)
        pos = cls._lstrip(input, pos)
        formula, pos = VersionFormula._chain_parse(input, pos)
        return Not(formula), pos


@dataclass(frozen=True)
class ParensVF(Parens[VersionFormula]):
    """
    A parenthetical around a package formula.
    """

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

    def is_satisfied(self, version: Version) -> bool:
        """
        Test whether the version is_satisfied the binary relation.
        """
        if self.relop == RelOp.EQ:
            result = version == self.version
        elif self.relop == RelOp.NEQ:
            result = version != self.version
        elif self.relop == RelOp.LT:
            result = version < self.version
        elif self.relop == RelOp.LEQ:
            result = version <= self.version
        elif self.relop == RelOp.GT:
            result = version > self.version
        elif self.relop == RelOp.GEQ:
            result = version >= self.version
        return result

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
        return VersionConstraint(relop, version), pos


class PackageFormula(Parseable, ABC):
    """
    A formula expressing a set of package requirements.

    Filtered package formulas are not yet directly supported, i.e.,
    https://opam.ocaml.org/doc/Manual.html#Filtered-package-formulas.
    """

    @abstractmethod
    def is_satisfied(self, packages: Mapping[str, Version]) -> bool:
        """
        Test whether the given versioned packages satisfy the formula.

        Parameters
        ----------
        packages : Mapping[str, Version]
            A map from package names to versions.

        Returns
        -------
        bool
            Whether the given packages satisfy the constraints of the
            formula.
        """
        ...

    @classmethod
    def _chain_parse(cls, input: str, pos: int) -> Tuple['Parseable', int]:
        """
        Parse a package formula.

        A package formula has the following grammar::

            <PackageFormula> ::= <LogicalPF>
                               | <ParensPF>
                               | <PackageConstraint>
        """
        begpos = pos
        try:
            formula, pos = ParensPF._chain_parse(input, pos)
        except ParseError:
            formula, pos = PackageConstraint._chain_parse(input, pos)
        # attempt some left recursion
        left = formula
        try:
            logop, pos = LogOp._chain_parse(input, pos)
        except ParseError:
            pass
        else:
            try:
                right, pos = PackageFormula._chain_parse(input, pos)
            except ParseError as e:
                raise ParseError(LogicalPF, input[begpos :]) from e
            else:
                formula = LogicalPF(left, logop, right)
        return formula, pos


@dataclass(frozen=True)
class LogicalPF(Logical[PackageFormula], PackageFormula):
    """
    A logical combination of two version formulae.
    """

    @classmethod
    def formula_type(cls) -> Type[PackageFormula]:  # noqa: D102
        return PackageFormula


@dataclass(frozen=True)
class ParensPF(Parens[PackageFormula]):
    """
    A parenthetical around a package formula.
    """

    @classmethod
    def formula_type(cls) -> Type[PackageFormula]:  # noqa: D102
        return PackageFormula


@dataclass(frozen=True)
class PackageConstraint(PackageFormula):
    """
    A package paired with any version constraints.
    """

    package_name: str
    version_constraint: Optional[Union[Version, VersionFormula]] = None

    def __str__(self) -> str:  # noqa: D105
        version_constraint = self.version_constraint
        if version_constraint is None:
            result = f'"{self.package_name}"'
        elif isinstance(version_constraint, Version):
            result = f'"{self.package_name}.{version_constraint}"'
        else:
            result = ' '.join(
                [f'"{self.package_name}"',
                 "{",
                 str(version_constraint),
                 "}"])
        return result

    def is_satisfied(self, packages: Mapping[str, Version]) -> bool:
        """
        Return whether the package constraint is satisfied.

        Parameters
        ----------
        packages : Mapping[str, Version]
            A map from package names to versions.

        Returns
        -------
        bool
            If one of the given packages is_satisfied the constraint.
        """
        try:
            version = packages[self.package_name]
        except KeyError:
            return False
        else:
            constraint = self.version_constraint
            if constraint is None:
                return True
            elif isinstance(constraint, Version):
                return version == constraint
            else:
                return constraint.is_satisfied(version)

    @classmethod
    def _chain_parse(cls,
                     input: str,
                     pos: int) -> Tuple['PackageConstraint',
                                        int]:
        """
        Parse a package constraint.

        A package constraint matches the following grammar::

            <PackageConstraint> ::= <pkgname> { <VersionFormula> }
                                  | <pkgname>
                                  | <package>
            <pkgname>           ::= (") <ident> (")
            <package>           ::= (") <ident> "." <Version> (")
        """
        begpos = pos
        pos = cls._expect(input, pos, '"', begpos)
        p = []
        while pos < len(input):
            char = input[pos]
            if _identchar_syntax.match(char) is None:
                break
            else:
                p.append(char)
                pos += 1
        try:
            pos = cls._expect(input, pos, '.', begpos)
        except ParseError:
            pos = cls._expect(input, pos, '"', begpos)
            pos = cls._lstrip(input, pos)
            try:
                pos = cls._expect(input, pos, '{', begpos)
            except ParseError:
                version_constraint = None
            else:
                pos = cls._lstrip(input, pos)
                version_constraint, pos = VersionFormula._chain_parse(input, pos)
                pos = cls._lstrip(input, pos)
                pos = cls._expect(input, pos, '}', begpos)
        else:
            (version_constraint,
             pos) = Version._chain_parse(
                 input,
                 pos,
                 require_quotes=False)
            pos = cls._expect(input, pos, '"', begpos)
        pos = cls._lstrip(input, pos)
        return PackageConstraint(''.join(p), version_constraint), pos
