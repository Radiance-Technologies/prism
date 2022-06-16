import json
import os
from typing import Optional, Set


def load_json(filepath: os.PathLike, prefix: Optional[str] = None) -> Set[str]:
    """
    Load a json containing a tree of logical names in json format.

    Each key in the json is the name of a directory or file in
    the project that will appear in the library. Nested
    objects imply that logical names in the object are
    subpaths found in the parent object.

    Parameters
    ----------
    filepath : os.PathLike
        Path to the json file.
    prefix : Optional[str], optional
        If not None, prepend the prefix to all produced logical names,
        by default None.

    Returns
    -------
    Set[str]
        Set of logical names extracted from the json objects.
    """
    data = json.load(open(filepath, "r"))
    stack = [(prefix, data)]
    names = []
    while len(stack) > 0:
        prefix, d = stack.pop()
        if isinstance(d, dict) and len(d) > 0:
            stack = [('.'.join((prefix, k)), v) for k, v in d.items()] + stack
        if prefix is not None and prefix not in names:
            names.append(prefix)
    return names


COQ_STANDARD_LIBRARY = load_json('coq.json', prefix='Coq')
"""
This json file was produced using the following documentation:
https://coq.inria.fr/library/
"""
NON_PROJECT_LIBRARIES = load_json('external.json')
"""
The library names in this json file are an incomplete list of
project coq dependencies that are not projects considered
for data mining.
"""
