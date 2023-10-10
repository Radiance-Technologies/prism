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
Subpackage for utilities related to the original os package.
"""

import os
from contextlib import contextmanager
from typing import Generator

from prism.util.radpytools import PathLike


@contextmanager
def pushd(dir: PathLike) -> Generator[None, None, None]:
    """
    Temporarily change directories for the duration of the context.

    Mimics the behavior of a ``pushd`` command followed by a ``popd``
    command at context conclusion

    Parameters
    ----------
    dir : os.PathLike
        The new directory to push onto the stack.

    Examples
    --------
    >>> from pathlib import Path
    >>> os.chdir(Path.home())
    >>> with pushd("/etc"):
    ...     print(os.getcwd())
    ...
    /etc
    >>> print(os.getcwd()) # your home directory
    """
    current_dir = os.getcwd()
    os.chdir(dir)
    try:
        yield
    finally:
        os.chdir(current_dir)
