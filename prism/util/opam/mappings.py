"""
class to cache and search the logical mappings yaml.
"""

import re
from pathlib import Path

import yaml

_MAPPING_DATA_PATH = Path(__file__).parent / "logical_mapping.yml"


class LogicalMappings:
    """
    cache and search logical mappings for coq packages.
    """

    @classmethod
    def search(cls, prefix="", suffix=""):
        """
        Search coq package logical mappings for the owner package.

        provide a suffix and optionally a prefix of the logical path.
        """
        if (not hasattr(cls, "mappings")):
            # load the mappings yaml
            # todo: this needs to be loaded from the pip installed dir!
            with open(_MAPPING_DATA_PATH) as f:
                cls.mappings = yaml.safe_load(f)

        if (prefix):
            reg = re.compile(
                fr"{re.escape(prefix)}\.(.+\.)*{re.escape(suffix)}")
        else:
            reg = re.compile(fr"(.+\.)?{re.escape(suffix)}")

        candidate = None

        for x in cls.mappings:
            if re.match(reg, x):
                if (candidate is not None):
                    return None  # double match, ambiguous
                candidate = cls.mappings[x]

        return candidate
