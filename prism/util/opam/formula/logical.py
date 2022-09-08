"""
Defines a generic class for conjunctive and disjunctive formulas.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import partialmethod
from typing import (
    Any,
    Dict,
    Generic,
    Iterator,
    List,
    Optional,
    Tuple,
    Type,
    Union,
)

from prism.util.parse import Parseable

from .common import FormulaT, LogOp


@dataclass(frozen=True)
class Logical(Parseable, Generic[FormulaT], ABC):
    """
    A logical combination of two version formulae.
    """

    left: FormulaT
    logop: LogOp
    right: FormulaT

    def __post_init__(self) -> None:
        """
        Ensure conjunction has higher precedence than disjunction.
        """
        cls = type(self)
        left = self.left
        logop = self.logop
        right = self.right
        if isinstance(left,
                      Logical) and (logop == LogOp.AND or logop == LogOp.OR
                                    and left.logop == LogOp.OR):
            # A | B & C incorrectly represented as (A | B) & C
            # or
            # A & B & C inefficiently represented as (A & B) & C
            # or
            # A | B | C inefficiently represented as (A | B) | C
            # (less efficient short-circuiting during evaluations)
            # Pivot!
            object.__setattr__(self, 'left', left.left)
            object.__setattr__(self, 'logop', left.logop)
            object.__setattr__(self, 'right', cls(left.right, logop, right))
            self.__post_init__()
        elif isinstance(
                right,
                Logical
        ) and self.logop == LogOp.AND and self.right.logop == LogOp.OR:
            # A & B | C incorrectly represented as A & (B | C)
            # Pivot!
            object.__setattr__(self, 'left', cls(left, logop, right.left))
            object.__setattr__(self, 'logop', right.logop)
            object.__setattr__(self, 'right', right.right)
            self.__post_init__()

    def __iter__(self) -> Iterator['FormulaT']:
        """
        Iterate over the clauses of the conjunctive phrase.
        """
        yield from self.to_conjunctive_list()

    def __str__(self) -> str:  # noqa: D105
        return f"{self.left} {self.logop} {self.right}"

    def _to_list(
        self,
        op: LogOp,
        preceding: Optional[List['Logical[FormulaT]']] = None
    ) -> List['Logical[FormulaT]']:
        """
        Return an equivalent list implicitly joined by `LogOp`s.

        See Also
        --------
        to_conjunctive_list, to_disjunctive_list : For public APIs.
        """
        if preceding is None:
            preceding = []
        if self.logop == op:
            # by construction, there will not be any AND clauses to the
            # left
            preceding.append(self.left)
            if isinstance(self.right, Logical):
                self.right._to_list(op, preceding)
            else:
                preceding.append(self.right)
        return preceding

    def is_satisfied(
            self,
            *objects: Tuple[Any,
                            ...],
            **kwargs: Dict[str,
                           Any]) -> bool:
        """
        Perform logical conjunction/disjunction on the paired formulae.
        """
        if self.left.is_satisfied(*objects, **kwargs):
            return self.logop == LogOp.OR or self.right.is_satisfied(
                *objects,
                **kwargs)
        else:
            return self.logop == LogOp.OR and self.right.is_satisfied(
                *objects,
                **kwargs)

    def simplify(
            self,
            *objects: Tuple[Any,
                            ...],
            **kwargs: Dict[str,
                           Any]) -> Union[bool,
                                          'Logical[FormulaT]',
                                          FormulaT]:
        """
        Simplify the logical conjunction/disjunction.
        """
        left_simplified = self.left.simplify(*objects, **kwargs)
        if isinstance(left_simplified, bool):
            if left_simplified:
                return self.logop == LogOp.OR or self.right.simplify(
                    *objects,
                    **kwargs)
            else:
                return self.logop == LogOp.OR and self.right.simplify(
                    *objects,
                    **kwargs)
        else:
            right_simplified = self.right.simplify(*objects, **kwargs)
            if isinstance(right_simplified, bool):
                if right_simplified:
                    return self.logop == LogOp.OR or left_simplified
                else:
                    return self.logop == LogOp.OR and left_simplified
            else:
                return type(self)(left_simplified, self.logop, right_simplified)

    to_conjunctive_list = partialmethod(_to_list, op=LogOp.AND)
    """
    Return an equivalent list implicitly joined by AND operators.

    Parameters
    ----------
    conjunctives : Optional[List['Logical[FormulaT]']], optional
        A preceding list of formulas, by default None.
        The list is modified in-place.

    Returns
    -------
    List['Logical[FormulaT]']
        The list of implicitly joined formulas.
        If `conjunctives` was provided, then it is returned.
    """

    to_disjunctive_list = partialmethod(_to_list, op=LogOp.OR)
    """
    Return an equivalent list implicitly joined by OR operators.

    Parameters
    ----------
    disjunctives : Optional[List['Logical[FormulaT]']], optional
        A preceding list of formulas, by default None.
        The list is modified in-place.

    Returns
    -------
    List['Logical[FormulaT]']
        The list of implicitly joined formulas.
        If `disjunctives` was provided, then it is returned.
    """

    @classmethod
    def _chain_parse(cls,
                     input: str,
                     pos: int) -> Tuple['Logical[FormulaT]',
                                        int]:
        """
        Parse a binary logical combination of package formulae.

        A logical combination matches the following grammar::

            <Logical> ::= <Formula> <LogOp> <Formula>
        """
        left, pos = cls.formula_type()._chain_parse(input, pos)
        pos = cls._lstrip(input, pos)
        logop, pos = LogOp._chain_parse(input, pos)
        pos = cls._lstrip(input, pos)
        right, pos = cls.formula_type()._chain_parse(input, pos)
        return cls(left, logop, right), pos

    @classmethod
    @abstractmethod
    def formula_type(cls) -> Type[FormulaT]:
        """
        Get the type of logical formula.
        """
        ...
