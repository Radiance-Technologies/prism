"""
Defines an interface for programmatically querying OPAM.
"""
import logging
import re
from dataclasses import dataclass
from typing import ClassVar, Dict, List, Optional

from seutil import bash

from .constraint import VersionConstraint
from .version import OCamlVersion, Version

logger = logging.getLogger(__file__)
logger.setLevel(logging.DEBUG)


@dataclass
class OpamAPI:
    """
    Provides methods for querying the OCaml package manager.

    Note that OPAM must be installed.

    .. warning::
        This class does not yet fully support the full expressivity of
        OPAM dependencies as documented at
        https://opam.ocaml.org/blog/opam-extended-dependencies/.
    """

    _whitespace_regex: ClassVar[re.Pattern] = re.compile(r"\s+")
    _newline_regex: ClassVar[re.Pattern] = re.compile("\n")
    _SWITCH_INSTALLED_ERROR = "[ERROR] There already is an installed switch named"

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
        # exploit fact that each dependency is on its own line in output
        dependencies: List[List[str]]
        dependencies = [
            cls._whitespace_regex.split(dep,
                                        maxsplit=1)
            for dep in cls._newline_regex.split(r.stdout)
        ]
        dependencies.pop()
        return {
            dep[0][1 :-1]:
            VersionConstraint.parse(dep[1] if len(dep) > 1 else "")
            for dep in dependencies
        }
