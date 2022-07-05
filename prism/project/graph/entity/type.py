"""
Module to define node type enumeration.
"""

from enum import Enum, auto
from pathlib import Path
from typing import (
    Any,
    Dict,
    Generator,
    List,
    Optional,
    Set,
    Tuple,
    TypeVar,
    Union,
)

import networkx as nx

from prism.util.criteria import Criteria

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


class EdgeType(Enum):
    """
    An enumeration of different EdgeTypes.
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
            edges = {(s,
                      d,
                      k) for s,
                     d,
                     k,
                     type_ in edges if type_ is self}
        else:
            in_edges = graph.in_edges(
                node,
                data='edge_type',
                keys=True,
                default=None)
            in_edges = {
                (s,
                 d,
                 k) for s,
                d,
                k,
                type_ in in_edges if type_ is self
            }
            out_edges = graph.out_edges(
                node,
                data='edge_type',
                keys=True,
                default=None)
            out_edges = {
                (s,
                 d,
                 k) for s,
                d,
                k,
                type_ in out_edges if type_ is self
            }
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
        if criteria is None:

            def criteria(edge):
                return node == edge[0]

        edges = self.find_edges(graph, node)

        # assume
        def connected(edge):
            if edge[0] == node:
                value = edge[1]
            elif edge[1] == node:
                value = edge[0]
            else:
                raise ValueError(
                    f"find_edges returned edge without node ({node})")
            return value

        return {edge[1] for edge in edges if criteria(edge)}

    def in_edge_iter(
        self,
        sources: List[NodeId],
        destination: NodeId,
    ) -> Generator[KeyedEdgePair,
                   None,
                   None]:
        """
        Generate edge tuples for each source using same destination.
        """
        for src in sources:
            yield self.tuple(src, destination)

    def out_edge_iter(
        self,
        source: NodeId,
        destinations: List[NodeId],
    ) -> Generator[KeyedEdgePair,
                   None,
                   None]:
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
        src : NodeId
            The source node of the added, directed (outward) edge.
        dst : NodeId
            The destination node of the added, directed (inward) edge.


        Returns
        -------
        KeyedEdgePair
            A tuple containing source, destination, and key for
            a directed edge.
        """
        key = self.edge_key(src, dst)
        return (src,
                dst,
                key,
                {
                    "edge_type": self
                })


class ProjectFileTypeNodeCriteria(Criteria):
    """
    Criteria that  a node is of a particular type.
    """

    def __init__(self, file_type: 'ProjectFileType'):
        Criteria.__init__(self)
        self.file_type = file_type

    def evaluate(self, node: NodeId, data: DataDict) -> bool:
        """
        Evaluate criteria on the arguments.
        """
        values = [self.file_type, self.file_type.name, self.file_type.value]
        return data.get('file_type', None) in values


class ProjectFileTypePathCriteria(Criteria):
    """
    Criteria that a file is a particular type.
    """

    def __init__(self, file_type: 'ProjectFileType'):
        Criteria.__init__(self)
        self.file_type = file_type

    def evaluate(self, path: Path) -> bool:
        """
        Evaluate criteria on the arguments.
        """
        return self.file_type.matches_pattern(path)


class ProjectFileType(Enum):
    """
    An enumeration of files types.

    Attributes:
    ----------
    matches_pattern : Callable[[Path], bool]
        Function that identifes if input file matches
        the filetype.
    """  # noqa: D406

    def __new__(cls, *args, **kwds):
        """
        Initialize the enumeration instance with criteria functions.
        """
        value = len(cls.__members__) + 1
        obj = object.__new__(cls)
        obj._value_ = value
        obj.path_criteria = ProjectFileTypePathCriteria(obj)
        obj.node_criteria = ProjectFileTypeNodeCriteria(obj)
        return obj

    def __init__(self, value, matches_pattern):
        """
        Initialize the enumeration instance.
        """
        self.matches_pattern = matches_pattern

    coqdirectory = (
        "coqdirectory",
        lambda file: (len(list(Path(file).glob("**/*.v"))) > 0))
    makedirectory = (
        "makedirectory",
        lambda file: (
            len(
                [
                    p for p in Path(file).glob("**/*Makefile*")
                    if p.stem == "Makefile"
                ]) > 0))
    coqfile = ("coqfile", lambda file: (Path(file).suffix == ".v"))
    coqproject = ("coqproject", lambda file: (Path(file).stem == "_CoqProject"))
    makefile = ("makefile", lambda file: (Path(file).stem == "Makefile"))
    configure = ("configure", lambda file: (Path(file).stem == "configure"))

    def criteria(self, *args) -> bool:
        """
        Evaluate the criteria inferred by argument shape.

        Parameters
        ----------
        args: Union[str, Path, Tuple[NodeId, DataDict]]
            If a single value is given, it's assumed to be a
            path. Otherwise a 2-tuple of NodeId and DataDict
            must be given.
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
        Set[NodeId]
            All nodes that match the instance's node type.
        """
        return {
            node for node,
            data in graph.nodes(data=True) if self.criteria(node,
                                                            data)
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
