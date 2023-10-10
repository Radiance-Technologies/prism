#
# Copyright (c) 2023 Radiance Technologies, Inc.
#
# This file is part of PRISM
# (see https://github.com/orgs/Radiance-Technologies/prism).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program. If not, see
# <http://www.gnu.org/licenses/>.
#
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
