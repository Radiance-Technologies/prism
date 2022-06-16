"""
Modules for defining nodes in project graphs.
"""
from .base import ProjectNode
from .dependency import ProjectCoqDependency
from .file import ProjectFile
from .iqr import ProjectExtractedIQR
from .library import (
    LibraryAlias,
    ProjectCoqLibrary,
    ProjectCoqLibraryRequirement,
)
from .logical import LogicalName
from .root import Project
from .type import (
    DataDict,
    Edge,
    EdgeId,
    EdgeIdSet,
    EdgeKey,
    EdgePair,
    EdgeType,
    EdgeTypeCriteria,
    KeyedEdgePair,
    Node,
    NodeId,
    NodeIdSet,
    NodeType,
    NodeTypeCriteria,
    ProjectFileType,
    ProjectFileTypeNodeCriteria,
    ProjectFileTypePathCriteria,
)
