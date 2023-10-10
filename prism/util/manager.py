#
# Copyright (c) 2023 Radiance Technologies, Inc.
#
# This file is part of PRISM
# (see https://github.com/orgs/Radiance-Technologies/prism).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program. If not, see
# <http://www.gnu.org/licenses/>.
#
"""
Module for Manager based Client/Server.
"""
import inspect
import multiprocessing
import multiprocessing.connection
import multiprocessing.queues
import multiprocessing.reduction
import re
import typing
from multiprocessing.managers import BaseManager, NamespaceProxy  # type: ignore
from typing import Generic, Type, TypeVar

import dill

from prism.util.serialize import get_typevar_bindings


# HACK in lieu of writing a proper reduction protocol compatible with
# the builtin pickler
def _override_multiprocessing_pickler():
    dill.Pickler.dumps = dill.dumps  # type: ignore
    dill.Pickler.loads = dill.loads  # type: ignore
    multiprocessing.reduction.ForkingPickler = dill.Pickler  # type: ignore
    multiprocessing.reduction.dump = dill.dump
    multiprocessing.connection._ForkingPickler = dill.Pickler  # type: ignore
    multiprocessing.queues._ForkingPickler = dill.Pickler  # type: ignore


_override_multiprocessing_pickler()

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
        Register client proxy with base manager.
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
        proxy_members = {
            '_exposed_': list(exposed)
        }
        ClientProxy = type(
            referent.__name__ + "Proxy",
            (NamespaceProxy,
             ),
            proxy_members,
        )
        cls.register("Client", referent, ClientProxy)
        return super().__new__(cls, *args, **kwargs)
