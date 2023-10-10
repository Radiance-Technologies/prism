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
Supplies utilities for querying OCaml package information.
"""

from .api import OpamAPI  # noqa: F401
from .formula import (  # noqa: F401
    AssignedVariables,
    PackageFormula,
    Variable,
    VersionFormula,
)
from .switch import OpamSwitch  # noqa: F401
from .util import major_minor_version_bound  # noqa: F401
from .version import (  # noqa: F401
    OCamlVersion,
    OpamVersion,
    ParseError,
    Version,
)
