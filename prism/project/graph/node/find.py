"""
Module for a node finding utility
"""
import networkx as nx
from pathlib import Path
from typing import List, Tuple

from .logical import LogicalName
from .type import EdgeId, NodeId, EdgeType, NodeIdSet
from .base import ProjectNode
from .file import ProjectFile
from .library import LibraryAlias, ProjectCoqLibrary, ProjectCoqLibraryRequirement
from .iqr import ProjectExtractedIQR
from .dependency import ProjectCoqDependency
from prism.util.compare import Criteria


class NodeIsSourceCriteria(Criteria):
    """
    Criteria that given node is the source node in the edge.
    """
    def __init__(self, query_node: NodeId, *args, **kwargs):
        super(NodeIsSourceCriteria, self).__init__(*args, **kwargs)
        self.buffer["query_node"] = query_node

    def evaluated(self, edge: EdgeId) -> bool:
        return (edge[0] == self.buffer["query_node"])


class NodeIsDestinationCriteria(Criteria):
    """
    Criteria that given node is the destination node in the edge.
    """
    def __init__(self, query_node: NodeId, *args, **kwargs):
        super(NodeIsSourceCriteria, self).__init__(*args, **kwargs)
        self.buffer["query_node"] = query_node

    def evaluated(self, edge: EdgeId) -> bool:
        return (edge[1] == self.buffer["query_node"])


class NodeFinder:

    def __init__(self, graph):
        self.graph = graph

    @classmethod
    def all_libraries(cls, graph) -> NodeIdSet:
        """
        Get all library nodes in the graph.
        """
        return ProjectCoqDependency.nodes_from_graph(graph)

    @classmethod
    def all_dependencies(cls, graph) -> NodeIdSet:
        """
        Get all dependency nodes in the graph.
        """
        return ProjectCoqDependency.nodes_from_graph(graph)

    @classmethod
    def all_requirements(cls, graph) -> NodeIdSet:
        """
        Get all requiremsnt nodes in the graph.
        """
        return ProjectCoqLibraryRequirement.nodes_from_graph(graph)


    @classmethod
    def all_aliases(cls, graph) -> NodeIdSet:
        """
        Get all library alias nodes in the graph.
        """
        libraries = cls.libraries(graph)
        aliases = set()
        for library in libraries:
            aliases = aliases.union(cls.library_aliases(graph, library))
        return aliases

    @classmethod
    def children(cls, graph, node: NodeId) -> NodeIdSet:
        """
        Return all children of the given node.

        A parent will have a inward edges from each child to itself
        with edge_type == EdgeType.ChildtoParent.
        """
        edges = graph.in_edges(node, data='edge_type', default=None)
        nodes = set()
        for _, destination, edge_type in edges:
            if edge_type == EdgeType.ParentToChild:
                nodes.add(destination)
        return nodes
    
    @classmethod
    def find_alias_from_library(
        cls,
        graph: nx.Graph,
        library_node: NodeId,
    ) -> List[LibraryAlias]:
        """
        Find the LibraryAlias nodes for a ProjectCoqLibrary node.
        """
        Criteria
        EdgeType.LibraryAliasToLibrary.find_target_nodes(graph, library_node)
        edges = EdgeType.LibraryAliasToLibrary.find_edges(graph, library_node)
        nodes =  [node for node, l, _ in edges if l == node]
        return [LibraryAlias.init_from_node(graph, node) for node in nodes]

    @classmethod
    def find_effected_libraries_by_iqr(
        cls,
        graph: nx.Graph,
        iqr_node: NodeId
    ) -> Tuple[ProjectFile, ProjectCoqLibrary, LogicalName]:
        """
        Find the libraries that require adding aliases due to iqr.

        The following explanation uses the following example IQR
        flag:  ``-R ./lib/comp Comp``.

        All subdirectories and files of ``./lib/comp`` recursively
        can be loaded using a logical name that starts with ``Comp``.
        This method will return the corresponding ProjectFile and 
        ProjectCoqLibrary instances, as well as the logical name
        that will be used to define a LibraryAlias node.
        """
        iqr = ProjectExtractedIQR.init_from_node(graph, iqr_node)
        path_node = cls.find_iqr_path(graph, iqr_node)
        if path_node is None:
            return set()
        relative_path = graph.nodes[path_node]['relative']
        files_nodes = ProjectFile.nodes_from_graph(
            graph,
            lambda n, d: d['relative'].is_relative_to(relative_path)
        )

        # Convert the LogicalName given in the IQR argument
        # in to a path. This is done to replace relative
        # path of the files, so that the relative paths
        # can be used to construct the new library aliases.
        modified_root = Path(*str(iqr.iqr_name).split('.'))
        effected = set()
        for file_node in files_nodes:
            library = cls.projectcoqlibrary_from_projectfile(graph, file_node.node)
            current_path = graph.nodes[file_node]['relative']
            # Construct a new logical name by replaceing the root
            # in current path with modified root. The root
            # being overlap in path between iqr and project file.
            if library is not None:
                modified_path = current_path.relative_to(relative_path)
                new_path = modified_root / modified_path
                new_name = LogicalName.from_physical_path(new_path)
                effected.add((file_node, library, new_name))
        return effected    

    @classmethod
    def find_iqr_library(
        cls,
        graph: nx.Graph,
        iqr_node: NodeId
    ) -> ProjectCoqLibrary:
        """
        Find the library corresponding to logical name in iqr.

        The following explanation uses the following example IQR
        flag:  ``-R ./lib/comp Comp``.

        The IQR argument implies the existance of directory
        ``./lib/comp`` that is logically bound to ``Comp``. This method
        will find the ProjectCoqLibrary with ``logical_name == Comp``
        that is a child of ProjectFile corresponding to ``./lib/comp``.
        """
        iqr = ProjectExtractedIQR.init_from_node(graph, iqr_node)
        iqr_stem = iqr.iqr_path.stem
        file_node = cls.find_iqr_path(graph, iqr_node)
        library_node = cls.find_library_from_file(graph, file_node.node)
        return ProjectCoqLibrary.init_from_node(graph, library_node)

    @classmethod
    def find_iqr_path(
        cls,
        graph: nx.Graph,
        iqr_node: NodeId
    ) -> ProjectFile:
        """
        Find the ProjectFile correpsonding to path in iqr node.

        The following explanation uses the following example IQR
        flag:  ``-R ./lib/comp Comp``.

        The IQR argument implies the existance of directory
        ``./lib/comp`` that is logically bound to ``Comp``. This method
        will find the ProjectFile coresponding to ``./lib/comp``.
        """
        iqr = ProjectExtractedIQR.init_from_node(graph, iqr_node)    
        coqproject_ = iqr.super
        relative_path = coqproject_.project_file_path.parent / iqr.iqr_path
        relative_path = relative_path.relative_to(iqr.project_path)
        files_nodes = ProjectFile.nodes_from_graph(
            graph,
        )
        for file_node in files_nodes:
            if graph.nodes[file_node]['relative'] == relative_path:
                return file_node

    @classmethod
    def find_library_from_alias(
        cls,
        graph: nx.Graph,
        node: NodeId
    ) -> ProjectCoqLibrary:
        """
        Find the library from one of it's aliases.
        """
        edges = EdgeType.LibraryAliasToLibrary.find_edges(graph, node)
        for alias, library, _ in edges:
            if alias == node:
                break
        return ProjectCoqLibrary.init_from_node(graph, library)

    @classmethod
    def find_library_from_file(
        cls,
        graph: nx.Graph,
        node: NodeId
    ) -> ProjectCoqLibrary:
        """
        Get ProjectCoqLibrary node connected to a ProjectFile node.
        """
        children = cls.children(graph, node)
        library = None
        for child in children:
            if graph.node[child]['type'] == ProjectCoqLibrary:
                if library is None:
                    library = child
                else:
                    raise ValueError(
                        "Multiple libraries found connected to project file"
                    )
        return ProjectCoqLibrary.init_from_node(graph, library)

    @classmethod
    def library_aliases(
        cls,
        graph: nx.Graph,
        node: NodeId
    ) -> List[LibraryAlias]:
        """
        Find all alias nodes of a library.
        """
        edges = EdgeType.LibraryAliasToLibrary.find_edges(graph)
        return {alias for alias, library, _ in edges if node == library}

    @classmethod
    def library_requirements(
        cls,
        graph: nx.Graph,
        node: NodeId
    ) -> List[ProjectCoqLibraryRequirement]:
        """
        Find all requirement nodes of a library
        """
        edges = EdgeType.ParentToChild.find_edges(graph, node)
        return {child_req for parent, child_req, _ in edges if parent == node}

    @classmethod
    def parent(
        cls,
        graph: nx.Graph,
        node: NodeId
    ) -> ProjectNode:
        """
        Return node id of the parent of the given node.

        A parent will have a outward edge from itself to the child
        with edge_type == EdgeType.ParentToChild
        """
        edges = graph.out_edges(node, data='edge_type', default=None)
        nodes = set()
        for _, destination, edge_type in edges:
            if edge_type == EdgeType.ChildToParent:
                nodes.add(destination)
        return nodes

    @classmethod
    def requirement_resolution(
        cls,
        graph: nx.Graph,
        node: NodeId
    ) -> NodeIdSet:
        """
        Find the dependency node for a given requirement node.
        """
        edges = EdgeType.DependencyToRequirement.find_edges(graph)
        return {dep for dep, req, _ in edges if req == node}
