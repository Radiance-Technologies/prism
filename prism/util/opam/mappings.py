"""
class to cache and search the logical mappings yaml.
"""

import re

import yaml


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
            with open("./dataset/logicalmapping.yml") as f:
                cls.mappings = yaml.safe_load(f)

        if (prefix):
            reg = re.compile(
                fr"{re.escape(prefix)}\.(.+\.)*{re.escape(suffix)}")
        else:
            reg = re.compile(fr"(.+\.)?{re.escape(suffix)}")

        for x in cls.mappings:
            if re.match(reg, x):
                return cls.mappings[x]

        return None
