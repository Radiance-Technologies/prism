"""
System path utilities.
"""
from pathlib import Path
from typing import Sequence

from prism.util.radpytools import PathLike


def get_relative_path(path: PathLike, other: PathLike) -> Path:
    """
    Return the relative path of one path to another.
    """
    path = Path(path).resolve()
    try:
        return path.relative_to(other)
    except ValueError:
        # target does not start with origin
        other = Path(other)
        if other.parts:
            return ".." / get_relative_path(path, other.parent)
        else:
            # other is the system root
            return path


def without_suffixes(path: PathLike) -> Path:
    """
    Remove all suffixes (extensions) from a path.
    """
    path = Path(path)
    while True:
        without = path.with_suffix('')
        if without == path:
            break
        path = without
    return without


def with_suffixes(path: PathLike, suffixes: Sequence[str]) -> Path:
    """
    Replace the suffixes of a path with those given.
    """
    path = without_suffixes(path)
    return path.with_suffix(''.join(suffixes))
