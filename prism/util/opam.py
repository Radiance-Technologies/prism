"""
Supplies utilities for querying OCaml package information.
"""

import re
from dataclasses import dataclass
from functools import total_ordering
from typing import Dict, Optional, Set, Tuple, Union

import seutil.bash as bash

from .compare import Bottom, Top


class VersionParseError(Exception):
    """
    Represents an error encountered during Ocaml version parsing.
    """

    pass


@total_ordering
@dataclass(frozen=True)
class Version:
    """
    An OCaml package version.
    """

    major: int
    minor: int
    patch: int
    prerelease: Optional[str]
    extra: Optional[str]

    def __lt__(self, other: 'Version') -> bool:  # noqa: D105
        if not isinstance(other, Version):
            return NotImplemented
        return self.key < other.key

    def __str__(self) -> str:
        """
        Pretty-print the version.
        """
        prerelease = "" if self.prerelease is None else f"~{self.prerelease}"
        extra = "" if self.extra is None else f"+{self.extra}"
        return f"{self.major}.{self.minor}.{self.patch}{prerelease}{extra}"

    @property
    def key(self) -> Tuple[int,
                           int,
                           int,
                           Union[Bottom,
                                 str],
                           Union[Bottom,
                                 str]]:
        """
        Get a key by which versions may be compared.

        Returns
        -------
        Tuple[int, int, int, Union[Bottom, str], Union[Bottom, str]]
            A key that can be compared lexicographically to determine if
            one version supercedes another.
        """
        return (
            self.major,
            self.minor,
            self.patch,
            # None > Some
            Top() if self.prerelease is None else self.prerelease,
            Bottom() if self.extra is None else self.extra)

    @classmethod
    def parse(cls, version: str) -> 'Version':
        """
        Parse the version from a string.

        Raises
        ------
        VersionParseError
            If a version cannot be parsed from the given string.
        """
        prerelease = None
        try:
            (major,
             minor,
             patch,
             sep,
             extra) = re.match(r"(\d+).(\d+).(\d+)([+~])?(\S+)?",
                               version).groups()
        except TypeError:
            raise VersionParseError(f"Failed to parse version from {version}")
        if sep == "~":
            prerelease, extra = re.match(r"(\S+)+?(\S+)", extra).groups()
        return Version(major, minor, patch, prerelease, extra)


@dataclass(frozen=True)
class VersionConstraint:
    """
    An OCaml package version constraint.
    """

    lower_bound: Optional[Version] = None
    upper_bound: Optional[Version] = None
    lower_closed: bool = False
    upper_closed: bool = False

    def __contains__(self, item: Version) -> bool:
        """
        Return whether a given version satisfies the constraint.
        """
        if not isinstance(item, Version):
            return NotImplemented
        lower_bound = self.lower_bound
        if lower_bound is None:
            lower_bound = Bottom()
        upper_bound = self.upper_bound
        if upper_bound is None:
            upper_bound = Top()
        if ((self.lower_closed and lower_bound <= item)
                or (not self.lower_closed and lower_bound < item)):
            return (
                (self.upper_closed and upper_bound >= item)
                or (not self.upper_closed and upper_bound > item))
        return False

    def __str__(self) -> str:
        """
        Pretty-print the version constraint.
        """
        pretty = []
        if self.lower_bound is not None:
            if self.lower_closed:
                pretty.append(">=")
            else:
                pretty.append(">")
            pretty.append(str(self.lower_bound))
        if self.upper_bound is not None:
            if pretty:
                pretty.append("&")
            if self.upper_closed:
                pretty.append("<=")
            else:
                pretty.append("<")
            pretty.append(str(self.upper_bound))
        return " ".join(pretty)

    @classmethod
    def parse(cls, constraint: str) -> 'VersionConstraint':
        """
        Parse a version constraint.

        This parser is very simple and does not verify that the expected
        format is met.
        Consequently, incorrect results may be obtained for unusual
        constraints.

        Parameters
        ----------
        constraint : str
            A constraint on a package version in the format returned by
            OPAM, e.g., ``{>= "4.08.1" & < "4.08.2~"}``

        Returns
        -------
        VersionConstraint
            The constraint specifying a version range.
        """
        lower_bound = None
        upper_bound = None
        lower_closed = False
        upper_closed = False
        constraint = re.sub(r"\{|\}|\||\"", "", constraint).split(" ")
        i = 0
        while i < len(constraint):
            token = constraint[i]
            set_lower = False
            set_upper = False
            if token.endswith(">="):
                lower_closed = True
                set_lower = True
                i += 1
            elif token.endswith(">"):
                set_lower = True
                i += 1
            elif token.endswith("<="):
                upper_closed = True
                set_upper = True
                i += 1
            elif token.endswith("<"):
                set_upper = True
                i += 1
            elif token.endswith('='):
                lower_closed = True
                upper_closed = True
                set_lower = True
                set_upper = True
                i += 1
            if set_lower:
                lower_bound = constraint[i]
            if set_upper:
                upper_bound = constraint[i]
            i += 1
        if lower_bound is not None:
            lower_bound = Version.parse(lower_bound)
        if upper_bound is not None:
            upper_bound = Version.parse(upper_bound)
        return VersionConstraint(
            lower_bound,
            upper_bound,
            lower_closed,
            upper_closed)


class OpamAPI:
    """
    Provides methods for querying the OCaml package manager.

    .. warning::
        This class does not yet fully support the full expressivity of
        OPAM dependencies as documented at
        https://opam.ocaml.org/blog/opam-extended-dependencies/.
    """

    @classmethod
    def get_dependencies(
            cls,
            pkg: str,
            version: Optional[str] = None) -> Dict[str,
                                                   VersionConstraint]:
        """
        Get the dependencies of the indicated package.

        Note that OPAM must be installed.

        Parameters
        ----------
        pkg : str
            The name of an OCaml package.
        version : Optional[str], optional
            A specific version of the package, by default None.
            If not given, then either the latest or the installed
            version of the package will be queried for dependencies.

        Returns
        -------
        Dict[str, VersionConstraint]
            Dependencies as a map from package names to version
            constraints.
        """
        if version is not None:
            pkg = f"{pkg}={version}"
        r = bash.run(f"opam show -f depends: {pkg}")
        r.check_returncode()
        dependencies: Set[Tuple[str, str]]
        dependencies = [
            re.split(r"\s+",
                     dep,
                     maxsplit=1) for dep in re.split("\n",
                                                     r.stdout)
        ]
        dependencies.pop()
        return {
            (
                dep[0][1 :-1],
                VersionConstraint.parse(dep[1] if len(dep) > 1 else ""))
            for dep in dependencies
        }
