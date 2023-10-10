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
Utilities for working with Unicode, especially for regular expressions.
"""

import re
from typing import List, Tuple

import prism.interface.coq.unicode_table as UT

_special_regex_chars = {
    "(",
    ")",
    "[",
    "]",
    "*",
    "+",
    ".",
    "^",
    "$",
    "?",
    "{",
    "}",
    "\\",
    "|"
}


def chr_escape(code: int) -> str:
    """
    Encode the Unicode value and escape escape special characters.
    """
    code = chr(code)
    if code in _special_regex_chars:
        code = "\\" + code
    return code


def mk_regex_from_unicode_tables(
        *tables: Tuple[List[Tuple[int,
                                  int]],
                       ...]) -> re.Pattern:
    """
    Compile a regex that matches the characters in given Unicode tables.
    """
    options = ["["]
    for table in tables:
        for lb, ub in table:
            if lb != ub:
                option = f"{chr_escape(lb)}-{chr_escape(ub)}"
            else:
                option = chr_escape(lb)
            options.append(option)
    options.append("]")
    pattern = re.compile(''.join(options))
    return pattern


def single(code: int) -> Tuple[int, int]:
    """
    Make a pair from a single Unicode value.
    """
    return (code, code)


LETTER = mk_regex_from_unicode_tables(
    UT.lu,
    UT.ll,
    UT.lt,
    UT.lo,
    UT.lm,
    [(0x01D00,
      0x01D7F)],  # Phonetic Extensions.
    [(0x01D80,
      0x01DBF)],  # Phonetic Extensions Suppl.
    [(0x01DC0,
      0x01DFF)])  # Combining Diacritical Marks Suppl.

IDENTPART = mk_regex_from_unicode_tables(
    UT.nd,
    UT.nl,
    UT.no,
    [single(0x0027)],  # Single quote.
)

IDENTSEP = mk_regex_from_unicode_tables([
    single(0x005F),  # Underscore.
    single(0x00A0),  # Non breaking space, overrides Sep
])
