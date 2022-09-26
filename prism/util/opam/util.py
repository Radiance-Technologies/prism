"""
Utility functions related to OPAM.
"""

from typing import Union

from .formula import PackageFormula
from .version import OCamlVersion, Version


def major_minor_version_bound(
        package: str,
        version: Union[str,
                       Version]) -> PackageFormula:
    """
    Create a constraint that matches a major and minor version.

    Parameters
    ----------
    package : str
        The name of an OCaml package.
    version : Union[str, Version]
        A version of the package.

    Returns
    -------
    PackageFormula
        If the `version` has major and minor components (i.e., it is an
        instance of `OCamlVersion`), then a package constraint bounding
        the version between the given major and minor components and the
        next minor release is returned.
        Otherwise, a formula requiring a simple exact version match is
        returned.
    """
    if isinstance(version, str):
        version = Version.parse(version)
    if isinstance(version, OCamlVersion):
        lower_bound = OCamlVersion(
            version.major,
            version.minor,
            prerelease=version.prerelease)
        upper_bound = OCamlVersion(version.major, int(version.minor) + 1)
        formula = PackageFormula.parse(
            f'"{package}" {{ >= "{lower_bound}" & < "{upper_bound}" }}')
    else:
        # "major" version not defined
        formula = PackageFormula.parse(f'"{package}.{version}"')
    return formula
