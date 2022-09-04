"""
Custom exceptions related to switch management.
"""

from typing import Tuple, Union

from prism.util.opam.formula import PackageFormula


class UnsatisfiableConstraints(Exception):
    """
    For when a switch cannot be retrieved for given package constraints.
    """

    def __init__(self, formula: PackageFormula) -> None:
        self.unsatisfiable = formula

    def __reduce__(self) -> Union[str, Tuple[PackageFormula]]:  # noqa: D105
        return UnsatisfiableConstraints, (self.unsatisfiable,)

    def __str__(self) -> str:
        """
        Show the unsatisfiable constraints.
        """
        return str(self.unsatisfiable)
