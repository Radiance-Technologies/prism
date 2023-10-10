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
Utilities for regular expressions.
"""
import re
from typing import Iterable, Union


def regex_from_options(
        options: Iterable[str],
        must_start: bool,
        must_end: bool,
        group: bool = False,
        compile: bool = True,
        flags: Union[int,
                     re.RegexFlag] = 0) -> re.Pattern:
    """
    Make a regular expression for matching mutually exclusive options.

    Parameters
    ----------
    options : Iterable[str]
        The options to match.
    must_start : bool
        Whether the match must appear at the start of the string.
    must_end : bool
        Whether the match must appear at the end of the string.
    group : bool, optional
        Whether to capture the options as a group, by default False
    compile : bool, optional
        Whether to compile the regular expression before returning or
        not, by default True.
    flags : Union[int, re.RegexFlag], optional
        Flags to pass when `compile` is True.

    Returns
    -------
    re.Pattern
        The regular expression.
    """
    regex = '|'.join(options)
    if group:
        regex = f"({regex})"
    else:
        regex = f"(?:{regex})"
    regex = f"{'^' if must_start else ''}{regex}{'$' if must_end else ''}"
    if compile:
        regex = re.compile(regex, flags=flags)
    return regex
