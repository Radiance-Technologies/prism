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
Module for defining Project Node.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from prism.project.metadata.storage import Context

from .base import ProjectEntity


@dataclass
class ProjectRoot(ProjectEntity):
    """
    A node marking the root of a project.
    """

    project_path: Path
    context: Context

    def __post_init__(self):
        """
        Initialize ProjectEntity attributes.
        """
        ProjectEntity.__init__(
            self,
            self.project_path,
        )

    @property
    def commit(self) -> str:
        """
        Return current commit.

        Returns
        -------
        str
            Project name stored in context
        """
        return self.context.revision.commit_sha

    @property
    def project_name(self) -> str:
        """
        Return project name from context.

        Returns
        -------
        str
            Project name stored in context
        """
        return self.context.revision.project_source.project_name

    def id_component(self) -> Tuple[str, str]:
        """
        Use root entity id with relative file path as id.
        """
        return "project", str(self.project_name)

    def init_parent(self) -> None:
        """
        Return None since ProjectRoot has no parent entity.
        """
        return None
