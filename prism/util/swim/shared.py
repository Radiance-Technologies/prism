"""
Defines an adaptive switch manager that maintains switches across a global state.
"""

from prism.util.swim.adaptive import AdaptiveSwitchManager

from multiprocessing.managers import BaseManager

_MANAGER = BaseManager()

_MANAGER.register("AdaptiveSwitchManager",AdaptiveSwitchManager)

_MANAGER.start()

SharedSwitchManager = _MANAGER.AdaptiveSwitchManager()


