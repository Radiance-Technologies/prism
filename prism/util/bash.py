"""
Miscellaneous Bash-related utilities.
"""
from prism.util.iterable import CallableIterator
from prism.util.re import re

_escape_regex = re.compile('(["\'\\\\\b\f\t\n\r\v\a])')


def escape(cmd: str) -> str:
    """
    Sanitize the given Bash command by escaping special characters.

    Parameters
    ----------
    cmd : str
        A command intended as an argument in a Bash script or command.

    Returns
    -------
    str
        The sanitized command.
    """
    matches = _escape_regex.finditer(cmd)
    replacements = [rf"\{m[0]}" for m in matches]
    return _escape_regex.sub(CallableIterator(replacements),
                             cmd).replace("'",
                                          r"'\''")
