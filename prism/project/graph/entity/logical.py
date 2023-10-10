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
Module for utilies for logical components of a dependency.
"""
from itertools import accumulate
from pathlib import Path
from typing import Generator, List, Sequence, Tuple


def logical_iter(logical: str):
    """
    Iterate over accumulation of logical segments.
    """
    logical_parts = logical.split('.')
    for logical_ in accumulate(logical_parts, lambda *parts: '.'.join(parts)):
        yield logical_


class _LogicalParents(Sequence):
    """
    Object that provides sequence-like access to logical ancestors.

    Useful if the logical path is long and not all parents are needed
    """

    __slots__ = ('_logicalcls', '_parts')

    def __init__(self, logical_name):
        # We don't store the instance to avoid reference cycles
        self._logicalcls = type(logical_name)
        self._parts = logical_name._parts

    def __len__(self):
        """
        Return number of parents.
        """
        return len(self._parts) - 1

    def __getitem__(self, idx: int):
        """
        Return the `idx`th parent.
        """
        if idx < 0 or idx >= len(self):
            raise IndexError(idx)
        return self._logicalcls(*self._parts[:-idx - 1], parsed=True)

    def __repr__(self):
        """
        Return string representation of logical parents.
        """
        return "<{}.parents>".format(self._logicalcls.__name__)


class _LogicalShortNames(Sequence):
    """
    Object that provides sequence-like access to logical ancestors.
    """

    __slots__ = ('_logicalcls', '_parts')

    def __init__(self, logical_name):
        # We don't store the instance to avoid reference cycles
        self._logicalcls = type(logical_name)
        self._parts = logical_name._parts

    def __len__(self):
        """
        Return number of shortnames.
        """
        return len(self._parts)

    def __getitem__(self, idx):
        """
        Return the `idx`th shortname.
        """
        n = len(self)
        if idx < 0 or idx >= n:
            raise IndexError(idx)
        return self._logicalcls(*self._parts[n - idx - 1 :], parsed=True)

    def __repr__(self):
        """
        Return string representation of logical shortnames.
        """
        return "<{}.shortnames>".format(self._logicalcls.__name__)


class LogicalName(str):
    """
    A string that is used as a identifier for module/compiled library.
    """

    def __new__(cls, *args, parsed: bool = False, level=None):
        """
        Construct logical name from parts.

        The strings and path objects are combined so as to yield a
        canonicalized path, which is incorporated into the new PurePath
        object.
        """
        if not parsed:
            args = cls._parse_args(args)
        name = '.'.join(args)
        return str.__new__(cls, name)

    def __init__(self, *arg, parsed=None, level: int = None):
        """
        Initialize logical name.
        """
        if not isinstance(arg, str):
            arg = '.'.join(arg)
        parts = tuple(arg.split('.'))
        self._parts = parts
        self._path_like = Path(*parts)
        self._level = level

    @property
    def level(self) -> int:
        """
        Level of a logical name nested in logical name.
        """
        return self._level

    @property
    def parts(self) -> Tuple[str]:
        """
        Return logical name split by '.'.
        """
        return self._parts

    @property
    def path_like(self) -> Path:
        """
        Return logical name reformatted as a path.
        """
        return self._path_like

    @property
    def parent(self) -> 'LogicalName':
        """
        Return logical name containing this instance minux the tail.
        """
        parts = self._parts[0 :-1]
        parent = self.join(*parts, parsed=True) if self.level else None
        return parent

    @property
    def parents(self):
        """
        Return iterator over parents.
        """
        return _LogicalParents(self)

    @property
    def root_to_stem_generator(self) -> Generator['LogicalName', None, None]:
        """
        Return iterator over parents and self.
        """
        for parent in self.parents:
            yield LogicalName(parent)
        yield self

    @property
    def shortnames(self) -> _LogicalShortNames:
        """
        Return valid, shorter logical names that alias self.

        Returns
        -------
        _LogicalShortNames
            An iterator of shortnames that only constructs the shortname
            at the time it's needed.
        """
        return _LogicalShortNames(self)

    @property
    def stem(self) -> str:
        """
        Return final part of logical name.

        Returns
        -------
        str
            value after the last '.' in a logical name.
        """
        return self._parts[-1]

    @property
    def stem_to_root_generator(self) -> Generator['LogicalName', None, None]:
        """
        Generate shortnames in order followed by full logical name.

        Yields
        ------
        LogicalName
            The original logical name or one of it's shortnames.
        """
        for shortname in self.shortnames:
            yield LogicalName(shortname)
        yield self

    def is_relative_to(self, other: 'LogicalName') -> bool:
        """
        Return True if ``other`` contains this instance as a tail.

        Parameters
        ----------
        other : LogicalName
            Another logical name instance.

        Returns
        -------
        bool
            True if this instance matches the tail end of the other
            logical name.
        """
        return self.path_like.is_relative_to(other.path_like)

    def relative_to(self, other: 'LogicalName') -> 'LogicalName':
        """
        Return a LogicalName that removes other as a prefix of this.

        Parameters
        ----------
        other : LogicalName
            A logical name that is a prefix of this instance.

        Returns
        -------
        LogicalName
            A LogicalName contains the tail end of this instance
            but not the head end of other.

        Raises
        ------
        ValueError
            This instance is not relative to other.
        """
        if not self.is_relative_to(other):
            raise ValueError(f"{self} is not in the subpath of {other}")
        return self._from_parsed_parts(self.parts[len(other.parts):])

    @classmethod
    def _parse_args(cls, args) -> List[str]:
        """
        Parse arguments passed at initialization.

        This method serves to flatten tuple of strings that might
        consist of multiple parts already, or are already LogicalNames.

        Parameters
        ----------
        args : _type_
            Arguments passed at initialization.

        Returns
        -------
        List[str]
            List of individual parts that will compose
            the generated LogicalNAme

        Raises
        ------
        TypeError
            One of the arguments was not a str, LogicalName,
            or a tuple (or list) of those types.
        """
        # This is useful when you don't want to create an instance, just
        # canonicalize some constructor arguments.
        if isinstance(args, str):
            args = (args,
                    )
        stack = list(args)
        parts = ()
        while len(stack) > 0:
            part = str(stack.pop(0))
            if isinstance(part, LogicalName):
                parts += part.parts
            elif '.' in part:
                stack = part.split('.') + stack
            elif isinstance(part, tuple):
                stack = part + stack
            elif isinstance(part, str):
                parts += (part,
                          )
            else:
                raise TypeError(
                    "argument should be a str object or an LogicalName"
                    "object returning str, not %r" % type(part))
        return parts

    @classmethod
    def _from_parsed_parts(cls, parts: Sequence[str]) -> 'LogicalName':
        """
        Initialize from the output of ``_parse_args``.

        Parameters
        ----------
        parts : Sequence[str]
            _description_

        Returns
        -------
        LogicalName
            _description_
        """
        return cls(*parts, parsed=True)

    @classmethod
    def from_physical_path(cls, path: Path) -> 'LogicalName':
        """
        Convert a Path into a LogicalName.

        Parameters
        ----------
        path : Path
            A system file path.

        Returns
        -------
        LogicalName
            A logical name representing the system file path.
        """
        parts = list(path.parts)
        if parts[-1].endswith('.v'):
            parts[-1] = parts[-1].rstrip('.v')
        return cls(*parts)

    @classmethod
    def join(cls, *parts, parsed: bool = False):
        """
        Join the parts into a single string.
        """
        joined = cls(*parts, parsed=parsed)
        return joined
