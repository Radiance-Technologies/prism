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
            command: Optional[str] = None):
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
        The text of the command that caused the error.
        """

    def __reduce__(  # noqa: D105
        self) -> Tuple[Type['CoqExn'],
                       Tuple[str,
                             str,
                             Optional[SexpInfo.Loc]]]:
        return CoqExn, (self.msg, self.full_sexp, self.location)

    def __repr__(self) -> str:  # noqa: D105
        return str(self)

    def __str__(self) -> str:
        """
        Get the Coq error message.
        """
        if self.location is None:
            msg = self.msg
        else:
            if self.command is not None:
                command_text = f":\n{self.command}"
            else:
                command_text = ""
            msg = ''.join(
                [
                    self.msg,
                    "\n",
                    f"In file {self.location.filename}, "
                    f"lines {self.location.lineno}-{self.location.lineno_last}",
                    command_text
                ])
        return msg


class CoqTimeout(Exception):
    """
    Raised when SerAPI fails to respond within a time limit.
    """

    pass
