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
Module to define and create project graph.
"""
from typing import List, Tuple

from prism.project.graph.entity import (
    EdgeType,
    LibraryAlias,
    LogicalName,
    ProjectCoqDependency,
    ProjectCoqLibrary,
    ProjectCoqLibraryRequirement,
    ProjectExtractedIQR,
    ProjectFile,
    ProjectRoot,
)
from prism.project.graph.node import ProjectNode, ProjectNodeGraph


class ProjectGraph(ProjectNodeGraph):
    """
    A graph structure that connects project components.
    """

    node_types: List[ProjectNode] = [
        ProjectRoot,
        ProjectFile,
        ProjectCoqLibrary,
        LibraryAlias,
        ProjectCoqLibraryRequirement,
        ProjectExtractedIQR,
        ProjectCoqDependency,
    ]

    def __init__(self, *args, **kwargs):
        super(ProjectGraph, self).__init__(*args, **kwargs)

    def separate_dependencies(self) -> Tuple[List[ProjectNode]]:
        """
        Find all local dependencies and cross project dependencies.

        Returns
        -------
        local: List[ProjectNode]
            These dependencies are requirements that have libraries
            contained in the proejct files.
        cross: List[ProjectNode]
            These dependencies are requirements that have libraries
            contained are likely in another project.
        unknown: List[ProjectNode]
            These dependencies are requirements with no matching
            libraries.
        """
        cross = []
        local = []
        unknown = []
        edgetype = EdgeType.DependencyToLibrary
        for dependency_node in self.self.nodes_from_graph(ProjectCoqDependency):
            found = False
            dependency = dependency_node.entity
            dependency_root_node = dependency_node.get_root_node()

            # Get dependency libraries
            edges = self.out_edges(dependency_node.node_id, data='edge_type')
            lib_edges = list(filter(lambda edge: edge[2] is edgetype, edges))
            lib_nodeids = [lib for _, lib, _ in lib_edges]
            lib_nodes = [self.init_node(nodeid) for nodeid in lib_nodeids]
            keys = [node.entity.project_name for node in lib_nodes]
            if dependency.project_name in keys:
                found = True
                library_node = lib_nodes[keys.index(dependency.project_name)]
                local.append(
                    (
                        dependency_root_node,
                        lib_nodes[keys.index(dependency.project_name)],
                        library_node.get_root_node()))
            elif len(keys) == 1:
                found = True
                library_node = lib_nodes[0]
                cross.append(
                    (dependency_root_node,
                     library_node.get_root_node()))
            elif len(keys) > 1:
                raise ValueError(
                    "More than 1 cross project library identified"
                    "for a single dependency.")
            else:
                # Check if dependency could be cross project
                logical = dependency.logical_name
                for rootid, variant_names in self._root_variants.items():
                    if found:
                        continue
                    elif logical.parts[0] in variant_names:
                        found = True
                    else:
                        cls = ProjectExtractedIQR
                        for iqr in self.nodes_of_type(rootid, cls):
                            if found:
                                continue
                            names = list(
                                LogicalName(
                                    iqr.entity.iqr_name).root_to_stem_generator)
                            if any(logical.is_relative_to(n) for n in names):
                                found = True
                    if found:
                        root_node = self.init_node(rootid)
                        cross.append((dependency_root_node, root_node))
                if not found:
                    unknown.append((dependency_root_node))
        return local, cross, unknown
