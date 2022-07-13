"""
Miscellaneous utilities for SerAPI interaction.
"""

import re


def normalize_spaces(s: str) -> str:
    """
    Replace each span of contiguous whitespace with a single space.
    """
    return re.sub(r"\s+", " ", s, flags=re.DOTALL)
