"""
Exceptions related to interacting with Coq through SerAPI.
"""


class CoqExn(Exception):
    """
    An error raised within Coq and lifted to a Python exception.
    """

    def __init__(self, msg: str, full_sexp: str):
        super().__init__()
        self.msg = msg
        """
        The error message as reported by Coq.
        """
        self.full_sexp = full_sexp
        """
        The full S-expression containing the error yielded from SerAPI.
        """

    def __str__(self) -> str:
        """
        Get the Coq error message.
        """
        return self.msg

    def __repr__(self) -> str:  # noqa: D105
        return str(self)


class CoqTimeout(Exception):
    """
    Raised when SerAPI fails to respond within a time limit.
    """

    pass
