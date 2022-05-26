"""
Provides utilities for working with OCaml package constraints.
"""

import re
from bisect import bisect, bisect_left
from dataclasses import dataclass
from typing import ClassVar, Iterable, List, Optional, Sequence

from prism.util.compare import Bottom, Top

from .version import OCamlVersion, Version


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

    def apply(self,
              versions: Iterable[Version],
              sort: bool = False) -> List[Version]:
        """
        Get versions satisfying the constraint from a collection.

        The collection must be sorted

        Parameters
        ----------
        versions : Iterable[Version]
            A collection of versions. If an iteration over the
            collection will not yield the versions in a sorted,
            ascending order, then the `sort` argument should be enabled.
        sort : bool, optional
            Whether to sort the given collection (True) or not (False),
            by default False.

        Returns
        -------
        feasible : List[Version]
            The feasible set of versions in ascending order.
        """
        if sort:
            versions = sorted(versions)
        if not isinstance(versions, Sequence):
            versions = list(versions)
        first_idx, last_idx = 0, len(versions)
        if self.lower_bound is not None:
            bisection = bisect_left if self.lower_closed else bisect
            first_idx = bisection(versions, self.lower_bound)
            if self.upper_bound is not None:
                bisection = bisect if self.upper_closed else bisect_left
                last_idx = bisection(versions, self.upper_bound)
        elif self.upper_bound is not None:
            bisection = bisect if self.upper_closed else bisect_left
            last_idx = bisection(versions, self.upper_bound)
        return versions[first_idx : last_idx]

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
