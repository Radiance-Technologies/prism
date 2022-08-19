"""
Custom exceptions related to switch management.
"""


class UnsatisfiableConstraints(Exception):
    """
    For when a switch cannot be retrieved for given package constraints.
    """

    pass
