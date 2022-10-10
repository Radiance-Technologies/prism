"""
Manage the creation, organization, and retrieval of OPAM switches.
"""

from .adaptive import AdaptiveSwitchManager  # noqa: F401
from .auto import AutoSwitchManager  # noqa: F401
from .base import SwitchManager  # noqa: F401
from .exception import UnsatisfiableConstraints  # noqa: F401
from .shared import (  # noqa: F401
    SharedSwitchManager,
    SharedSwitchManagerClient,
    SharedSwitchManagerServer,
    SwitchManagerProxy,
)
