"""
Defines a generic class for binary relational formulas.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Tuple, Type, Union

from .binary import Binary
from .common import FormulaT, RelOp, Value


@dataclass(frozen=True)
class Relational(Binary[FormulaT, RelOp], ABC):
    """
    A logical combination of two version formulae.
    """

    @property
    def relop(self) -> RelOp:
        """
        Get the binary relational operator.
        """
        return self.op

    def is_satisfied(
            self,
            *objects: Tuple[Any,
                            ...],
            **kwargs: Dict[str,
                           Any]) -> bool:
        """
        Reduce the relational formula to a Boolean.
        """
        ...

    def simplify(
        self,
        *objects: Tuple[Any,
                        ...],
        **kwargs: Dict[str,
                       Any]) -> Union[Value,
                                      'Relational[FormulaT]',
                                      FormulaT]:
        """
        Simplify the relational formula.
        """
        ...

    @classmethod
    @abstractmethod
    def formula_type(cls) -> Type[FormulaT]:
        """
        Get the type of relational formula.
        """
        ...
