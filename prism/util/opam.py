"""
Supplies utilities for querying OCaml package information.
"""

import abc
import re
from abc import abstractmethod
from dataclasses import dataclass
from functools import cached_property, total_ordering
from typing import ClassVar, Dict, List, Optional, Set, Tuple, Union

import seutil.bash as bash

from .compare import Bottom, Top


class VersionParseError(Exception):
    """
    Represents an error encountered during Ocaml version parsing.
    """

    pass


class VersionString(str):
    """
    Strings with a custom comparison that matches OPAM version ordering.
    """

    def __lt__(self, other: str) -> bool:
        """
        See https://opam.ocaml.org/doc/Manual.html#version-ordering.
        """
        if not isinstance(other, str):
            return super().__lt__(other)
        for a, b in zip(self, other):
            if a == b:
                continue
            if a == '~':
                return True
            elif a.isascii() and a.isalpha():
                if b == '~':
                    return False
                elif b.isascii() and b.isalpha():
                    return a < b
                else:
                    return True
            elif b == '~' or (b.isascii() and b.isalpha()):
                return False
            else:
                return a < b
        return len(a) < len(b)


@total_ordering
class Version(abc.ABC):
    """
    An abstract base class for OCaml package versions.
    """

    def __lt__(self, other: 'Version') -> bool:  # noqa: D105
        if not isinstance(other, Version):
            return NotImplemented
        return self.key < other.key

    @abstractmethod
    def key(self) -> Tuple[Union[VersionString, int]]:
        """
        Get a key by which versions may be compared.

        Returns
        -------
        Tuple[Union[VersionString, int]]
            A key that can be compared lexicographically to determine if
            one version supercedes another.
        """
        ...

    @classmethod
    @abstractmethod
    def parse(cls, version: str) -> 'Version':
        """
        Parse the version from a string.

        Raises
        ------
        VersionParseError
            If a version cannot be parsed from the given string.
        """
        ...


@dataclass(frozen=True)
class OpamVersion:
    """
    Version specifiers according to the OCaml package manager.

    Implementation based on ``src/core/opamVersionCompare.ml`` and
    ``src/core/opamVersion.ml`` available at
    https://github.com/ocaml/opam.
    See https://opam.ocaml.org/doc/Manual.html#version-ordering for more
    information.
    """

    fields: List[Union[VersionString, str]]
    """
    Alternating sequence of non-digit/digit sequences, always starting
    with a non-digit sequence even if empty.
    """
    _version_syntax: ClassVar[re.Pattern] = re.compile(
        r"^[a-zA-Z0-9\-_\+\.~]+$")
    _sequence_syntax: ClassVar[re.Pattern] = re.compile(r"([^0-9]+)?([0-9]+)")

    def __post_init__(self):
        """
        Clean up digits by converting int to str.
        """
        for i, f in enumerate(self.fields):
            if isinstance(f, int):
                self.fields[i] = str(f)

    def __lt__(self, other: Version) -> bool:  # noqa: D105
        if not isinstance(other, Version):
            return NotImplemented
        return self.key < other.key

    def __str__(self) -> str:  # noqa: D105
        return ''.join([str(f) for f in self.fields])

    @cached_property
    def key(self) -> Tuple[Union[VersionString, int]]:  # noqa: D102
        return tuple(
            f if isinstance(f,
                            VersionString) else int(f) for f in self.fields)

    @classmethod
    def parse(cls, version: str) -> Version:  # noqa: D102
        if cls._version_syntax.match(version) is None:
            raise VersionParseError(f"Failed to parse version from {version}")

        sequence = [f for f in cls._sequence_syntax.split(version) if f]
        fields = []
        # make sure we start with a non-digit
        nondigit = True
        if sequence[0].isdigit():
            fields.append("")
            nondigit = False
        for field in sequence:
            field = VersionString(field) if nondigit else field
            fields.append(field)
            nondigit = not nondigit
        return OpamVersion(fields)


@dataclass(frozen=True)
class OCamlVersion(Version):
    """
    An OCaml compiler version.

    Version semantics are derived from
    https://github.com/ocurrent/ocaml-version.
    """

    major: str
    minor: str
    patch: Optional[str] = None
    prerelease: Optional[str] = None
    extra: Optional[str] = None
    _version_syntax: ClassVar[re.Pattern] = re.compile(
        r"^(\d+).(\d+)(\.\d+)?(([+~])(.*))?$")

    def __post_init__(self):
        """
        Clean up major, minor, and patch by converting int to str.
        """
        if isinstance(self.major, int):
            super().__setattr__('major', str(self.major))
        if isinstance(self.minor, int):
            super().__setattr__('minor', str(self.minor))
        if isinstance(self.patch, int):
            super().__setattr__('patch', str(self.patch))

    def __lt__(self, other: Version) -> bool:  # noqa: D105
        if not isinstance(other, Version):
            return NotImplemented
        elif isinstance(other, OCamlVersion):
            return self.fast_key < other.fast_key
        else:
            return self.key < other.key

    def __str__(self) -> str:
        """
        Pretty-print the version.
        """
        patch = "" if self.patch is None else f".{self.patch}"
        prerelease = "" if self.prerelease is None else f"~{self.prerelease}"
        extra = "" if self.extra is None else f"+{self.extra}"
        return f"{self.major}.{self.minor}{patch}{prerelease}{extra}"

    @cached_property
    def fast_key(
        self
    ) -> Tuple[int,
               int,
               Union[Bottom,
                     int],
               Union[Top,
                     str],
               Union[Bottom,
                     str]]:
        """
        Get a key specialized to `OCamlVersion`s.

        See Also
        --------
        Version.key
        """
        return (
            int(self.major),
            int(self.minor),
            Bottom() if self.patch is None else int(self.patch),
            # None > Some
            Top() if self.prerelease is None else self.prerelease,
            Bottom() if self.extra is None else self.extra)

    @cached_property
    def key(self) -> Tuple[Union[VersionString, int]]:  # noqa: D102
        return OpamVersion.parse(str(self)).key

    @classmethod
    def parse(cls, version: str) -> Version:  # noqa: D102
        prerelease = None
        try:
            (major,
             minor,
             patch,
             _,
             sep,
             extra) = cls._version_syntax.match(version).groups()
        except (TypeError, AttributeError):
            return OpamVersion.parse(version)
        if sep == "~":
            if extra is None:
                prerelease = ""
            else:
                try:
                    prerelease, extra = extra.split("+", maxsplit=1)
                except ValueError:
                    prerelease = extra
                    extra = None
        elif sep == "+" and extra is None:
            extra = ""
        if patch is not None:
            patch = patch[1 :]
        return OCamlVersion(major, minor, patch, prerelease, extra)


@dataclass(frozen=True)
class VersionConstraint:
    """
    An OCaml package version constraint.

    Currently only simple constraints are supported, namely logical
    conjunction (i.e., and) of at most two versions, which is expected
    to cover the majority of encountered constraints.
    """

    lower_bound: Optional[Version] = None
    upper_bound: Optional[Version] = None
    lower_closed: bool = False
    upper_closed: bool = False
    _brace_re: ClassVar[re.Pattern] = re.compile(r"\{|\}|\||\"")

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
        if (self.lower_bound == self.upper_bound
                and self.lower_bound is not None and self.lower_closed
                and self.upper_closed):
            return f"= {self.lower_bound}"
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
        constraint = cls._brace_re.sub("", constraint).split(" ")
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
            lower_bound = OCamlVersion.parse(lower_bound)
        if upper_bound is not None:
            upper_bound = OCamlVersion.parse(upper_bound)
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
    def get_available_versions(cls, pkg: str) -> List[Version]:
        """
        Get a list of available versions of the requested package.

        Parameters
        ----------
        pkg : str
            The name of a package.

        Returns
        -------
        List[Version]
            The list of available versions of `pkg`.
        """
        r = bash.run(f"opam show -f all-versions {pkg}")
        r.check_returncode()
        versions = re.split(r"\s+", r.stdout)
        versions.pop()
        return [OCamlVersion.parse(v) for v in versions]

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
            dep[0][1 :-1]:
            VersionConstraint.parse(dep[1] if len(dep) > 1 else "")
            for dep in dependencies
        }
