"""
General utilities and type aliases for system paths.
"""

import os
import pathlib
import typing

PathLike = typing.Union[str, os.PathLike, pathlib.Path]
