"""
Defines exceptions related to project management.
"""

from typing import Tuple, Union


class DirHasNoCoqFiles(Exception):
    """
    Exception indicating that the current directory has no Coq files.

    Sub-directories should be checked as well before raising this
    exception.
    """

    pass


class MissingMetadataError(Exception):
    """
    Exception indicating that an operation requires unknown metadata.
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

    def __reduce__(self) -> Union[str, Tuple[str, int, str, str]]:  # noqa: D105
        return ProjectBuildError, (self.msg, self.return_code, self.stdout, self.stderr)

    def __str__(self) -> str:  # noqa: D105
        return self.msg


class ProjectCommandError(ProjectBuildError):
    """
    A specialization of `ProjectBuildError` to non-build commands.
    """

    pass
