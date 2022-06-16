"""
Module for defining Library nodes.
"""
import networkx as nx
from typing import List, Union, Tuple
from pathlib import Path
from dataclasses import dataclass
from .root import Project
from .file import ProjectFile
from .logical import LogicalName

from .type import EdgeIdSet, NodeType, ProjectFileType, DataDict, NodeId, EdgeType, NodeIdSet
from prism.util.iterable import shallow_asdict


@dataclass
class ProjectCoqLibrary(ProjectFile):
    """
    A ProjectFile that can be bound to a logical name.

    The logical name is the referenece used to import
    the following library.
    """
    logical_name: LogicalName

    def __post_init__(self):
        self._node_type = NodeType.library

    def __hash__(self):
        return self.hash

    def get_data(self):
        return {'logical_name': self.logical_name}

    def init_parent(self) -> ProjectFile:
        return self.super

    @classmethod
    def init_from_node(cls, graph, node) -> 'ProjectCoqLibrary':
        super_node = cls.get_super_node(graph, node)
        super_instance = ProjectFile.init_from_node(graph, super_node)
        logical_name = graph.nodes[node]['logical_name']
        return cls.from_super(
            super_instance,
            logical_name,
        )

    @classmethod
    def init_with_local_name(cls, parent: ProjectFile) -> 'ProjectCoqLibrary':
        """
        Initialize the instance using file stem as logical name.

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
        instance = cls.from_parent(parent, logical_name=LogicalName(parent.data['stem']))
        return instance


@dataclass
class LibraryAlias(ProjectCoqLibrary):
    """
    An alias to the coq library.

    Multiple logical names can be used to
    refer to the same library file. The different
    logical names for any file are added as this node.
    """

    def __post_init__(self):
        self._node_type = NodeType.alias

    def __hash__(self):
        return self.hash

    def _connect_alias_to_library(
        self,
        graph: nx.Graph
    ) -> EdgeIdSet:
        """
        Connect this instance of alias to original library.

        Parameters
        ----------
        graph : nx.Graph
            The graph that will be modified to have the alias,
            the library, and their associated edges.

        Returns
        -------
        Set[Tuple[Hashable, Hashable, str]]
            The edge ids added to the graph.
        """
        edgetype = EdgeType.LibraryAliasToLibrary
        parent = self.parent
        key = f"{edgetype}: {hash(self)}"
        edge_id = (self.node, parent.node, key)
        edge_data = self.data
        graph.add_edge(*edge_id, **edge_data)
        return {edge_id}

    def connect(
        self,
        graph: nx.Graph,
        edgetypes: List[EdgeType],
    ) -> Tuple[NodeIdSet, EdgeIdSet]:
        """
        Connect the alias to the original library.

        In order for edges to be added the following
        values must be present in ``edgetypes``:
            EdgeType.LibraryAliasToLibrary

        Parameters
        ----------
        graph : nx.Graph
            The graph that will be modified to have the alias,
            the library, and their associated edges.
        edgetypes : List[EdgeType]
            EdgeTypes that are allowed to be added.
        """
        added_edges = set()
        if EdgeType.LibraryAliasToLibrary in edgetypes:
            added_edges = added_edges.union(self._connect_alias_to_library(graph))
        return set(), added_edges

    @classmethod
    def init_from_node(cls, graph: nx.Graph, node: NodeId) -> 'ProjectCoqLibrary':
        """
        Intialize the ProjectNode instance from a node in the graph.
        """
        super_node = cls.get_super_node(graph, node)
        super_instance = ProjectCoqLibrary.init_from_node(graph, super_node)
        logical_name = graph.nodes[node]['logical_name']
        return cls.from_super(
            super_instance,
            logical_name,
        )


@dataclass
class ProjectCoqLibraryRequirement(ProjectCoqLibrary):
    """
    A node reprensentation of a requirement extracted from a coq file.

    These nodes will be children to corresponding library nodes.
    """
    requirement: LogicalName

    def __post_init__(self):
        self._node_type = NodeType.requirement

    def __hash__(self):
        return self.hash

    def get_data(self) -> DataDict:
        """
        Return data dictionary for requirement node.

        Returns
        -------
        DataDict
            Dictionary stored in this node's attributes.
        """
        return {
            "requirement": self.requirement,
            "typename": self.typename,
        }

    @classmethod
    def init_from_node(cls, graph: nx.Graph, node: NodeId):
        """
        Intialize the ProjectNode instance from a node in the graph.
        """
        super_node = cls.get_super_node(graph, node)
        super_instance = ProjectCoqLibrary.init_from_node(graph, super_node)
        requirement = graph.nodes[node]['requirement']
        return cls.from_super(
            super_instance,
            requirement,
        )
