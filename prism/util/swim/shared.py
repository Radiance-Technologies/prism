"""
Defines an auto switch manager that maintains switches across a global state.
"""

from prism.util.swim.auto import AutoSwitchManager

from multiprocessing.managers import BaseManager, Server

from multiprocessing import Lock

# manager starts a process that "manages" an object
# and takes requests from multiple threads...
# but it does not serialize these requests!
# it starts a new thread in the shared process for every request,
# this makes operations on the shared objects prone to interleaving (non-thread-safe)!



_MANAGER = BaseManager()

_MANAGER.register("AutoSwitchManager",AutoSwitchManager)

_MANAGER.start()


SharedSwitchManager = lambda *args, **kwargs: _MANAGER.AutoSwitchManager(*args,**kwargs)


