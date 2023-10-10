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
Expose faster C versions of PyYAML encoding/decoding functions.
"""

import yaml


def safe_dump(data: object, stream=None, **kwargs) -> str:
    """
    Safely dump a Python object to a string.

    See Also
    --------
    yaml.safe_dump
    """
    return yaml.dump_all([data], stream, Dumper=yaml.CSafeDumper, **kwargs)


def safe_load(stream):
    """
    Safely load potentially untrusted input from a stream.

    See Also
    --------
    yaml.safe_load
    """
    return yaml.load(stream, yaml.CSafeLoader)
