"""
Miscellaneous utilities for SerAPI interaction.
"""

import re


def escape(vernac_cmd: str) -> str:
    """
    Sanitize the given command by escaping special characters.

    Parameters
    ----------
    vernac_cmd : str
        A command to be sent to SerAPI.

    Returns
    -------
    str
        The sanitized command.
    """
    return vernac_cmd.replace("\\", "\\\\").replace('"', '\\"')


def normalize_spaces(s: str) -> str:
    """
    Replace each span of contiguous whitespace with a single space.

    Also remove leading and trailing whitespace.
    """
    return re.sub(r"\s+", " ", s, flags=re.DOTALL).strip()
