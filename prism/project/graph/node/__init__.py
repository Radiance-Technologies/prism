"""
Modules for defining nodes in project graphs.
"""
from .base import ProjectNode
from .root import Project
from .file import ProjectFile
from .library import ProjectCoqLibrary, LibraryAlias, ProjectCoqLibraryRequirement
from .dependency import ProjectCoqDependency
from .iqr import ProjectExtractedIQR
from .dependency import ProjectCoqDependency
from .type import (
    DataDict,
    NodeId,
    EdgeKey,
    EdgePair,
    KeyedEdgePair,
    EdgeId,
    NodeIdSet,
    EdgeIdSet,
    Node,
    Edge,
    ProjectFileType,
    EdgeType,
    NodeType,
    NodeTypeCriteria,
    EdgeTypeCriteria,
    ProjectFileTypeNodeCriteria,
    ProjectFileTypePathCriteria,
)
from .logical import LogicalName