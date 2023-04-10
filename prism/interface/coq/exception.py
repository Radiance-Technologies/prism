"""
Exceptions related to interacting with Coq through SerAPI.
"""

from typing import Optional, Tuple, Type

from prism.language.gallina.analyze import SexpInfo


class CoqExn(Exception):
    """
    An error raised within Coq and lifted to a Python exception.
    """

    def __init__(
            self,
            msg: str,
            full_sexp: str,
            location: Optional[SexpInfo.Loc] = None,
            command: Optional[str] = None,
            query: Optional[str] = None):
        super().__init__()
        self.msg = msg
        """
        The error message as reported by Coq.
        """
        self.full_sexp = full_sexp
        """
        The full S-expression containing the error yielded from SerAPI.
        """
        self.location = location
        """
        The source code location of the error.
        """
        self.command = command
        """
        The text of the Vernacular command that directly or indirectly
        caused the error.
        """
        self.query = query
        """
        The text of a SerAPI query that directly caused the error.
        """

    def __reduce__(  # noqa: D105
        self) -> Tuple[Type['CoqExn'],
                       Tuple[str,
                             str,
                             Optional[SexpInfo.Loc],
                             Optional[str],
                             Optional[str]]]:
        return (
            CoqExn,
            (self.msg,
             self.full_sexp,
             self.location,
             self.command,
             self.query))

    def __repr__(self) -> str:  # noqa: D105
        return str(self)

    def __str__(self) -> str:
        """
        Get the Coq error message.
        """
        if self.query is not None:
            query_text = f"While executing query:\n{self.query}\n"
        else:
            query_text = ""
        if self.location is None:
            msg = ''.join([self.msg, "\n", query_text])
        else:
            if self.command is not None:
                command_text = f":\n{self.command}"
            else:
                command_text = ""
            if self.location.lineno != self.location.lineno_last:
                line_text = f"lines {self.location.lineno}-{self.location.lineno_last}"
            else:
                line_text = (
                    f"line {self.location.lineno}, "
                    f"characters {self.location.column_start}"
                    f"-{self.location.column_end}")
            msg = ''.join(
                [
                    self.msg,
                    "\n",
                    query_text,
                    f"In file {self.location.filename}, ",
                    line_text,
                    command_text,
                ])
        return msg


class CoqTimeout(Exception):
    """
    Raised when SerAPI fails to respond within a time limit.
    """

    def __init__(self, *args, query: Optional[str] = None) -> None:
        super().__init__(*args)
        self.query = query
        """
        The text of a SerAPI query that caused the timeout.
        """

    def __reduce__(  # noqa: D105
            self) -> Tuple[Type['CoqTimeout'],
                           Tuple[Optional[str]]]:
        return CoqTimeout, (self.query,)

    def __str__(self) -> str:  # noqa: D105
        if self.query is None:
            msg = super().__str__()
        else:
            msg = f'Timeout in:\n    {self.query}'
        return msg
