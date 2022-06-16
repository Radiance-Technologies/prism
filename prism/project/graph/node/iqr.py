"""
Module defining node for extract IQR flags.
"""
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Literal, Optional, Tuple, TypeVar, Union

import networkx as nx

from .file import ProjectFile
from .library import LibraryAlias, ProjectCoqLibrary
from .logical import LogicalName
from .type import DataDict, EdgeIdSet, EdgeType, NodeId, NodeIdSet, NodeType

IQR_FLAG = Literal["I", "Q", "R"]
"""
The letter value of argument for a project's IQR arguments.
"""
IQR_PHYSICAL_PATH = TypeVar('IQR_PHYSICAL_PATH')
"""
Path passed as first of two arguments -Q and -R and only
argument passed to -I.
"""
IQR_BOUND_NAME = TypeVar('IQR_BOUND_NAME')
"""
Name passed as second argument -R and -Q that deteremines
access of libraries found in subdirectory(ies) of
first argument to -R and -Q.
"""
IQR_BINDING_ARGUMENT = Tuple[IQR_PHYSICAL_PATH, IQR_BOUND_NAME]
"""
A tuple of the physical and bound name passed to -R or -Q.
"""
IQR_INCLUDE_ARGUMENT = Tuple[IQR_PHYSICAL_PATH, None]
"""
A tuple of one element, the path passed to -I.
"""
IQR_ARGUMENT = Union[IQR_INCLUDE_ARGUMENT, IQR_BINDING_ARGUMENT]
"""
An instance that could be either arguments passed to -R, -Q, or -I.
"""

I_FLAG_REGEX = re.compile(r"-I (?P<src>\S+)")
Q_FLAG_REGEX = re.compile(r"-Q (?P<src>\S+)(\s*|\s+)(?P<tgt>\S+)")
R_FLAG_REGEX = re.compile(r"-R (?P<src>\S+)(\s*|\s+)(?P<tgt>\S+)")
R_FLAG_REGEX = re.compile(
    r"-R\s+(?P<src>\S+)(^(?!.*sqlbuddy.*).*$|,|\s+)(?P<tgt>\S+)")
IQR_REGEX = {
    'I': I_FLAG_REGEX,
    'Q': Q_FLAG_REGEX,
    'R': R_FLAG_REGEX,
}


def extract_iqr_flag_values(
    string: str,
    flag: IQR_FLAG,
) -> List[IQR_ARGUMENT]:
    """
    Extract paths and logical names using IQR arguments.

    Parameters
    ----------
    string : str
        String that could contain IQR arguments.
    flag : IQR_FLAG
        The letter in the argument -(I|Q|R).

    Returns
    -------
    Union[IQR_ARGUMENT]
        Extract tuples for value for each instance of
        flag usage. 2 values in each tuple for -R and -Q,
        while 1 value in each tuple for -I.
    """
    matches: List[IQR_ARGUMENT] = []
    for match in re.finditer(IQR_REGEX[flag], string):
        group_dict = match.groupdict()
        if 'tgt' in group_dict:
            item: IQR_BINDING_ARGUMENT = (group_dict['src'], group_dict['tgt'])
        else:
            item: IQR_INCLUDE_ARGUMENT = (group_dict.get('src'), None)
        matches.append(item)
    return matches


class IQRFlag(Enum):
    NONE = None
    I = "I"  # noqa: E741
    Q = "Q"
    R = "R"

    @property
    def regex(self):
        return IQR_REGEX[self.value]

    def parse_string(self, string: str) -> List[IQR_ARGUMENT]:
        return extract_iqr_flag_values(string, self.value)


def extract_from_file(file: str):
    with open(file, "r") as f:
        data = f.read()
    return {
        flag: flag.parse_string(data)
        for flag in IQRFlag
        if flag is not IQRFlag.NONE
    }


@dataclass
class ProjectExtractedIQR(ProjectFile):
    """
    A node representing the extract IQR flags from a file.

    This node is specifically the children of _CoqProject files or
    MakeFiles which will have build commands that are the IQR flags.
    """
    iqr_path: Path
    iqr_name: LogicalName
    iqr_flag: IQRFlag

    def __post_init__(self):
        self._node_type = NodeType.iqr

    def __hash__(self):
        return self.hash

    def _add_aliases_to_graph(
        self,
        graph: nx.Graph,
        edgetypes: Optional[List[EdgeType]] = None) -> Tuple[NodeIdSet,
                                                             EdgeIdSet]:
        """
        Add all derived logical names as LibraryAlias nodes.

        Parameters
        ----------
        graph : nx.Graph
            The graph that will be modified to have the alias,
            the library, and their associated edges.
        edgetypes : List[EdgeType]
            EdgeTypes that are allowed to be added.

        Returns
        -------
        Tuple[Set[Hashable], Set[Tuple[Hashable, Hashable, str]]]
            The sets of added nodes and edges, respectively.
        """
        added_edges = set()
        added_nodes = set()
        node_name_pairs = self.find_effected_libraries(graph)
        for node, new_name in iter(node_name_pairs):
            library = ProjectCoqLibrary.init_from_node(graph, node)
            alias = LibraryAlias.from_parent(library, logical_name=new_name)
            alias_nodes, alias_edges = alias.add_to_graph(
                graph,
                add_parent=False,
                connect_parent=False,
                edgetypes=edgetypes,
            )
            added_edges = added_edges.union(alias_edges)
            added_nodes = added_nodes.union(alias_nodes)
        return added_nodes, added_edges

    def _connect_to_aliases(
        self,
        graph: nx.Graph,
        alias_nodes: NodeIdSet,
    ) -> Tuple[NodeIdSet,
               EdgeIdSet]:
        """
        Add edges between this node and the added alias nodes.

        Parameters
        ----------
        graph : nx.Graph
            The graph that will be modified to have the alias,
            the library, and their associated edges.
        alias_nodes : List[EdgeType]
            Nodes added via ``_add_aliases_to_graph``.

        Returns
        -------
        Tuple[NodeIdSet, EdgeIdSet]
            The sets of added nodes and edges, respectively.
        """
        added_edges = set()
        edgetype = EdgeType.IQRToLibraryAlias
        edges = edgetype.out_edge_iter(self.node, alias_nodes)
        for edge_id, edge_data in iter(edges):
            graph.add_edge(*edge_id, **edge_data)
            added_edges.add(edge_id)
        return set(), added_edges

    def _connect_to_bound_paths(
            self,
            graph: nx.Graph,
            path_nodes: NodeIdSet) -> Tuple[NodeIdSet,
                                            EdgeIdSet]:
        """
        Add edges between this node and referenced ProjecFiles.

        The IQR flags contain path arguments, and it is the equivilant
        nodes to those path arguments that will connected to this
        instance.

        Parameters
        ----------
        graph : nx.Graph
            The graph that will be modified to have the alias,
            the library, and their associated edges.
        path_nodes : List[NodeIdSet]
            Paths found matching the path argument of the
            extracted IQR.

        Returns
        -------
        Tuple[NodeIdSet, EdgeIdSet]
            The sets of added nodes and edges, respectively.
        """
        added_edges = set()
        edgetype = EdgeType.IQRToProjectFile
        edges = edgetype.out_edge_iter(self.node, path_nodes)
        for edge_id, edge_data in iter(edges):
            graph.add_edge(*edge_id, **edge_data)
            added_edges.add(edge_id)
        return set(), added_edges

    def connect(self,
                graph: nx.Graph,
                edgetypes: List[EdgeType]) -> Tuple[NodeIdSet,
                                                    EdgeIdSet]:
        """
        Connect the IQR node to other nodes in the graph.

        The following edge types can be added:
            EdgeType.IQRToProjectFile
                --> Connect this node to the path referenced
                    in the IQR argument
            EdgeType.LibraryAliasToLibrary
                --> Connect aliases produced as result of this IQR
                    to the original libraries.
            EdgeType.IQRToLibraryAlias
                --> Connect this node to the aliases produced as
                    result of this IQR.
        """
        added_nodes = set()
        added_edges = set()

        if EdgeType.IQRToProjectFile in edgetypes:
            path_nodes = self.find_path_in_graph(graph)
            added_paths = self._connect_to_bound_paths(graph, path_nodes)
            nodes_, edges_ = added_paths
            if nodes_ is not None:
                added_nodes = added_nodes.union(nodes_)
            if edges_ is not None:
                added_edges = added_edges.union(edges_)

        if EdgeType.LibraryAliasToLibrary in edgetypes:
            alias_to_libray_edge = EdgeType.LibraryAliasToLibrary
        else:
            alias_to_libray_edge = None

        if EdgeType.IQRToLibraryAlias in edgetypes:
            path_nodes = self.find_path_in_graph(graph)

            added_aliases, alias_edges = self._add_aliases_to_graph(graph, edgetypes=(alias_to_libray_edge,))
            if added_aliases is not None:
                added_nodes = added_nodes.union(added_aliases)
            if alias_edges is not None:
                added_edges = added_edges.union(alias_edges)

            _, iqr_to_alias = self._connect_to_aliases(graph, added_aliases)
            if iqr_to_alias is not None:
                added_edges = added_edges.union(iqr_to_alias)
        return added_nodes, added_edges

    def get_data(self) -> DataDict:
        """
        Return data dictionary for iqr node.

        Returns
        -------
        DataDict
            Dictionary stored in this node's attributes.
        """
        return {
            'iqr_path': self.iqr_path,
            'iqr_name': self.iqr_name,
            'iqr_flag': self.iqr_flag,
        }

    def init_parent(self) -> ProjectFile:
        """
        Return the parent ProjectFile instance.

        Returns
        -------
        ProjectFile
            The ProjectFile instance that represents
            the file that the IQR flags were extracted from.
        """
        return self.super

    def find_effected_libraries(self, graph) -> NodeIdSet:
        """
        Find all libraries in the graph that are effected by the IQR.

        Effected libraries are those that can be imported, exported,
        or loaded in coq using the logical alias given in the IQR
        argument.

        Returns
        -------
        Set[str]
            Names of nodes corresponding to libraries who require
            aliases to be added.
        """
        effected = set()
        file_node = None
        library_node = None
        start_path = None
        # find the node of the path referenced in the IQR argument
        # ex: -R ./lib/comp Comp  -->  find "./lib/comp" in graph.
        for _, node, data in graph.out_edges(self.node, data=True, default={}):
            if data.get('type', None) is EdgeType.IQRToProjectFile:
                file_node = ProjectCoqLibrary.get_parent_node(graph, node)
                start_path = graph.nodes[node]['relative']
                break

        # If node, then no libraries effected.
        if file_node is None:
            return effected

        # Find the library node associated with the IQR flag.
        # ex: -R ./lib/comp Comp  -->  find Comp in graph.

        for _, node, data in graph.out_edges(file_node, data=True, default={}):
            if data.get('type', None) is EdgeType.ParentToChild:
                library_node = node
                current_name = graph.nodes[library_node]['logical_name']
                break

        if library_node is None:
            return effected

        effected.add((library_node, current_name, self.iqr_path))

        # Find all files that are relative to the starting path.
        # These will be connected to libraries that are effected.
        nodes = ProjectCoqLibrary.nodes_from_graph(
            graph,
            lambda n,
            d: d['relative'].is_relative_to(start_path),
        )

        # Convert the LogicalName given in the IQR argument
        # in to a path. This is done to replace relative
        # path of the files, so that the relative paths
        # can be used to construct the new library aliases.
        iqr_root = Path(*self.iqr_name.parts)

        def compute_new_name(node):
            current = graph.nodes[node]['logical_name']
            rel_to_iqr_root = current.relative_to(start_path)
            rel_path = iqr_root / rel_to_iqr_root
            new_name = LogicalName.from_physical_path(rel_path)
            return new_name

        effected.union(set((node, compute_new_name(node)) for node in nodes))
        return effected

    def find_path_in_graph(self, graph: nx.Graph) -> NodeIdSet:
        """
        Find the paths that match the path component of the IQR.

        The set of returned paths are all ProjectFile nodes that match
        the path component of the IQR flag.
        """
        iqr_path = self.iqr_path
        file_relative = self.parent.data['parent'] / self.iqr_path
        file_relative = file_relative.relative_to(self.project_path)

        # look for any path that has the iqr path as a tail.
        def lazy_match(node, data):
            return path_is_matches_ending(iqr_path, data['relative'])

        # Return true if any of the conditions for a match are met.
        def matches(node, data):
            rel = data['relative']
            return (
                str(rel) == str(self.iqr_path)
                or str(rel) == str(file_relative) or lazy_match(node,
                                                                data))

        return ProjectFile.nodes_from_graph(
            graph,
            matches,
        )

    @classmethod
    def init_from_node(
            cls,
            graph: nx.Graph,
            node: NodeId) -> 'ProjectExtractedIQR':
        """
        Intialize the ProjectNode instance from a node in the graph.
        """
        super_node = cls.get_super_node(graph, node)
        super_instance = ProjectFile.init_from_node(graph, super_node)
        iqr_path = graph.nodes[node]['iqr_path']
        iqr_name = graph.nodes[node]['iqr_name']
        iqr_flag = graph.nodes[node]['iqr_flag']
        return cls.from_super(
            super_instance,
            iqr_path,
            iqr_name,
            iqr_flag,
        )
