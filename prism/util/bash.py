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
Miscellaneous Bash-related utilities.
"""
from prism.util.iterable import CallableIterator
from prism.util.re import re

_escape_regex = re.compile('(["\'\\\\\b\f\t\n\r\v\a])')


def escape(cmd: str) -> str:
    """
    Sanitize the given Bash command by escaping special characters.

    Parameters
    ----------
    cmd : str
        A command intended as an argument in a Bash script or command.

    Returns
    -------
    str
        The sanitized command.
    """
    matches = _escape_regex.finditer(cmd)
    replacements = [rf"\{m[0]}" for m in matches]
    return _escape_regex.sub(CallableIterator(replacements),
                             cmd).replace("'",
                                          r"'\''")
