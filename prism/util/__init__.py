"""
General utilities.
"""

import copy
from typing import Hashable, TypeVar, Union

T = TypeVar("T")


def get_as_list(d: dict, k: Hashable, default: T = None) -> Union[list, T]:
    """
    Get a value from a dict as a list or None if the key is unknown.

    Parameters
    ----------
    d : dict
        An arbitrary dictionary.
    k : Hashable
        A potential key to a value in `d`.
    default : T
        The default value to be copied and returned if `k` is not in
        `d`.

    Returns
    -------
    x : list or T
        The value to which `k` is mapped wrapped in a list if not
        already a list or `default` if `k` is not in `d`.
    """
    try:
        x = d[k]
    except KeyError:
        x = copy.deepcopy(default)
    else:
        if not isinstance(x, list):
            x = [x]
    return x
