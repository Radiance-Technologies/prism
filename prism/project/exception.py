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

    pass
