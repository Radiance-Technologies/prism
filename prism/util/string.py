"""
Miscellaneous utilities for SerAPI interaction.
"""

import re

_whitespace_regex = re.compile(r"\s+", flags=re.DOTALL)


def escape(cmd: str) -> str:
    """
    Sanitize the given command by escaping special characters.

    In particular, backslashes and double quotes are escaped by
    prepending backslashes to each.

    Parameters
    ----------
    cmd : str
        A command.

    Returns
    -------
    str
        The sanitized command.
    """
    return cmd.replace("\\", r"\\").replace('"', r'\"')


def normalize_spaces(s: str) -> str:
    """
    Replace each span of contiguous whitespace with a single space.

    Also remove leading and trailing whitespace.
    """
    return _whitespace_regex.sub(" ", s).strip()
