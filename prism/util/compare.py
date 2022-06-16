"""
Defines utilities for comparisons.
"""
from abc import ABC, abstractmethod
from functools import total_ordering
from types import MethodType
from typing import Any, Callable, List, Protocol, runtime_checkable


@total_ordering
class Bottom:
    """
    A value that is less than any other.

    A generalization of negative infinity to any type.
    """

    def __eq__(self, other: Any) -> bool:  # noqa: D105
        if isinstance(other, Bottom):
            return True
        else:
            return False

    def __gt__(self, _: Any) -> bool:  # noqa: D105
        return False


@runtime_checkable
class Comparable(Protocol):
    """
    A protocol for comparable objects.

    This class can be used with `isinstance` checks and ensures
    compatibility with builtin functions based on comparisons, which
    exclusively use the less-than operator.
    """

    def __lt__(self, other: Any) -> bool:  # noqa: D105
        ...


@total_ordering
class Top:
    """
    A value that is greater than any other.

    A generalization of positive infinity to any type.
    """

    def __eq__(self, other: Any) -> bool:  # noqa: D105
        if isinstance(other, Top):
            return True
        else:
            return False

    def __lt__(self, _: Any) -> bool:  # noqa: D105
        return False


class Criteria(ABC, Callable):
    """
    A helper for constructing criteria functions.
    """

    def __init__(self, evaluate=None):
        self.buffer = {}
        if evaluate is not None:
            self.evaluate = MethodType(evaluate, self.__class__, self.__class__)

    def __and__(self, other) -> 'Criteria':
        """
        Combine two criteria function through AND gate.
        """
        if not isinstance(other, (list, tuple)):
            criteria = [self, other]
        else:
            criteria = [self] + list(other)

        def reduction(criteria_outputs):
            output = criteria_output.pop(0)
            for criteria_output in criteria_outputs:
                output &= criteria_output
            return output

        return self.chain(reduction, *criteria)

    def __call__(self, *args, **kwargs) -> bool:
        """
        Call the criteria evaluation function on arguments.
        """
        return self.evaluate(*args, **kwargs)

    def __enter__(self):
        """
        Create new buffer on entering context.
        """
        setattr(self, "_old_buffer", self.buffer)
        self.buffer = {}

    def __exit__(self, exc_type, exc_value, exc_traceback):
        """
        Delete the temporary buffer and replace it original value.
        """
        self.buffer = self._old_buffer
        delattr(self, "_old_buffer")

    def __or__(self, other) -> 'Criteria':
        """
        Combine two criteria function through OR gate.
        """
        if not isinstance(other, (list, tuple)):
            criteria = [self, other]
        else:
            criteria = [self] + list(other)

        def reduction(criteria_outputs):
            output = criteria_output.pop(0)
            for criteria_output in criteria_outputs:
                output |= criteria_output
            return output

        return self.chain(reduction, *criteria)

    def __xor__(self, other) -> 'Criteria':
        """
        Combine two criteria function through XOR gate.
        """
        if not isinstance(other, (list, tuple)):
            criteria = [self, other]
        else:
            criteria = [self] + list(other)

        def reduction(criteria_outputs):
            output = criteria_output.pop(0)
            for criteria_output in criteria_outputs:
                output ^= criteria_output
            return output

        return self.chain(reduction, *criteria)

    @abstractmethod
    def evaluate(self, *args, **kwargs) -> bool:
        """
        Compute the criteria on the arguments.
        """
        pass

    @classmethod
    def chain(
            cls,
            reduction: Callable[[List[bool]],
                                bool],
            *group_of_criteria,
            join_buffers: bool = True) -> 'Criteria':
        """
        Chain multiple crtieria into a single criteria.

        Parameters
        ----------
        reduction : Callable[[List[bool]], bool]
            Perform the reduction on output of all certeria outputs.
        join_buffers : bool, optional
            Use union of all criteria buffers when evaluating any criteria,
            otherwise use criteria's original buffer, by default True

        Returns
        -------
        Criteria
            A set of criteria coupled by a reduction operation.
        """
        group_of_criteria = [
            c if isinstance(c,
                            cls) else cls(c) for c in group_of_criteria
        ]
        if join_buffers:

            def evaluate(self, *args, **kwargs):
                output = []
                for criteria in group_of_criteria:
                    with criteria:
                        criteria.buffer = self.buffer
                        output.append(criteria(*args, **kwargs))
                return reduction(output)
        else:

            def evaluate(self, *args, **kwargs):
                output = []
                for criteria in group_of_criteria:
                    output.append(criteria(*args, **kwargs))
                return reduction(output)

        buffer = {k: v for c in group_of_criteria for k,
                  v in c.buffer.items()}
        criteria = Criteria(evaluate=evaluate)
        criteria.buffer = buffer
        return criteria
