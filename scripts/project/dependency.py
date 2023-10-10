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
Script to extract dependencies from projects.
"""
import json
import os
from multiprocessing import Pool
from pathlib import Path

from tqdm import tqdm

from prism.project.graph.entity.root import ProjectRoot
from prism.project.graph.entity.type import NodeType
from prism.project.graph.graph import ProjectGraph
from prism.project.graph.node import ProjectNode
from prism.project.metadata.storage import Context, ProjectSource, Revision


def fill_graph(item):
    """
    Add all files, requirements, and dependencies to graph under root.
    """
    nodeid, graph = item
    try:
        graph.add_files(nodeid)
        graph.add_requirements(nodeid)
        graph.add_dependencies(nodeid)
        crosses = {}
        local, cross, unknown = graph.separate_dependencies()
        for source, target in cross:
            source = source.entity.project_name
            target = target.entity.project_name
            if source not in crosses:
                crosses[source] = []
            if target not in crosses[source]:
                crosses[source].append(target)
    except Exception as exc:
        raise exc
    return graph, crosses


graph = ProjectGraph()
dirs = list(os.listdir("/workspace/datasets/pearls/repos"))
repos = Path("/workspace/datasets/pearls/repos")
nodes = []
paths = []
print("test")
for root in tqdm(dirs,
                 desc="Projects Dirs",
                 total=len(dirs),
                 leave=False,
                 position=0):
    source = ProjectSource(root, "github.com")
    revision = Revision(source, 234234242)
    context = Context(revision, "8.10.2", "4.07.1")
    root_path = repos / Path(root)
    paths.append(root_path)
    root_entity = ProjectRoot(root_path, context)
    root = ProjectNode(root_entity, NodeType.root)
    graph.add_project_node(root)
    nodes.append(root.node_id)

items = [(node, graph) for node in nodes]
with Pool(40) as p:
    results = list(
        tqdm(
            p.imap(fill_graph,
                   items),
            total=len(items),
            desc="projects",
        ))
graphs = []
crosses = {}
for graph, cross in results:
    crosses.update(cross)
    graphs.append(graph)
with open("cross.json", "w") as f:
    json.dump(crosses, f)
