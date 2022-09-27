"""
Defines an auto switch manager accessible from multiple processes.
"""

from multiprocessing.managers import BaseManager

from prism.util.swim.auto import AutoSwitchManager

# manager starts a process that "manages" an object
# and takes requests from multiple threads...
# but it does not serialize these requests!
# it starts a new thread in the shared process for every request,
# this makes operations on the shared objects prone to
# interleaving (non-thread-safe)!

_MANAGER = BaseManager()

_MANAGER.register("AutoSwitchManager", AutoSwitchManager)

# dies when parent process does, no need to clean up.
_MANAGER.start()


def SharedSwitchManager(*args, **kwargs):
    """
    Return a new SharedSwitchManager.

    Really just an AutoSwitchManager in a shared context.

    Takes precisely the same args as the
    AutoSwitchManager constructor.
    """
    return _MANAGER.AutoSwitchManager(*args, **kwargs)
