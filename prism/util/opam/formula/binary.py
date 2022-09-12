"""
Defines a generic class for binary relational formulas.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Generic, Tuple, Type, TypeVar, Union

from prism.util.parse import Parseable, ParseError

from .common import FormulaT, LogOp, RelOp

Op = TypeVar("Op", LogOp, RelOp)


@dataclass(frozen=True)
class Binary(Parseable, Generic[FormulaT, Op], ABC):
    """
    A binary operator applied to two formulae.
    """

    left: FormulaT
    op: Op
    right: FormulaT

    def __post_init__(self) -> None:
        """
        Apply operator precedence.

        Ensure conjunction has higher precedence than disjunction, and
        ensure relational operators have higher precedence than logical
        operators.
        """
        cls = type(self)
        left = self.left
        op = self.op
        right = self.right
        if isinstance(op, LogOp):
            if isinstance(left,
                          Binary) and (op == LogOp.AND or op == LogOp.OR
                                       and left.op == LogOp.OR):
                # A | B & C incorrectly represented as (A | B) & C
                # or
                # A & B & C inefficiently represented as (A & B) & C
                # or
                # A | B | C inefficiently represented as (A | B) | C
                # (less efficient short-circuiting during evaluations)
                # Pivot!
                object.__setattr__(self, 'left', left.left)
                object.__setattr__(self, 'op', left.op)
                object.__setattr__(self, 'right', cls(left.right, op, right))
                self.__post_init__()
            elif isinstance(
                    right,
                    Binary) and op == LogOp.AND and self.right.op == LogOp.OR:
                # A & B | C incorrectly represented as A & (B | C)
                # Pivot!
                object.__setattr__(self, 'left', cls(left, op, right.left))
                object.__setattr__(self, 'op', right.op)
                object.__setattr__(self, 'right', right.right)
                self.__post_init__()
        else:
            if isinstance(left, Binary) and isinstance(left.op, LogOp):
                # A <logop> B <relop> C incorrectly represented as
                # (A <logop> B) <relop> C
                # Pivot!
                # This object changes from Binary[FormulaT, RelOp] to
                # Binary[FormulaT, LogOp]
                object.__setattr__(self, 'left', left.left)
                object.__setattr__(self, 'op', left.op)
                object.__setattr__(self, 'right', cls(left.right, op, right))
                self.__post_init__()
            elif isinstance(right, Binary) and isinstance(right.op, LogOp):
                # A <relop> B <logop> C incorrectly represented as
                # A <relop> (B <logop> C)
                # Pivot!
                object.__setattr__(self, 'left', cls(left, op, right.left))
                object.__setattr__(self, 'op', right.op)
                object.__setattr__(self, 'right', right.right)
                # This object changes from Binary[FormulaT, RelOp] to
                # Binary[FormulaT, LogOp]
                self.__class__ = type(left)
                self.__post_init__()

    def __str__(self) -> str:  # noqa: D105
        return f"{self.left} {self.op} {self.right}"

    @abstractmethod
    def is_satisfied(
            self,
            *objects: Tuple[Any,
                            ...],
            **kwargs: Dict[str,
                           Any]) -> bool:
        """
        Evaluate and apply the binary relation to each formula.
        """
        ...

    @abstractmethod
    def simplify(
        self,
        *objects: Tuple[Any,
                        ...],
        **kwargs: Dict[str,
                       Any]) -> Union[bool,
                                      'Binary[FormulaT, Op]',
                                      FormulaT]:
        """
        Simplify the binary relation.
        """
        ...

    @classmethod
    def _chain_parse(cls,
                     input: str,
                     pos: int) -> Tuple['Binary[FormulaT, Op]',
                                        int]:
        """
        Parse a binary logical combination of package formulae.

        A logical combination matches the following grammar::

            <Binary> ::= <FormulaT> <Op> <FormulaT>
        """
        left, pos = cls.formula_type()._chain_parse(input, pos)
        pos = cls._lstrip(input, pos)
        try:
            op, pos = LogOp._chain_parse(input, pos)
        except ParseError:
            op, pos = RelOp._chain_parse(input, pos)
        pos = cls._lstrip(input, pos)
        right, pos = cls.formula_type()._chain_parse(input, pos)
        return cls(left, op, right), pos

    @classmethod
    @abstractmethod
    def formula_type(cls) -> Type[FormulaT]:
        """
        Get the type of logical formula.
        """
        ...
