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
Utilities for working with dataclasses.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    Protocol,
    Type,
    TypeVar,
    runtime_checkable,
)

_T = TypeVar('_T')


@runtime_checkable
class Dataclass(Protocol):
    """
    A basic protocol for type-checking dataclasses.
    """

    __dataclass_fields__: ClassVar[Dict[str, Any]]


def default_field(obj: _T, **kwargs) -> _T:
    r"""
    Specify the default value of a dataclass field.

    Parameters
    ----------
    obj : T
        A mutable default value.

    Returns
    -------
    Field
        An object representing the dataclass field.

    Examples
    --------
    >>> @dataclass
    ... class Example:
    ...     example: List[int] = []
    ...
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
      File "...\lib\dataclasses.py", line 1010, in dataclass
        return wrap(_cls)
      ...
      File "...\lib\dataclasses.py", line 733, in _get_field
        raise ValueError(f'mutable default {type(f.default)} for field '
    ValueError: mutable default <class 'list'> for field example ...
    >>> @dataclass
    ... class Example:
    ...     example: List[int] = default_field([])
    ...
    >>> a = Example()
    >>> b = Example()
    >>> assert id(a.example) != id(b.example)
    """
    return field(default_factory=lambda: deepcopy(obj), **kwargs)


def immutable_dataclass(*args, **kwargs) -> Callable[[Type[_T]], Type[_T]]:
    """
    Make an immutable, hashable dataclass.

    A wrapper around the dataclass decorator to be used in its place.

    Examples
    --------
    >>> @immutable_dataclass
    ... class Example:
    ...     example: int
    ...
    >>> ex = Example(0)
    >>> hash(ex)
    3430018387555
    >>> ex.example = 5
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
      File "<string>", line 4, in __setattr__
    dataclasses.FrozenInstanceError: cannot assign to field 'example'
    """
    kwargs.update({
        'frozen': True,
        'eq': True
    })
    return dataclass(*args, **kwargs)
