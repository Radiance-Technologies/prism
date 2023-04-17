"""
class to cache and search the logical mappings yaml.
"""

import re
from pathlib import Path
from typing import Dict, Optional, Set, Tuple, Union

from prism.util import cyaml
from prism.util.opam import Version

_PARENT_DIR = Path(__file__).parent

_OPAM_MAPPING_DATA_PATH = _PARENT_DIR / "opam_mappings.yml"
_COQ_8_9_1_DATA_PATH = _PARENT_DIR / "coq_8.9.1_mappings.yml"
_COQ_8_10_2_DATA_PATH = _PARENT_DIR / "coq_8.10.2_mappings.yml"
_COQ_8_11_2_DATA_PATH = _PARENT_DIR / "coq_8.11.2_mappings.yml"
_COQ_8_12_2_DATA_PATH = _PARENT_DIR / "coq_8.12.2_mappings.yml"
_COQ_8_13_2_DATA_PATH = _PARENT_DIR / "coq_8.13.2_mappings.yml"
_COQ_8_14_1_DATA_PATH = _PARENT_DIR / "coq_8.14.1_mappings.yml"
_COQ_8_15_2_DATA_PATH = _PARENT_DIR / "coq_8.15.2_mappings.yml"

RequiredLibrary = Tuple[Optional[str], str]


class LogicalMappings:
    """
    Cache and search logical mappings for Coq packages.

    Parameters
    ----------
    mappings : Dict[str, str]
        A map from logical library names to packages that define them.
    """

    opam: 'LogicalMappings'
    """
    A cached map from logical library names to public opam packages.
    """
    coq_8_9_1: 'LogicalMappings'
    """
    A cached map of logical library names belonging to Coq 8.9.1.
    """
    coq_8_10_2: 'LogicalMappings'
    """
    A cached map of logical library names belonging to Coq 8.10.2.
    """
    coq_8_11_2: 'LogicalMappings'
    """
    A cached map of logical library names belonging to Coq 8.11.2.
    """
    coq_8_12_2: 'LogicalMappings'
    """
    A cached map of logical library names belonging to Coq 8.12.2.
    """
    coq_8_13_2: 'LogicalMappings'
    """
    A cached map of logical library names belonging to Coq 8.13.2.
    """
    coq_8_14_1: 'LogicalMappings'
    """
    A cached map of logical library names belonging to Coq 8.14.1.
    """
    coq_8_15_2: 'LogicalMappings'
    """
    A cached map of logical library names belonging to Coq 8.15.2.
    """

    def __init__(self, mappings: Dict[str, str]) -> None:
        """
        Initialize a searchable map of logical library names.
        """
        # precompute possible mapping variants for O(1) lookups
        self.mappings: Dict[RequiredLibrary, Set[str]]
        self.mappings = {}
        for library, package in mappings.items():
            variants = self._generate_variants(library)
            for variant in variants:
                mapping = self.mappings.setdefault(variant, set())
                mapping.add(package)

    def search(self,
               prefix: Optional[str] = None,
               suffix: str = "") -> Set[str]:
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
        try:
            matching_packages = set(self.mappings[(prefix, suffix)])
        except KeyError:
            matching_packages = set()
        return matching_packages

    @classmethod
    def get_coq_mappings(
            cls,
            coq_version: Union[str,
                               Version]) -> 'LogicalMappings':
        """
        Get logical library mappings for the requested version of Coq.
        """
        coq_version = str(coq_version)
        try:
            return getattr(
                LogicalMappings,
                f"coq_{coq_version.replace('.', '_')}")
        except AttributeError:
            raise NotImplementedError(
                f"Mappings for Coq {coq_version} are not implemented.")

    @staticmethod
    def _generate_variants(library: str) -> Set[RequiredLibrary]:
        """
        Generate variants of a library's possible Required statements.

        Parameters
        ----------
        library : str
            A fully qualified library name.

        Returns
        -------
        Set[RequiredLibrary]
            A set of possible prefixes and suffixes that may appear in a
            Required statement corresponding to the given `library`.
        """
        # ignore possibility of qualid in final component
        parts = library.split('.')
        variants = set()
        prefix = None
        for split_point in range(len(parts)):
            prefix = '.'.join(parts[: split_point])
            suffix_parts = parts[split_point :]
            if not prefix:
                prefix = None
            # generate all possible suffixes
            for i in range(len(suffix_parts)):
                for j in range(i + 1, len(suffix_parts) + 1):
                    suffix = '.'.join(suffix_parts[i : j])
                    variants.add((prefix, suffix))
        return variants

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


# load precomputed mappings
with open(_OPAM_MAPPING_DATA_PATH) as f:
    LogicalMappings.opam = LogicalMappings(cyaml.safe_load(f))
with open(_COQ_8_9_1_DATA_PATH) as f:
    LogicalMappings.coq_8_9_1 = LogicalMappings(cyaml.safe_load(f))
with open(_COQ_8_10_2_DATA_PATH) as f:
    LogicalMappings.coq_8_10_2 = LogicalMappings(cyaml.safe_load(f))
with open(_COQ_8_11_2_DATA_PATH) as f:
    LogicalMappings.coq_8_11_2 = LogicalMappings(cyaml.safe_load(f))
with open(_COQ_8_12_2_DATA_PATH) as f:
    LogicalMappings.coq_8_12_2 = LogicalMappings(cyaml.safe_load(f))
with open(_COQ_8_13_2_DATA_PATH) as f:
    LogicalMappings.coq_8_13_2 = LogicalMappings(cyaml.safe_load(f))
with open(_COQ_8_14_1_DATA_PATH) as f:
    LogicalMappings.coq_8_14_1 = LogicalMappings(cyaml.safe_load(f))
with open(_COQ_8_15_2_DATA_PATH) as f:
    LogicalMappings.coq_8_15_2 = LogicalMappings(cyaml.safe_load(f))
