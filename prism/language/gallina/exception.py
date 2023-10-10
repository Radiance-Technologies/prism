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
Defines exceptions related to Gallina and its parsing or analysis.

Adapted from `roosterize.parser.SexpAnalyzer`
at https://github.com/EngineeringSoftware/roosterize/.
"""

from typing import Tuple, Union

from prism.language.sexp.node import SexpNode


class SexpAnalyzingException(Exception):
    """
    For representing errors thrown during Gallina s-expression analysis.
    """

    def __init__(self, sexp: SexpNode, message: str = ""):
        self.sexp = sexp
        self.message = message

    def __reduce__(self) -> Union[str, Tuple[SexpNode, str]]:  # noqa: D105
        return SexpAnalyzingException, (self.sexp, self.message)

    def __str__(self):  # noqa: D105
        return f"{self.message}\nin sexp: {self.sexp.pretty_format()}"
