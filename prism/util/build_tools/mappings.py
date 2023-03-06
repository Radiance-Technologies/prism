"""
class to cache and search the logical mappings yaml.
"""

import re
from pathlib import Path
from typing import ClassVar, Dict, Optional, Set

import yaml

from prism.util.radpytools import cachedmethod

_MAPPING_DATA_PATH = Path(__file__).parent / "logical_mapping.yml"


class LogicalMappings:
    """
    Cache and search logical mappings for Coq packages.
    """

    mappings: ClassVar[Optional[Dict[str, str]]] = None
    """
    The cached map from logical library names to package names.

    If None, then it will be refreshed on the next call to `search`.
    """

    @classmethod
    def search(cls, prefix: Optional[str] = None, suffix: str = "") -> Set[str]:
        """
        Search Coq package logical mappings for the owner package.

        Parameters
        ----------
        prefix : Optional[str]
            The prefix logical path to a library or None if not
            required.
        suffix : str
            The suffix logical path to a library.

        Returns
        -------
        Set[str]
            The set of packages matching the given logical prefixes and
            suffixes, if any.
        """
        if cls.mappings is None:
            # load the mappings yaml
            with open(_MAPPING_DATA_PATH) as f:
                cls.mappings = yaml.safe_load(f)

        matching_packages: Set[str] = set()

        for x in cls.mappings:
            if cls.is_match(prefix, suffix, x):
                matching_packages.add(cls.mappings[x])

        return matching_packages

    @cachedmethod
    @staticmethod
    def _match_pattern(prefix: Optional[str], suffix: str) -> re.Pattern:
        """
        Get a regex that matches a given library prefix and suffix.
        """
        if prefix:
            reg = re.compile(
                fr"{re.escape(prefix)}\.(.+\.)*{re.escape(suffix)}")
        else:
            reg = re.compile(fr"(.+\.)?{re.escape(suffix)}")
        return reg

    @staticmethod
    def is_match(prefix: Optional[str], suffix: str, library: str) -> bool:
        """
        Return whether a given prefix and suffix match a given library.

        Parameters
        ----------
        prefix : Optional[str]
            The prefix logical path to a library or None if not
            required.
        suffix : str
            The suffix logical path to a library.
        library : str
            A logical library path.

        Returns
        -------
        bool
            True if the library is a match, False otherwise.
        """
        reg = LogicalMappings._match_pattern(prefix, suffix)
        return reg.match(library) is not None
