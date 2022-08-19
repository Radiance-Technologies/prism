"""
Define a metaclass for enumerated abstract classes.

Also allows enumerated types to inherit from abstract classes.
"""

from abc import ABCMeta
from enum import EnumMeta


class ABCEnumMeta(EnumMeta, ABCMeta):
    """
    A metaclass that allows one to combine abstract classes and enums.
    """

    pass


class ABCEnum(metaclass=ABCEnumMeta):
    """
    Provides a standard way to create an ABCEnum through inheritance.
    """

    __slots__ = ()
