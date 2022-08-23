"""
Defines a generic class for parenthetical formulas.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Generic, Tuple, Type, Union

from prism.util.parse import Parseable, ParseError

from .common import FormulaT


@dataclass(frozen=True)
class Parens(Parseable, Generic[FormulaT], ABC):
    """
    A parenthetical around a package formula.
    """

    formula: FormulaT

    def __str__(self) -> str:  # noqa: D105
        return f"({self.formula})"

    def is_satisfied(
            self,
            *objects: Tuple[Any,
                            ...],
            **kwargs: Dict[str,
                           Any]) -> bool:
        """
        Test whether the objects satisfy the internal formula.
        """
        return self.formula.is_satisfied(*objects, **kwargs)

    def simplify(
            self,
            *objects: Tuple[Any,
                            ...],
            **kwargs: Dict[str,
                           Any]) -> Union[bool,
                                          'Parens[FormulaT]',
                                          FormulaT]:
        """
        Simplify the internal formula.
        """
        formula_simplified = self.formula.simplify(*objects, **kwargs)
        if isinstance(formula_simplified, bool):
            return formula_simplified
        else:
            return type(self)(formula_simplified)

    @classmethod
    def _chain_parse(cls,
                     input: str,
                     pos: int) -> Tuple['Parens[FormulaT]',
                                        int]:
        """
        Parse a parenthesized version formula.

        A parenthesized formula has the following grammar::

            <ParensVF> ::= ( <VersionFormula> )
        """
        begpos = pos
        pos = cls._expect(input, pos, "(", begpos)
        pos = cls._lstrip(input, pos)
        try:
            formula, pos = cls.formula_type()._chain_parse(input, pos)
        except IndexError:
            raise ParseError(cls, input[begpos :])
        pos = cls._lstrip(input, pos)
        pos = cls._expect(input, pos, ")", begpos)
        pos = cls._lstrip(input, pos)
        return cls(formula), pos

    @classmethod
    @abstractmethod
    def formula_type(cls) -> Type[FormulaT]:
        """
        Get the type of parenthetical formula.
        """
        ...
