"""
System path utilities.
"""
import os
from pathlib import Path


def get_relative_path(path: os.PathLike, other: os.PathLike) -> Path:
    """
    Return the relative path of one path to another.
    """
    path = Path(path).resolve()
    try:
        return path.relative_to(other)
    except ValueError:
        # target does not start with origin
        return ".." / get_relative_path(path, Path(other).parent)
