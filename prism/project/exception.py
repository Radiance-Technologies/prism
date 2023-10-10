#
# Copyright (c) 2023 Radiance Technologies, Inc.
#
# This file is part of PRISM
# (see https://github.com/orgs/Radiance-Technologies/prism).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program. If not, see
# <http://www.gnu.org/licenses/>.
#
"""
Defines exceptions related to project management.
"""

from typing import Tuple, Union

from prism.language.gallina.analyze import SexpInfo


class DirHasNoCoqFiles(Exception):
    """
    Exception indicating that the current directory has no Coq files.

    Sub-directories should be checked as well before raising this
    exception.
    """

    pass


class ExecutionError(Exception):
    """
    Alert that an unexpected error has occurred during execution.

    For example, this may be raised if an error is encountered when
    trying to reach a designated region of repair.
    """

    def __init__(self, fail_loc: SexpInfo.Loc, error_msg: str) -> None:
        self.fail_loc = fail_loc
        self.error_msg = error_msg

    def __str__(self) -> str:  # noqa: D105
        return (
            f"In {self.fail_loc.filename}, "
            f"lines {self.fail_loc.lineno}-{self.fail_loc.lineno_last}: "
            f"{self.error_msg}")


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
