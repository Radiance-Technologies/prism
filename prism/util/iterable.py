"""
A collection of utilities for iterable containers.
"""

from dataclasses import InitVar, dataclass, field
from typing import Generic, Iterable, Iterator, Sequence, TypeVar, Union

from radpytools import unzip

from prism.util.compare import Bottom, Comparable, Top

T = TypeVar('T')
C = TypeVar('C', bound=Comparable)


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
