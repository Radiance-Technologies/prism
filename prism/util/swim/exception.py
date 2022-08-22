"""
Custom exceptions related to switch management.
"""

from prism.util.opam.formula import PackageFormula


class UnsatisfiableConstraints(Exception):
    """
    For when a switch cannot be retrieved for given package constraints.
    """

    def __init__(self, formula: PackageFormula) -> None:
        self.unsatisfiable = formula

    def __str__(self) -> str:
        """
        Show the unsatisfiable constraints.
        """
        return str(self.unsatisfiable)
