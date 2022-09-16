"""
Defines classes for parsing and expressing package dependencies.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, List, Mapping, Optional, Set, Tuple, Type, Union

from prism.util.opam.version import Version
from prism.util.parse import Parseable, ParseError

from .common import AssignedVariables, LogOp, _identchar_syntax
from .logical import Logical
from .parens import Parens
from .version import VersionFormula


class PackageFormula(Parseable, ABC):
    """
    A formula expressing a set of package requirements.

    Filtered package formulas are not yet directly supported, i.e.,
    https://opam.ocaml.org/doc/Manual.html#Filtered-package-formulas.
    """

    def __contains__(
        self,
        packages: Union[Mapping[str,
                                Version],
                        Tuple[Mapping[str,
                                      Version],
                              AssignedVariables]]
    ) -> bool:
        """
        Return whether the given packages/variables satisfy the formula.
        """
        if isinstance(packages, tuple):
            variables = packages[1]
            packages = packages[0]
        else:
            variables = None
        return self.is_satisfied(packages, variables)

    @property
    @abstractmethod
    def packages(self) -> Set[str]:
        """
        Get a list of the names of packages contained in the formula.
        """
        ...

    @property
    @abstractmethod
    def size(self) -> int:
        """
        Get the number of package constraints that must be satisfied.

        More precisely, get the minimum number of package constraints in
        this formula that must be satisfied for it to simplify to True.
        """
        ...

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
            packages: Mapping[str,
                              Version],
            variables: Optional[AssignedVariables] = None) -> bool:
        """
        Test whether the given versioned packages satisfy the formula.

        Parameters
        ----------
        packages : Mapping[str, Version]
            A map from package names to versions.
        variables : AssignedVariables
            A map from formula variable names to their values.

        Returns
        -------
        bool
            Whether the given packages satisfy the constraints of the
            formula.
        """
        ...

    @abstractmethod
    def map(
        self,
        f: Callable[['PackageConstraint'],
                    'PackageConstraint']
    ) -> 'PackageFormula':
        """
        Map a function over the package constraints in the formula.

        Parameters
        ----------
        f : Callable[[PackageConstraint], PackageConstraint]
            A function that modifies the constraints in this formula.

        Returns
        -------
        PackageFormula
            A new formula with the results of the mapped constraints
        """
        ...

    @abstractmethod
    def simplify(
            self,
            packages: Mapping[str,
                              Version],
            variables: Optional[AssignedVariables] = None,
            evaluate_filters: bool = True) -> Union[bool,
                                                    'PackageFormula']:
        """
        Substitute the packagse into the formula and simplify it.

        Parameters
        ----------
        packages : Mapping[str, Version]
            A map from package names to versions.
        variables : AssignedVariables
            A map from formula variable names to their values.
        evaluate_filters : bool, optional
            Whether to evaluate undefined filter variables or leave them
            in the simplified formula, by default True.

        Returns
        -------
        Union[bool, PackageFormula]
            True if the given packages satisfy the constraints of the
            formula, False if any constraints are violated, or the
            remaining formula for any parts left unevaluated.
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
        try:
            formula, pos = cls._lookahead_parse(begpos, formula, input, pos)
        except ParseError:
            pass
        return formula, pos

    @classmethod
    def _lookahead_parse(
            cls,
            begpos: int,
            left: 'PackageFormula',
            input: str,
            pos: int) -> Tuple['PackageFormula',
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

    @property
    def packages(self) -> Set[str]:  # noqa: D102
        packages = self.left.packages.union(self.right.packages)
        return packages

    @property
    def size(self) -> int:  # noqa: D102
        if self.logop == LogOp.AND:
            return self.left.size + self.right.size
        else:
            return min(self.left.size, self.right.size)

    @property
    def variables(self) -> Set[str]:  # noqa: D102
        variables = self.left.variables.union(self.right.variables)
        return variables

    def map(  # noqa: D102
        self,
        f: Callable[['PackageConstraint'],
                    'PackageConstraint']
    ) -> 'LogicalPF':
        return type(self)(self.left.map(f), self.logop, self.right.map(f))

    @classmethod
    def formula_type(cls) -> Type[PackageFormula]:  # noqa: D102
        return PackageFormula


@dataclass(frozen=True)
class ParensPF(Parens[PackageFormula], PackageFormula):
    """
    A parenthetical around a package formula.
    """

    @property
    def packages(self) -> Set[str]:  # noqa: D102
        return self.formula.packages

    @property
    def size(self) -> int:  # noqa: D102
        return self.formula.size

    @property
    def variables(self) -> List[str]:  # noqa: D102
        return self.formula.variables

    def map(  # noqa: D102
        self,
        f: Callable[['PackageConstraint'],
                    'PackageConstraint']
    ) -> 'ParensPF':
        return type(self)(self.formula.map(f))

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

    @property
    def packages(self) -> Set[str]:  # noqa: D102
        return {self.package_name}

    @property
    def size(self) -> int:  # noqa: D102
        return 1

    @property
    def variables(self) -> Set[str]:  # noqa: D102
        if isinstance(self.version_constraint, VersionFormula):
            return self.version_constraint.variables
        else:
            return set()

    def is_satisfied(
            self,
            packages: Mapping[str,
                              Version],
            variables: Optional[AssignedVariables] = None) -> bool:
        """
        Return whether the package constraint is satisfied.

        Parameters
        ----------
        packages : Mapping[str, Version]
            A map from package names to versions.
        variables : AssignedVariables
            A map from formula variable names to their values.

        Returns
        -------
        bool
            If one of the given packages satisfies the constraint.
        """
        constraint = self.version_constraint
        if isinstance(constraint, VersionFormula):
            # perform the equivalent of
            # opam/src/format/opamFilter.mli:filter_deps
            constraint = constraint.simplify(
                None,
                variables,
                evaluate_filters=True)
            if isinstance(constraint, bool):
                if constraint:
                    constraint = None
                else:
                    return True
        try:
            version = packages[self.package_name]
        except KeyError:
            return False
        else:
            if constraint is None:
                return True
            elif isinstance(constraint, Version):
                return version == constraint
            else:
                return constraint.is_satisfied(version, variables)

    def map(  # noqa: D102
        self,
        f: Callable[['PackageConstraint'],
                    'PackageConstraint']
    ) -> 'PackageFormula':
        return f(self)

    def simplify(
            self,
            packages: Mapping[str,
                              Version],
            variables: Optional[AssignedVariables] = None,
            evaluate_filters: bool = True) -> Union[bool,
                                                    'PackageFormula']:
        """
        Substitute the given package versions into the formula.

        Parameters
        ----------
        packages : Mapping[str, Version]
            A map from package names to versions.
        variables : AssignedVariables
            A map from formula variable names to their values.
        evaluate_filters : bool, optional
            Whether to evaluate undefined filter variables or leave them
            in the simplified formula, by default True.

        Returns
        -------
        Union[bool, PackageFormula]
            This formula if its package is not in the mapping.
            Otherwise, the simplification of the version formula.
        """
        constraint = self.version_constraint
        if isinstance(constraint, VersionFormula):
            constraint = constraint.simplify(
                None,
                variables,
                evaluate_filters=evaluate_filters)
            if isinstance(constraint, bool):
                if constraint:
                    constraint = None
                else:
                    return True
        result = None
        try:
            version = packages[self.package_name]
        except KeyError:
            result = type(self)(self.package_name, constraint)
        else:
            if constraint is None:
                result = True
            elif isinstance(constraint, Version):
                result = version == constraint
            else:
                constraint_simplified = constraint.simplify(version, variables)
                if isinstance(constraint_simplified, bool):
                    result = constraint_simplified
                else:
                    result = type(self)(
                        self.package_name,
                        constraint_simplified)
        assert result is not None
        return result

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
        return cls(''.join(p), version_constraint), pos
