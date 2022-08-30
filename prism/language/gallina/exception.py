"""
Defines exceptions related to Gallina and its parsing or analysis.

Adapted from `roosterize.parser.SexpAnalyzer`
at https://github.com/EngineeringSoftware/roosterize/.
"""

from typing import Tuple, Union

from prism.language.sexp.node import SexpNode


class SexpAnalyzingException(Exception):
    """
    For representing errors thrown during Gallina s-expression analysis.
    """

    def __init__(self, sexp: SexpNode, message: str = ""):
        self.sexp = sexp
        self.message = message

    def __reduce__(self) -> Union[str, Tuple[SexpNode, str]]:  # noqa: D105
        return SexpAnalyzingException, (self.sexp, self.message)

    def __str__(self):  # noqa: D105
        return f"{self.message}\nin sexp: {self.sexp.pretty_format()}"
