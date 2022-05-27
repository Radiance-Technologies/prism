"""
Provides debugging utilities.

Adapted from `roosterize.Debug` at
https://github.com/EngineeringSoftware/roosterize.
"""

import collections
from typing import Counter, Set


class Debug:
    """
    For holding some debugging variables.
    """

    is_debug = False
    global_print_counter = 0
    print_counter: Counter[str] = collections.Counter()
    seen_shapes: Set[str] = set()
