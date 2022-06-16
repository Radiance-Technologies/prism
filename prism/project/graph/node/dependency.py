"""
Module for representing coq dependencies.
"""
import networkx as nx
from typing import List, Tuple
from dataclasses import dataclass
from .library import LibraryAlias, ProjectCoqLibrary, ProjectCoqLibraryRequirement
from .root import Project
from .logical import LogicalName
from .type import EdgeIdSet, NodeIdSet, NodeType, DataDict, NodeId, EdgeType


@dataclass
class ProjectCoqDependency(Project):
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
        self._node_type = NodeType.dependency

    def __hash__(self):
        return self.hash

    def _connect_to_requirements(
        self,
        graph: nx.Graph,
        requirements: NodeIdSet
    ) -> Tuple[NodeIdSet, EdgeIdSet]:
        """
        Connect this dependency to matching requirements.

        Parameters
        ----------
        graph : nx.Graph
            Graph containing both this dependency and the
            given requirements.
        requirements : Set[str]
            Requirement nodes that will have edges added to them
            connected to this node.

        Returns
        -------
        Tuple[Set[Hashable], Set[Tuple[Hashable, Hashable, str]]]
            The sets of added nodes and edges, respectively.
        """
        added_edges = set()
        edges = EdgeType.DependencyToRequirement.out_edge_iter(self.node, requirements)
        for edge_id, edge_data in edges:
            graph.add_edge(*edge_id, **edge_data)
            added_edges.add(edge_id)
        return set(), added_edges

    def _connect_to_libraries(
        self,
        graph: nx.Graph,
        libraries: NodeIdSet
    ) -> Tuple[NodeIdSet, EdgeIdSet]:
        """
        Add edges from this node to matching libraries.

        Parameters
        ----------
        graph : nx.Graph
            Graph containing both this dependency and the
            given requirements.
        libraries : Set[str]
            These libraries satisfy the requirements that
            share an edge with this dependency node.

        Returns
        -------
        Tuple[Set[Hashable], Set[Tuple[Hashable, Hashable, str]]]
            The sets of added nodes and edges, respectively.
        """
        added_edges = set()
        edges = EdgeType.DependencyToLibrary.out_edge_iter(self.node, libraries)
        for edge_id, edge_data in edges:
            graph.add_edge(*edge_id, **edge_data)
            added_edges.add(edge_id)
        return set(), added_edges

    def _connect_from_libraries(
        self,
        graph: nx.Graph,
        libraries: NodeIdSet
    ) -> Tuple[NodeIdSet, EdgeIdSet]:
        """
        Add edges from matching libraries to this node.

        Parameters
        ----------
        graph : nx.Graph
            Graph containing both this dependency and the
            given requirements.
        libraries : Set[str]
            These libraries satisfy the requirements that
            share an edge with this dependency node.

        Returns
        -------
        Tuple[Set[Hashable], Set[Tuple[Hashable, Hashable, str]]]
            The sets of added nodes and edges, respectively.
        """

        added_edges = set()
        edges = EdgeType.LibraryToDependency.out_edge_iter(self.node, libraries)
        for edge_id, edge_data in edges:
            graph.add_edge(*edge_id, **edge_data)
            added_edges.add(edge_id)
        return set(), added_edges

    def connect(
        self,
        graph: nx.Graph,
        edgetypes: List[EdgeType],
    ) -> Tuple[NodeIdSet, EdgeIdSet]:
        """
        Connect the IQR node to other nodes in the graph.

        The following edge types can be added:
            EdgeType.DependencyToRequirement
                --> Connect this node to requirement nodes
                    that established the dependency
            EdgeType.DependencyToLibrary
                --> Connect this node to libraries that
                    that resolve the requirements connected
                    to this node, using an outward edge
                    from this node.
            EdgeType.LibraryToDependency
                --> Connect this node to libraries that
                    that resolve the requirements connected
                    to this node, using an inward edge
                    into this node.
        """
        added_nodes = set()
        added_edges = set()

        if EdgeType.DependencyToRequirement in edgetypes:
            reqs = self.find_matching_library_requirement(graph)
            nodes_, edges_ = self._connect_to_requirements(graph, reqs)
            if nodes_ is not None:
                added_nodes = added_nodes.union(nodes_)
            if edges_ is not None:
                added_edges = added_edges.union(edges_)
        if EdgeType.DependencyToLibrary in edgetypes:
            libraries = self.find_matching_library(graph)
            nodes_, edges_ = self._connect_to_libraries(graph, libraries)
            if nodes_ is not None:
                added_nodes = added_nodes.union(nodes_)
            if edges_ is not None:
                added_edges = added_edges.union(edges_)
        if EdgeType.LibraryToDependency in edgetypes:
            libraries = self.find_matching_library(graph)
            nodes_, edges_ = self._connect_from_libraries(graph, libraries)
            if nodes_ is not None:
                added_nodes = added_nodes.union(nodes_)
            if edges_ is not None:
                added_edges = added_edges.union(edges_)

        return added_nodes, added_edges

    def find_matching_library_requirement(self, graph: nx.Graph) -> NodeIdSet:
        """
        Find requirements that match this dependency name.

        Search the graph for requirements that have the same
        logical name as this dependency.
        """
        return ProjectCoqLibraryRequirement.nodes_from_graph(
            graph,
            lambda n, d: self.logical_name == d.get('requirement', None),
        )

    def find_matching_library(self, graph: nx.Graph) -> NodeIdSet:
        """
        Find libraries that match this dependency name.

        Search the graph for libraries that have the same
        logical name as this dependency.
        """

        def match(_, d):
            name = d.get('logical_name', None)
            if name is not None:
                return self.logical_name in name.shortnames
            else:
                return False

        libraries = ProjectCoqLibrary.nodes_from_graph(
            graph,
            match,
        )
        aliases = LibraryAlias.nodes_from_graph(
            graph,
            match,
        )
        return libraries.union(aliases)

    def get_data(self) -> DataDict:
        """
        Return data dictionary for depednency node.

        Returns
        -------
        DataDict
            Dictionary stored in this node's attributes.
        """
        return {
            'logical_name': self.logical_name,
            "typename": self.typename, 
        }

    def init_parent(self) -> Project:
        """
        Return the parent Project instance.

        Returns
        -------
        Project
            The Project instance that represents the project that the
            requires the dependencies.
        """
        return self.super

    @classmethod
    def init_from_node(cls, graph: nx.Graph, node: NodeId) -> 'ProjectCoqDependency':
        """
        Intialize the ProjectNode instance from a node in the graph.
        """
        super_node = cls.get_super_node(graph, node)
        super_instance = Project.init_from_node(graph, super_node)
        logical_name = graph.nodes[node]['logical_name']
        return cls.from_super(
            super_instance,
            logical_name
        )
