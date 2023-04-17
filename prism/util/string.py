"""
Miscellaneous utilities for SerAPI interaction.
"""

from prism.util.iterable import CallableIterator
from prism.util.re import re

_whitespace_regex = re.compile(r"\s+", flags=re.DOTALL)
_escape_regex = re.compile('(["\'\\\\\b\f\t\n\r\v\a])')

_escaped_chars = {x: repr(x)[1 :-1]
                  for x in "\b\f\t\n\r\v\a"} | {x: "\\" + x for x in "\"\'\\"}


def escape(s: str) -> str:
    """
    Sanitize the given string by escaping special characters.

    Parameters
    ----------
    s : str
        A string.

    Returns
    -------
    str
        The sanitized command.
    """
    matches = _escape_regex.finditer(s)
    replacements = [_escaped_chars[m.group(0)] for m in matches]
    return _escape_regex.sub(CallableIterator(replacements), s)


def escape_backslash(s: str) -> str:
    """
    Escape only backslashes.

    Parameters
    ----------
    s : str
        A string.

    Returns
    -------
    str
        An escaped string.
    """
    return s.replace("\\", r"\\")


def normalize_spaces(s: str) -> str:
    """
    Replace each span of contiguous whitespace with a single space.

    Also remove leading and trailing whitespace.
    """
    return _whitespace_regex.sub(" ", s).strip()


def unquote(s: str) -> str:
    """
    Remove starting and ending (double) quotes if present.
    """
    if s.startswith('"') and s.endswith('"'):
        s = s[1 :-1]
    return s


def quote_escape(s: str, quotes_only: bool = False) -> str:
    """
    Escape the given string and surround it in double quotes.

    Quotes are only added if any character in the string needed to be
    escaped.

    Parameters
    ----------
    s : str
        A string.
    quotes_only : bool, optional
        Escape only double quotes, by default False

    Returns
    -------
    str
        The escaped and quoted string.
    """
    if _escape_regex.search(s) is not None:
        # escape double quotes only
        if quotes_only:
            escaped = s.replace('"', r'\"')
        else:
            escaped = escape(s)
        s = f'"{escaped}"'
    return s
