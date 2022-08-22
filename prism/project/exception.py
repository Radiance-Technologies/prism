"""
Defines exceptions related to project management.
"""


class DirHasNoCoqFiles(Exception):
    """
    Exception indicating that the current directory has no Coq files.

    Sub-directories should be checked as well before raising this
    exception.
    """

    pass


class ProjectBuildError(Exception):
    """
    Exception indicating that a project has failed to build.

    Also raised when a project fails to clean or install.
    """

    def __init__(
            self,
            msg: str,
            return_code: int,
            stdout: str,
            stderr: str) -> None:
        super().__init__()
        self.msg = msg
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self) -> str:  # noqa: D105
        return self.msg
