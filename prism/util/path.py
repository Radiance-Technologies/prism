"""
System path utilities.
"""
from pathlib import Path

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
