"""
Expose faster C versions of PyYAML encoding/decoding functions.
"""

import yaml


def safe_dump(data: object, stream=None, **kwargs) -> str:
    """
    Safely dump a Python object to a string.

    See Also
    --------
    yaml.safe_dump
    """
    return yaml.dump_all([data], stream, Dumper=yaml.CSafeDumper, **kwargs)


def safe_load(stream):
    """
    Safely load potentially untrusted input from a stream.

    See Also
    --------
    yaml.safe_load
    """
    return yaml.load(stream, yaml.CSafeLoader)
