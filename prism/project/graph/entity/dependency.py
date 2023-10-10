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
Module for representing coq dependencies.
"""
from dataclasses import dataclass
from typing import Tuple

from prism.project.graph.entity.base import ProjectEntity

from .logical import LogicalName
from .root import ProjectRoot


@dataclass
class ProjectCoqDependency(ProjectRoot):
    """
    A node that will connect requirements to ProjectCoqLibrary nodes.

    This node will have a inward edge from the root node as it is a
    child of the root node. It will have outward edges to the
    requirement nodes that establish the dependency and to
    ProjectCoqLibrary nodes in the graph that satisfy the requirement.

    If no edge to a ProjectCoqLibrary exist for a given node, then the
    resolution for that requirement is not known.
    """

    logical_name: LogicalName

    def __post_init__(self):
        """
        Initialize the ProjectEntity attributes.
        """
        ProjectEntity.__init__(self, None)

    def id_component(self) -> Tuple[str, str]:
        """
        Use file entity id with logical name as id.
        """
        return "dep", str(self.logical_name)
