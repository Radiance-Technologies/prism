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
Utilities related to system/shell environments.
"""
import os
import typing
from itertools import chain
from typing import Dict, List, Tuple, Union

import numba.typed

from prism.util.alignment import Alignment, align_factory

path_align = align_factory(
    lambda x,
    y: 0. if x == y else 1.,
    # Skip cost is less than half the cost of misalignment to encourage
    # skipping.
    lambda x: 0.25,
    True)
"""
Align two sequences of paths.
"""


def merge_path(a: str, b: str) -> str:
    """
    Merge two PATH environment variables.

    The PATHs are zipped together, taking into account the relative
    order of each.
    Paths in `b` are favored to appear before paths in `a` when there
    would be ambiguity in the order otherwise.

    Parameters
    ----------
    a, b : str
        PATH environment variables.

    Returns
    -------
    str
        The union of `a` and `b` as another valid PATH environment
        variable.
    """
    a_paths = a.split(os.pathsep)
    b_paths = b.split(os.pathsep)
    alignment = typing.cast(
        Alignment,
        path_align(numba.typed.List(a_paths),
                   numba.typed.List(b_paths),
                   False))
    components: List[Union[str, Tuple[List[str], List[str]]]] = []
    for a_path, b_path in alignment:
        if a_path is None or b_path is None:
            if not components or isinstance(components[-1], str):
                components.append(([], []))
            if a_path is None:
                assert b_path is not None
                typing.cast(list, components[-1][1]).append(b_path)
            else:
                assert a_path is not None
                typing.cast(list, components[-1][0]).append(a_path)
        else:
            assert a_path is not None and b_path is not None
            assert a_path == b_path
            components.append(a_path)
    paths = list(
        chain.from_iterable(
            [[c] if isinstance(c,
                               str) else c[1] + c[0] for c in components]))
    return os.pathsep.join(paths)


def merge_environments(a: Dict[str, str], b: Dict[str, str]) -> Dict[str, str]:
    """
    Take the union of two environments, taking care to merge PATHs.

    The latter environment overrides the former in cases where they both
    define the same variable.
    """
    result = a | b
    if 'PATH' in a and 'PATH' in b:
        result['PATH'] = merge_path(a['PATH'], b['PATH'])
    return result
