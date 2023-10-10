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
Module for defining nodes for project files.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from prism.project.graph.entity.base import ProjectEntity

from .root import ProjectRoot
from .type import ProjectFileType


@dataclass
class ProjectFile(ProjectRoot):
    """
    A dataclass for handling nodes that project files or directories.
    """

    project_file_path: Path
    project_file_type: ProjectFileType

    def __post_init__(self):
        """
        Initialize ProjectEntity attributes and add extra to data.
        """
        ProjectEntity.__init__(
            self,
            self.project_file_path,
            parent=self.project_file_path.parent,
            relative=self.project_file_path.relative_to(self.project_path),
            stem=self.project_file_path.stem,
            suffix=self.project_file_path.suffix or None,
        )

    def id_component(self) -> Tuple[str, str]:
        """
        Use root entity id with relative file path as id.
        """
        value = f"{self.project_file_path.relative_to(self.project_path)}"
        label = f"{self.project_file_type.name}"
        return label, value
