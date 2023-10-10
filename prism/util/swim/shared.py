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
Defines an auto switch manager accessible from multiple processes.
"""

from multiprocessing.managers import BaseManager, BaseProxy
from typing import Type

from prism.util.swim.base import SwitchManager

# manager starts a process that "manages" an object
# and takes requests from multiple threads...
# but it does not serialize these requests!
# it starts a new thread in the shared process for every request,
# this makes operations on the shared objects prone to
# interleaving (non-thread-safe)!

SharedSwitchManager = BaseManager

SwitchManagerProxy = BaseProxy


def SharedSwitchManagerServer(
        swim_cls: Type[SwitchManager]) -> SharedSwitchManager:
    """
    Initialize a shared switch manager subprocess.

    Parameters
    ----------
    swim_cls : Type[SwitchManager]
        The type of `SwitchManager` that will be shared.

    Returns
    -------
    SharedSwitchManager
        A running server that manages requests sent to the shared switch
        manager.

    See Also
    --------
    SharedSwitchManagerClient : To send requests to the shared manager.
    """
    manager = SharedSwitchManager()
    manager.register("SwitchManager", swim_cls)
    # dies when parent process does, no need to clean up.
    manager.start()
    return manager


def SharedSwitchManagerClient(
        server: SharedSwitchManager,
        *args,
        **kwargs) -> SwitchManagerProxy:
    """
    Create a client of the given `SharedSwitchManager` server.

    Parameters
    ----------
    server : SharedSwitchManager
        A switch manager server created by `SharedSwitchManagerServer`.
    args : Tuple[Any, ...]
        Positional arguments for the constructor of the switch manager
        class wich which the `server` was created.
    kwargs : Dict[str, Any]
        Keyword arguments for the constructor of the switch manager
        class wich which the `server` was created.

    Returns
    -------
    SwitchManagerProxy
        A proxy object that behaves outwardly the same as the
        `SwitchManager` type with which the `server` was created.

    See Also
    --------
    SharedSwitchManagerServer : For creation of the shared server.
    """
    return server.SwitchManager(*args, **kwargs)
