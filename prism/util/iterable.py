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
A collection of utilities for iterable containers.
"""

from bisect import bisect_left
from dataclasses import InitVar, dataclass, field, fields
from typing import (
    Any,
    Dict,
    Generic,
    Hashable,
    Iterable,
    Iterator,
    List,
    Sequence,
    Tuple,
    TypeVar,
    Union,
)

from prism.util.compare import Bottom, Comparable, Top
from prism.util.radpytools import unzip
from prism.util.radpytools.dataclasses import Dataclass

T = TypeVar('T')
C = TypeVar('C', bound=Comparable)
H = TypeVar('H', bound=Hashable)


@dataclass
class CallableIterator(Generic[T]):
    """
    A wrapper that makes the iterator of a collection callable.
    """

    it: Iterator[T] = field(init=False)
    collection: InitVar[Iterable[T]]

    def __post_init__(self, collection: Iterable[T]) -> None:  # noqa: D105
        self.it = iter(collection)

    def __call__(self, *args, **kwargs) -> T:
        """
        Advance the iterator.
        """
        return next(self.it)

    def __iter__(self) -> Iterator[T]:
        """
        Get the iterator.
        """
        return self.it


@dataclass
class CompareIterator(Generic[C]):
    """
    A wrapper that advances an iterator based on a comparison.
    """

    items: Sequence[C]
    """
    A presumably sorted sequence of items.
    """
    pointer: Union[Bottom, int, Top] = field(init=False)
    """
    An index into the sequence.
    """
    reverse: bool = False
    """
    Whether to iterate forwards or in reverse.
    """
    sort: InitVar[bool] = False
    """
    Whether to sort the given sequence or not, by default False.
    """

    def __post_init__(self, sort: bool) -> None:  # noqa: D105
        if sort:
            self.items = sorted(self.items)
        if self.reverse:
            self.pointer = len(self.items) - 1
        else:
            self.pointer = 0

    def __eq__(self, value: C) -> bool:
        """
        Compare and advance the pointer.
        """
        if self.pointer < 0:
            self.pointer = Bottom()
        elif self.pointer < len(self.items):
            if self.items[self.pointer] == value:
                if self.reverse:
                    self.pointer -= 1
                else:
                    self.pointer += 1
                return True
        else:
            self.pointer = Top()
        return False

    @property
    def next(self) -> Union[Bottom, C, Top]:
        """
        Get the next iteration item without advancing the iterator.
        """
        if self.pointer < 0:
            return Bottom()
        elif self.pointer < len(self.items):
            return self.items[self.pointer]
        else:
            return Top()

    def reversed(self) -> 'CompareIterator[C]':
        """
        Reverse the order of iteration at the current point.

        Returns
        -------
        CompareIterator[C]
            A comparison iterator whose orientation is reversed.
            If `self` is mid-iteration, the returned iterator will also
            be mid-iteration at the same index.
        """
        reversed_ptr = CompareIterator(self.items, not self.reverse)
        if self.reverse:
            reversed_ptr.pointer = max(self.pointer, reversed_ptr.pointer)
        else:
            reversed_ptr.pointer = min(self.pointer, reversed_ptr.pointer)
        return reversed_ptr

    @classmethod
    def next_among(cls, ptrs: Iterable['CompareIterator[C]']) -> C:
        """
        Get the next item among the given comparison iterators.

        None of the iterators are advanced.

        Parameters
        ----------
        ptrs : Iterable[CompareIterator[C]]
            A collection of comparison iterators with equal orientation.

        Returns
        -------
        C
            If the iterators are reverse-oriented, then the maximum of
            their next values.
            Otherwise, the minimum of the iterators' next values.

        Raises
        ------
        RuntimeError
            If each iterator does not possess the same orientation.
        """
        (nexts, reverses) = unzip([(ptr.next, ptr.reverse) for ptr in ptrs])
        reverse = reverses[0] if reverses else False
        if not all(r == reverses[0] for r in reverses):
            raise RuntimeError(
                "All iterators must be oriented in the same direction.")
        nexts.append(-1 if reverse else Top())
        return max(nexts) if reverse else min(nexts)


def fast_contains(seq: Sequence[C], value: C) -> bool:
    """
    Return whether the value is in the sequence in logarithmic time.

    Assumes that the sequence is sorted; otherwise the results are
    undefined.
    """
    insertion_index = bisect_left(seq, value)
    return insertion_index != len(seq) and seq[insertion_index] == value


def fast_index(seq: Sequence[C], value: C) -> int:
    """
    Return first index of value in logarithmic time complexity.

    Assumes that the sequence is sorted; otherwise the results are
    undefined.

    Raises
    ------
    ValueError
        If the value is not present
    """
    insertion_index = bisect_left(seq, value)
    if insertion_index == len(seq) or seq[insertion_index] != value:
        raise ValueError(f"{value} is not in sequence")
    return insertion_index


def unpack(dc: Dataclass) -> Tuple[Any, ...]:
    """
    Return tuple of dataclass field values.
    """
    return tuple(getattr(dc, field.name) for field in fields(dc))


def shallow_asdict(dc: Dataclass) -> Dict[str, Any]:
    """
    Non-recursively convert dataclass into dictionary.
    """
    return dict((field.name, getattr(dc, field.name)) for field in fields(dc))


def split(it: Sequence[T], n: int) -> Iterator[Sequence[T]]:
    """
    Split a sequence into `n` sequential subsequences.
    """
    if n == 0:
        return (_ for _ in range(0))
    k, m = divmod(len(it), n)
    return (it[i * k + min(i, m):(i + 1) * k + min(i + 1, m)] for i in range(n))


def uniquify(it: Iterable[H]) -> List[H]:
    """
    Remove duplicate elements but keep the original order of iteration.

    Parameters
    ----------
    it : Iterable[H]
        An iterable container.

    Returns
    -------
    List[H]
        A list containing the unique elements of `it` in the order of
        their appearance during iteration.
    """
    return list(dict.fromkeys(it).keys())
