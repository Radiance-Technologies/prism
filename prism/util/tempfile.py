"""
Utilities for creation of temporary files.
"""
import os
import tempfile
from typing import BinaryIO, TextIO


def PermissiveNamedTemporaryFile(*args, **kwargs) -> TextIO | BinaryIO:
    """
    Get a named temporary file with the current default permissions.

    Notes
    -----
    Temporary files are usually only created with only read and write
    permissions for the owner of the file.
    This function allows one to create temporary files that can be
    shared with a group without subsequent manual intervention.
    """
    f = tempfile.NamedTemporaryFile(*args, **kwargs)
    # Must set umask to get umask (octal).
    # Do not use 0 like pip does for security reasons
    # (https://github.com/pypa/pip/blob/38a8fb1f601c782eef0988290f11aa2a4dfc3c69/src/pip/_internal/utils/unpacking.py#L43).
    # See https://bugs.python.org/issue21082 for explanation.
    umask = os.umask(0o666)
    # reset umask
    os.umask(umask)
    # Change permissions of tempfile
    os.chmod(f.name, 0o666 & ~umask)
    return f
