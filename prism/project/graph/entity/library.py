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
Module for defining Library nodes.
"""
from dataclasses import dataclass
from typing import Tuple

from prism.project.graph.entity.base import ProjectEntity

from .file import ProjectFile
from .logical import LogicalName


@dataclass
class ProjectCoqLibrary(ProjectFile):
    """
    A ProjectFile that can be bound to a logical name.

    The logical name is the referenece used to import the following
    library.
    """

    logical_name: LogicalName

    def __post_init__(self):
        """
        Initialize ProjectEntity attributes and set default name.
        """
        if self.logical_name is None:
            self.logical_name = self.default_lib_name
        ProjectEntity.__init__(
            self,
            self.project_file_path,
        )

    @property
    def default_lib_name(self) -> LogicalName:
        """
        Return stem of file path as the default library name.

        Returns
        -------
        LogicalName
            The default library name.
        """
        return LogicalName(self.project_file_path.stem)

    def id_component(self) -> Tuple[str, str]:
        """
        Use file entity id with logical name as id.
        """
        return "lib", str(self.logical_name)

    @classmethod
    def init_with_local_name(cls, parent: ProjectFile) -> 'ProjectCoqLibrary':
        """
        Initialize the instance using file stem as logical name.

        The ``logical_name`` of this instance should match
        ``instance.default_lib_name``

        Parameters
        ----------
        parent : ProjectFile
            The ProjectFile node that is the
            parent of the output instance.

        Returns
        -------
        ProjectCoqLibrary
            A library whose path is same as the parent ProjectFile.
        """
        instance = cls.from_parent(
            parent,
            logical_name=LogicalName(parent.data['stem']))
        return instance


@dataclass
class LibraryAlias(ProjectCoqLibrary):
    """
    An alias to the coq library.

    Multiple logical names can be used to refer to the same library
    file. The different logical names for any file are added as this
    node.
    """

    alias: LogicalName

    def __post_init__(self):
        """
        Initialize ProjectEntity attributes.
        """
        ProjectEntity.__init__(
            self,
            self.project_file_path,
        )

    def id_component(self) -> Tuple[str, str]:
        """
        Use file entity id with logical name as id.
        """
        return "alias", str(self.alias)


@dataclass
class ProjectCoqLibraryRequirement(ProjectCoqLibrary):
    """
    A node reprensentation of a requirement extracted from a coq file.

    These nodes will be children to corresponding library nodes.
    """

    requirement: LogicalName

    def __post_init__(self):
        """
        Initialize ProjectEntity attributes.
        """
        ProjectEntity.__init__(
            self,
            self.project_file_path,
        )

    def id_component(self) -> Tuple[str, str]:
        """
        Use file entity id with logical name as id.
        """
        return "req", str(self.requirement)
