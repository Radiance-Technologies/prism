"""
Modules for defining nodes in project graphs.
"""
from .dependency import ProjectCoqDependency  # noqa: F401
from .file import ProjectFile  # noqa: F401
from .iqr import ProjectExtractedIQR  # noqa: F401
from .library import (  # noqa: F401
    LibraryAlias,
    ProjectCoqLibrary,
    ProjectCoqLibraryRequirement,
)
from .logical import LogicalName  # noqa: F401
from .root import ProjectRoot  # noqa: F401
from .type import (  # noqa: F401
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
