"""
Utilities for regular expressions.
"""
import re
from typing import Iterable


def regex_from_options(
        options: Iterable[str],
        must_start: bool,
        must_end: bool,
        group: bool = False,
        compile: bool = True) -> re.Pattern:
    """
    Make a regular expression for matching mutually exclusive options.

    Parameters
    ----------
    options : Iterable[str]
        The options to match.
    must_start : bool
        Whether the match must appear at the start of the string.
    must_end : bool
        Whether the match must appear at the end of the string.
    group : bool, optional
        Whether to capture the options as a group, by default False
    compile : bool, optional
        Whether to compile the regular expression before returning or
        not, by default True.

    Returns
    -------
    re.Pattern
        The regular expression.
    """
    regex = '|'.join(options)
    if group:
        regex = f"({regex})"
    regex = f"{'^' if must_start else ''}{regex}{'$' if must_end else ''}"
    if compile:
        regex = re.compile(regex)
    return regex
