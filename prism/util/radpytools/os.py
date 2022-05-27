"""
Subpackage for utilities related to the original os package.
"""

import os
from contextlib import contextmanager
from typing import Generator


@contextmanager
def pushd(dir: os.PathLike) -> Generator[None, None, None]:
    """
    Temporarily change directories for the duration of the context.

    Mimics the behavior of a ``pushd`` command followed by a ``popd``
    command at context conclusion

    Parameters
    ----------
    dir : os.PathLike
        The new directory to push onto the stack.

    Examples
    --------
    >>> from pathlib import Path
    >>> os.chdir(Path.home())
    >>> with pushd("/etc"):
    ...     print(os.getcwd())
    ...
    /etc
    >>> print(os.getcwd()) # your home directory
    """
    current_dir = os.getcwd()
    os.chdir(dir)
    try:
        yield
    finally:
        os.chdir(current_dir)
