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
System path utilities.
"""
from pathlib import Path
from typing import Sequence

from prism.util.radpytools import PathLike


def get_relative_path(path: PathLike, other: PathLike) -> Path:
    """
    Return the relative path of one path to another.
    """
    path = Path(path).resolve()
    try:
        return path.relative_to(other)
    except ValueError:
        # target does not start with origin
        other = Path(other)
        if other.parts:
            return ".." / get_relative_path(path, other.parent)
        else:
            # other is the system root
            return path


def without_suffixes(path: PathLike) -> Path:
    """
    Remove all suffixes (extensions) from a path.
    """
    path = Path(path)
    while True:
        without = path.with_suffix('')
        if without == path:
            break
        path = without
    return without


def with_suffixes(path: PathLike, suffixes: Sequence[str]) -> Path:
    """
    Replace the suffixes of a path with those given.
    """
    path = without_suffixes(path)
    return path.with_suffix(''.join(suffixes))


def pop_suffix(path: PathLike) -> Path:
    """
    Remove the last suffix of the given path if it has any.
    """
    return Path(path).with_suffix('')


def append_suffix(path: PathLike, suffix: str) -> Path:
    """
    Add a new suffix to the end of the path.
    """
    suffixes = Path(path).suffixes
    suffixes.append(suffix)
    return with_suffixes(path, suffixes)
