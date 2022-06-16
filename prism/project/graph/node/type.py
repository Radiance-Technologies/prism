"""
Module to define node type enumeration
"""

import networkx as nx
from pathlib import Path
from enum import Enum, auto
from dataclasses import dataclass
from typing import Generator, TypeVar, Tuple, Union, Dict, Optional, Any, Set, List
from prism.util.compare import Criteria



DataDict = Dict[str, Any]
NodeId = TypeVar('NodeId')
EdgeKey = TypeVar("EdgeKey")

EdgePair = Tuple[NodeId, NodeId]
KeyedEdgePair = Tuple[NodeId, NodeId, EdgeKey]
EdgeId = Union[EdgePair, KeyedEdgePair]

NodeIdSet = Set[NodeId]
EdgeIdSet = Set[EdgeId]

Node = Tuple[NodeId, Optional[DataDict]]
Edge = Tuple[EdgeId, Optional[DataDict]]


class NodeTypeCriteria(Criteria):
    """
    Criteria that  a node is of a particular type.
    """
    def __init__(self, node_type: 'NodeType', *args, **kwargs):
        Criteria.__init__(self, *args, **kwargs)
        self.node_type = node_type
        self.accepted_values = [self.node_type, self.node_type.name, self.node_type.value]

    def evaluate(self, node: NodeId, data: DataDict) -> bool:
        """Evaluate criteria on the arguments"""
        return data.get('node_type', None) in self.accepted_values



class NodeType(Enum):
    """
    An enumeration of node types.
    """
    root = auto()
    path = auto()
    library = auto()
    alias = auto()
    requirement = auto()
    iqr = auto()
    dependency = auto()

    def add_node(
        self,
        graph: nx.Graph,
        node: NodeId,
        data: DataDict,
    ) ->  Set[NodeId]:
        """
        Add edge to graph and return added edge id.

        Parameters
        ----------
        graph : nx.Graph
            A networkx graph that will be modified.
        node: NodeId
            The node identifier.
        data: DataDict
            Data dictionary of for a node.

        Returns
        -------
        Set[NodeId]
            A uniquely identifing tuple for the added node.
        """
        graph.add_node(node, node_type=self, **data)
        return {node}

    def add_nodes(
        self,
        graph: nx.Graph,
        nodes: List[Node]
    ) -> Set[NodeId]:
        """
        Add all nodes with instance node_type.

        Parameters
        ----------
        graph : nx.Graph
            A networkx graph that will be modified.
        nodes: List[NodeId]
            The node identifier.

        Returns
        -------
        Set[NodeId]
            The set of node ids added to the graph.
        """
        ids = set()
        return ids.union(self.add_node(graph, *node) for node in nodes)


    def find_nodes(self, graph: nx.Graph) -> NodeIdSet:
        """
        Find all nodes that have same node type as the instance.

        Parameters
        ----------
        graph : nx.Graph
            Graph to be search whose node data dictinaries
            as the node type stored under ``node_type``.

        Returns
        -------
        Set[NodeId]
            All nodes that match the instance's node type.
        """
        criteria = self.criteria()
        return {
            node for node, data in graph.nodes(data=True) if criteria(node, data)
        }

    @classmethod
    def criteria(cls, node_type: Union[str, int, 'NodeType']) -> bool:
        if isinstance(node_type, int):
            node_type = cls(node_type)
        elif isinstance(node_type, str):
            node_type = cls[node_type]
        elif not isinstance(node_type, cls):
            raise TypeError(
                f"Invalid type ({type(node_type)}): must be str, int, or NodeType"
            )
        return cls.NodeTypeCriteria(node_type)


class EdgeTypeCriteria(Criteria):
    """
    Criteria that  a node is of a particular type.
    """
    def __init__(self, edge_type: 'EdgeType'):
        Criteria.__init__(self)
        self.edge_type = edge_type

    def evaluate(self, edge: EdgeId, data: DataDict) -> bool:
        """Evaluate criteria on the arguments"""
        return data.get('edge_type', None) in [self.edge_type,
                                               self.edge_type.name,
                                               self.edge_type.value]


class EdgeType(Enum):
    """
    An enumeration of different EdgeTypes
    """
    ChildToParent = auto()
    ParentToChild = auto()
    DependencyToRequirement = auto()
    DependencyToLibrary = auto()
    LibraryToDependency = auto()
    """
    An edge from a libary to a dependency node.

    The source node in this edge is the library being
    dependent on, while the dependency node is just
    an placeholder node that has an edge from requirements
    to the library that satisfy them.
    """
    RequirementToDependency = auto()
    """
    An edge from a requirement to a dependency node.

    The source node in this edge is the requirement of
    some library within a project, while the dependency node
    is just an placeholder node that has an edge from
    requirements to the library that satisfy them.
    """
    IQRToProjectFile = auto()
    """
    An edge from an extracted IQR definition to a project path.

    The project path with an inward edge of this type is the path
    value given in the IQR statement (e.x. ``-R  path name``)
    """
    IQRToLibraryAlias = auto()
    """
    An edge from an extracted IQR definition to a library whose
    logical name is effected.
    """
    LibraryAliasToLibrary = auto()

    def __init__(self, *args, **kwargs):
        Enum.__init__(self)
        self.criteria = EdgeTypeCriteria(self)

    def add_edge(
        self,
        graph: nx.Graph,
        source: NodeId,
        destination: NodeId,
    ) ->  EdgeIdSet:
        """
        Add edge to graph and return added edge id.

        Parameters
        ----------
        graph : nx.Graph
            A networkx graph that will be modified.
        source : Hashable
            The source node of the added, directed (outward) edge.
        destination : Hashable
            The destination node of the added, directed (inward) edge.

        Returns
        -------
        EdgeIdSet
            A uniquely identifing tuple for the added edge.
        """
        key = self.edge_key(source, destination)
        graph.add_edge(source, destination, key=key, edge_type=self)
        return {(source, destination, key)}

    def add_edges(
        self,
        graph: nx.Graph,
        edges: List[EdgePair]
    ) -> EdgeIdSet:
        """
        Add an edge for each pair of nodes.

        Parameters
        ----------
        graph : nx.Graph
            The networkx graph that will be modified
        edges : List[Tuple[Hashable, Hashable]]
            A list of node pairs, where each pair will be used to
            construct an edge using ``add_edge``.

        Returns
        -------
        EdgeIdSet
            A set of unique tuples, each identifying the added edges.
        """
        ids = set()
        return ids.union(self.add_edge(graph, *edge) for edge in edges)

    def edge_key(self, source: NodeId, destination: NodeId) -> str:
        """
        Return the key used to identify the edge from other edges.

        Parameters
        ----------
        source : Hashable
            The source node of the added, directed (outward) edge.
        destination : Hashable
            The destination node of the added, directed (inward) edge.


        Returns
        -------
        str
            The edge ``key`` passed to:
            ``nx.Graph().add_edge(source, destination, key=key)``.
        """
        return f"{self}: {source}-->{destination}"

    def find_edges(self, graph: nx.Graph, node=None) -> EdgeIdSet:
        """
        Find edges in graph that match enumeration value.
        """
        if node is None:
            edges = graph.edges(data='edge_type', keys=True, default=None)
            edges = {(s, d, k) for s, d, k, type_ in edges if type_ is self}
        else:
            in_edges = graph.in_edges(node, data='edge_type', keys=True, default=None)
            in_edges = {(s, d, k) for s, d, k, type_ in in_edges if type_ is self}
            out_edges = graph.out_edges(node, data='edge_type', keys=True, default=None)
            out_edges = {(s, d, k) for s, d, k, type_ in out_edges if type_ is self}
            edges = in_edges.union(out_edges)
        return edges

    def find_target_nodes(
        self,
        graph: nx.Graph,
        node: NodeId,
        criteria: Optional[Criteria] = None,
    ) -> NodeIdSet:
        """
        Find and reutrn project nodes connected to a graph node.

        Parameters
        ----------
        graph : nx.Graph
            The target graph.
        node : str
            A node id of ``graph``.
        criteria : Criteria, optional
            A criteria edges must satisfy to be accepted.
        """
        if allowed_types is None:
            allowed_types = []

        if criteria is None:
            criteria: lambda edge: node in edge

        edges = self.find_edges(graph, node)

        # assume
        def connected(edge):
            if edge[0] == node:
                value = edge[1]
            elif edge[1] == node:
                value = edge[0]
            else:
                raise ValueError(
                    f"find_edges returned edge without node ({node})"
                )

        return {connected(edge) for edge in edges if criteria(edge)}

    def in_edge_iter(
        self,
        sources: List[NodeId],
        destination: NodeId,
    ) -> Generator[KeyedEdgePair, None, None]:
        """
        Generate edge tuples for each source using same destination.
        """
        for src in sources:
            yield self.tuple(src, destination)

    def out_edge_iter(
        self,
        source: NodeId,
        destinations: List[NodeId],
    ) -> Generator[KeyedEdgePair, None, None]:
        """
        Generate edge tuples for each destination using same source.
        """
        for dst in destinations:
            yield self.tuple(source, dst)

    def tuple(self, src: NodeId, dst: NodeId) -> KeyedEdgePair:
        """
        Compute unique edge tuple between src and dst.

        Parameters
        ----------
        src : Hashable
            The source node of the added, directed (outward) edge.
        dst : Hashable
            The destination node of the added, directed (inward) edge.


        Returns
        -------
        KeyedEdgePair
            A tuple containing source, destination, and key for
            a directed edge.
        """
        return (src, dst, f"{self}: {dst}"), {'type': self}

    @classmethod
    def get_edge_type(
        cls,
        graph: nx.Graph,
        *edge: Union[EdgeId, DataDict]
    ) -> 'EdgeType':
        """
        Extract the edge type stored in edge data.

        Parameters
        ----------
        graph : nx.Graph
            A graph whose edges have the "edge_type" key
            in their data dictionary.

        Returns
        -------
        EdgeType
            The edge type stored in the edge's data dictionary
            (denoting the type of relationship between nodes.)

        Raises
        ------
        TypeError
            The value of edge is not a data dictionary,
            pair of nodes, or pair of nodes and an edge key.
        """
        if len(edge) == 2:
            source, destination = edge
            edge_type = cls.get_edge_type(graph, graph[source][destination])
        elif len(edge) == 3:
            source, destination, key = edge
            edge_type = cls.get_edge_type(graph, graph[source][destination][key])
        elif len(edge) == 1:
            edge = edge[0]
            if isinstance(edge, dict):
                edge_type = edge['edge_type']
            elif isinstance(edge, tuple):
                edge_type = cls.get_edge_type(graph, edge)
        else:
            raise TypeError(
                f"Edge should be one of the following:"
                "Tuple[dict], "
                "Tuple[Hashable, Hashable], "
                "Tuple[Hashable, Hashable, str]"
            )
        return edge_type


class ProjectFileTypeNodeCriteria(Criteria):
    """
    Criteria that  a node is of a particular type.
    """
    def __init__(self, file_type: 'ProjectFileType'):
        Criteria.__init__(self)
        self.file_type = file_type

    def evaluate(self, node: NodeId, data: DataDict) -> bool:
        """Evaluate criteria on the arguments"""
        return data.get('file_type', None) in [self.file_type,
                                               self.file_type.name,
                                               self.file_type.value]

class ProjectFileTypePathCriteria(Criteria):
    """
    Criteria that a file is a particular type
    """
    def __init__(self, file_type: 'ProjectFileType'):
        Criteria.__init__(self)
        self.file_type = file_type

    def evaluate(self, path: Path) -> bool:
        """Evaluate criteria on the arguments"""
        return self.file_type.matches_pattern(path)



class ProjectFileType(Enum):
    """
    An enumeration of files types.
    """

    def __new__(cls, *args, **kwds):
        value = len(cls.__members__) + 1
        obj = object.__new__(cls)
        obj._value_ = value
        obj.path_criteria = ProjectFileTypePathCriteria(obj)
        obj.node_criteria = ProjectFileTypeNodeCriteria(obj)
        return obj

    def __init__(self, value, matches_pattern):
        self.matches_pattern = matches_pattern

    coqdirectory = (
        "coqdirectory",
        lambda file: (len(Path(file).glob("**/*.v")) > 0)
    )
    coqfile = (
        "coqfile",
        lambda file: (Path(file).suffix == ".v")
    )
    coqproject = (
        "coqproject",
        lambda file: (Path(file).stem == "_CoqProject")
    )
    makefile = (
        "makefile",
        lambda file: (Path(file).stem == "Makefile")
    )
    configure = (
        "configure",
        lambda file: (Path(file).stem == "configure")
    )

    def criteria(self, *args) -> bool:
        """
        Evaluate the criteria inferred by argument shape.
        """
        if len(args) == 2:
            return self.node_criteria(*args)
        else:
            return self.path_criteria(*args)

    def find_files(self, graph: nx.Graph) -> Set[NodeId]:
        """
        Find all nodes that have same node type as the instance.

        Parameters
        ----------
        graph : nx.Graph
            Graph to be search whose node data dictinaries
            as the node type stored under ``file_type``.

        Returns
        -------
        Set[file_type]
            All nodes that match the instance's node type.
        """
        return {
            node for node, data in graph.nodes(data=True) if self.criteria(node, data)
        }

    @classmethod
    def infer(cls, path: Path) -> Optional['ProjectFileType']:
        """
        Infer file type from path.

        Returns
        -------
        ProjectFileType, optional:
            Returns the inferred file type, or None.
        """
        for file_type in cls:
            if file_type.criteria(path):
                return file_type