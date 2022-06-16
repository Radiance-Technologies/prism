"""
Module for defining Project Node
"""
import networkx as nx
from typing import List
from pathlib import Path
from dataclasses import dataclass
from .base import ProjectNode
from .type import EdgeType, NodeType, DataDict


@dataclass
class Project(ProjectNode):
    """
    A node marking the root of a project.
    """
    project_path: Path

    def __post_init__(self):
        self._node_type = NodeType.root

    def __hash__(self) -> int:
        return self.hash

    def connect(
        self,
        graph: nx.Graph,
        edgetypes: List[EdgeType]
    ):
        """
        Return empty sets since no connections are added to graph.
        """
        return set(), set()

    def get_data(self) -> DataDict:
        """
        Return context and project path.

        Returns
        -------
        DataDict
            Project node data dictionary.
        """
        return {
            "context": self.context,
            "project_path": self.project_path,
        }

    def init_parent(self) -> None:
        """
        Return None because Project has no parent node.
        """
        return None

    @classmethod
    def init_from_node(cls, graph: nx.Graph, node: str):
        """
        Load the data from the given node to initialize Project.

        Parameters
        ----------
        graph : _type_
            A graph containing ``node`` whose type is ``Project``.
        node : _type_
            A node added to the graph by a ``Project`` type
            ``ProjectNode``.
        """
        return cls(
            graph.nodes[node]['context'],
            graph.nodes[node]['project_path'],
        )
