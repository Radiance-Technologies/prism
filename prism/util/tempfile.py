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
Utilities for creation of temporary files.
"""
import os
import tempfile
from typing import BinaryIO, TextIO


def PermissiveNamedTemporaryFile(*args, **kwargs) -> TextIO | BinaryIO:
    """
    Get a named temporary file with the current default permissions.

    Notes
    -----
    Temporary files are usually only created with only read and write
    permissions for the owner of the file.
    This function allows one to create temporary files that can be
    shared with a group without subsequent manual intervention.
    """
    f = tempfile.NamedTemporaryFile(*args, **kwargs)
    # Must set umask to get umask (octal).
    # Do not use 0 like pip does for security reasons
    # (https://github.com/pypa/pip/blob/38a8fb1f601c782eef0988290f11aa2a4dfc3c69/src/pip/_internal/utils/unpacking.py#L43).
    # See https://bugs.python.org/issue21082 for explanation.
    umask = os.umask(0o666)
    # reset umask
    os.umask(umask)
    # Change permissions of tempfile
    os.chmod(f.name, 0o666 & ~umask)
    return f
