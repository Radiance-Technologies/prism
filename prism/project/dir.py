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
Module providing Coq project directory class representations.
"""

import pathlib

from prism.project.base import MetadataArgs, Project
from prism.project.exception import DirHasNoCoqFiles
from prism.util.radpytools import PathLike


class ProjectDir(Project):
    """
    Class for representing a Coq project.

    This class makes no assumptions about whether the project directory
    is a git repository or not.
    """

    def __init__(self, dir_abspath: PathLike, *args, **kwargs):
        """
        Initialize Project object.
        """
        self.working_dir = dir_abspath
        super().__init__(dir_abspath, *args, **kwargs)
        if not self._traverse_file_tree():
            raise DirHasNoCoqFiles(f"{dir_abspath} has no Coq files.")

    @property
    def metadata_args(self) -> MetadataArgs:  # noqa: D102
        return MetadataArgs(None, None, self.coq_version, self.ocaml_version)

    @property
    def name(self) -> str:  # noqa: D102
        return pathlib.Path(self.working_dir).stem

    @property
    def path(self) -> pathlib.Path:  # noqa: D102
        return pathlib.Path(self.working_dir)

    def _pre_get_file(self, **kwargs):
        """
        Do nothing.
        """
        pass

    def _pre_get_random(self, **kwargs):
        """
        Do nothing.
        """
        pass
