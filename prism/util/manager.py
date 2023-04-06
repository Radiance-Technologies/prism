"""
Module for Manager based Client/Server.
"""
import typing
from multiprocessing.managers import BaseManager
from typing import Generic, Type, TypeVar

from prism.util.serialize import get_typevar_bindings

ManagedClient = TypeVar('ManagedClient')


class ManagedServer(BaseManager, Generic[ManagedClient]):
    """
    A BaseManager-derived server.
    """

    Client: Type[ManagedClient]
    """
    A class attribute that can be used
    to initialize client from server.
    """

    def __new__(cls, *args, **kwargs):
        """
        Register logger with base manager.
        """
        referent = typing.cast(
            Type[ManagedClient],
            get_typevar_bindings(cls)[1][ManagedClient])
        cls.register("Client", referent)
        return super().__new__(cls, *args, **kwargs)
