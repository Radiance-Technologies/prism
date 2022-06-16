"""
Module for defining nodes for project files
"""
import networkx as nx
from typing import Union
from pathlib import Path
from dataclasses import dataclass
from .root import Project
from .type import NodeType, ProjectFileType, DataDict, NodeId
from prism.util.iterable import shallow_asdict



@dataclass
class ProjectFile(Project):
    """
    A dataclass for handling nodes that project files or directories.
    """
    project_file_path: Path
    project_file_type: ProjectFileType

    def __post_init__(self):
        self._node_type = NodeType.file

    def __hash__(self):
        return self.hash

    def get_data(self) -> DataDict:
        """
        Return data for ProjectFile node.

        Returns
        -------
        DataDict
            node data dictionary
        """
        return {
            "filetype": self.project_file_type,
            "parent": self.project_file_path.parent,
            "relative": self.project_file_path.relative_to(self.project_path),
            "stem": self.project_file_path.stem,
            "suffix": self.project_file_path.suffix or None,
            "typename": self.typename, 
        }

    def init_parent(self) -> Union[Project, 'ProjectFile']:
        """
        Return ProjectNode instance corresponding to parent path for this node.
        """
        parent = self.data['parent']
        if parent == self.project_path:
            parent = Project(self.contex, self.project_path)
        else:
            self_dict = shallow_asdict(self)
            self_dict['project_file_path'] = parent
            self_dict['parent_file_type'] = ProjectFileType.coqdirectory
            parent = self.__class__(**self_dict)
        return parent

    @classmethod
    def init_from_node(cls, graph: nx.Graph, node: NodeId) -> 'ProjectFile':
        """
        Initialize Projectfile from node in graph.
        """
        super_node = cls.get_super_node(graph, node)
        super_instance = Project.init_from_node(graph, super_node)
        project_file_path = super_instance.project_path / graph.nodes[node]['relative']
        project_file_type = graph.nodes[node]['filetype']
        return cls.from_super(
            super_instance,
            project_file_path,
            project_file_type
        )
