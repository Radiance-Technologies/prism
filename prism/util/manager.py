"""
Module for Manager based Client/Server.
"""
import inspect
import re
import typing
from functools import partialmethod
from multiprocessing.managers import (  # type: ignore
    BaseManager,
    BaseProxy,
    NamespaceProxy,
)
from typing import Generic, Type, TypeVar

from prism.util.serialize import get_typevar_bindings

ManagedClient = TypeVar('ManagedClient')

__all__ = ['ManagedServer']

_PRIVATE_METHOD_REGEX = re.compile('_(?:[^_].*)?')


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
        reserved = {
            '_exposed_',
            '__class_getitem__',
            '__dir__',
            '__getstate__',
            '__init__',
            '__init_subclass__',
            '__reduce__',
            '__reduce_ex__',
            '__repr__',
            '__sizeof__',
            '__str__',
            '__subclasshook__',
            '__weakref__',
        }
        exposed = {'__getattribute__',
                   '__setattr__',
                   '__delattr__'}
        proxy_methods = {}

        def _callmethod(self: BaseProxy, nm, *args, **kwargs):
            return self._callmethod(nm, args, kwargs)

        for nm, _ in inspect.getmembers(referent,
                                        lambda m: inspect.ismethod(m)
                                        or inspect.isfunction(m)
                                        or inspect.isdatadescriptor(m)
                                        or inspect.ismemberdescriptor(m)
                                        or inspect.ismethoddescriptor(m)
                                        or inspect.isgetsetdescriptor(m)):
            # do not expose private or reserved attributes
            if (nm not in exposed and nm not in reserved
                    and _PRIVATE_METHOD_REGEX.fullmatch(nm) is None):
                exposed.add(nm)
                proxy_methods[nm] = partialmethod(_callmethod, nm)
        proxy_members = {
            '_exposed_': list(exposed)
        }
        proxy_members.update(proxy_methods)
        ClientProxy = type(
            referent.__name__ + "Proxy",
            (NamespaceProxy,
             ),
            proxy_members,
        )
        cls.register("Client", referent, ClientProxy)
        return super().__new__(cls, *args, **kwargs)
