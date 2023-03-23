"""
Module for Manager based Client/Server.
"""
import typing
from multiprocessing.managers import BaseManager
from typing import Generic, Type, TypeVar

from typing_extensions import Protocol, TypeGuard


class _GenericAlias(Protocol):
    """
    Alias for Generic.
    """

    __origin__: type[object]


class IndirectGenericSubclass(Protocol):
    """
    Type hint for generic subclass.
    """

    __orig_bases__: tuple[_GenericAlias]


def is_indirect_generic_subclass(
    obj: object,
) -> TypeGuard[IndirectGenericSubclass]:
    """
    Determine if obj is subclass of Generic.
    """
    if hasattr(obj, '__orig_bases__'):
        bases = obj.__orig_bases__
        return bases is not None and isinstance(bases, tuple)
    return False


def get_generic_args(cls):
    """
    Get types passed to generic arguments.
    """
    if not is_indirect_generic_subclass(cls):
        raise ValueError(
            'Expected class type to have an `__orig_bases__` attribute')
    return typing.get_args(cls.__orig_bases__[0])[0]


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
        if cls is not ManagedServer:
            cls.Client = get_generic_args(cls)
            cls.register(cls.Client.__name__, cls.Client)
        return super().__new__(cls, *args, **kwargs)
