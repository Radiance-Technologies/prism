#
# Copyright (c) 2023 Radiance Technologies, Inc.
#
# This file is part of PRISM
# (see https://github.com/orgs/Radiance-Technologies/prism).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program. If not, see
# <http://www.gnu.org/licenses/>.
#
"""
Utility functions related to OPAM.
"""

import typing
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
    return typing.cast(PackageFormula, formula)
