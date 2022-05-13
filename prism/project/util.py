"""
Common project-related utilities.
"""

import os
import urllib.parse
from pathlib import Path
from typing import Union

URL = str


def extract_name(url: Union[URL, os.PathLike]) -> str:
    """
    Get project name from url or path.

    Parameters
    ----------
    url :  Union[URL, os.PathLike]
        A URL or path to an existing project or repository.

    Returns
    -------
    str
        The name of the project.
    """
    url = str(url)
    fork = Path(urllib.parse.urlparse(url.strip()).path)
    return fork.stem
