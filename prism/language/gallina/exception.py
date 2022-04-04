"""
Defines exceptions related to Gallina and its parsing or analysis.
"""

from prism.language.sexp.node import SexpNode


class SexpAnalyzingException(Exception):
    """
    For representing errors thrown during Gallina s-expression analysis.
    """

    def __init__(
            self,
            sexp: SexpNode = None,
            message: str = "",
            *args,
            **kwargs):
        self.sexp = sexp
        self.message = message

    def __str__(self):
        return f"{self.message}\nin sexp: {self.sexp.pretty_format()}"
