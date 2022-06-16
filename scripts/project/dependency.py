import os
from multiprocessing import Pool
from pathlib import Path

import networkx as nx
from tqdm import tqdm

from prism.project.graph.graph import ProjectGraph
from prism.project.graph.node.root import Project
from prism.project.metadata.storage import Context, Revision


def fill_graph(item):
    node, graph = item
    try:
        root_node = Project.init_from_node(graph, node)
        graph.add_iqrs(root_node.node)
        graph.add_requirements(root_node.node)
        graph.add_aliases(root_node.node)
        graph.add_dependencies(root_node.node)
    except Exception as exc:
        raise exc
    return graph


graph = ProjectGraph()
dirs = list(os.listdir("/workspace/datasets/pearls/repos"))
repos = Path("/workspace/datasets/pearls/repos")
nodes = []
for root in tqdm(dirs,
                 desc="Projects",
                 total=len(dirs),
                 leave=False,
                 position=0):
    context = Context(Revision(root, '111'), '', '')
    root = repos / Path(root)
    root = Project(context, root)
    graph.add_root(root)
    nodes.append(root.node)
    for dirname, _, files in os.path.walk():
        dirname = Path(dirname)
        if graph.add_path(dirname):
            for file in files:
                file = dirname / Path(file)
                graph.add_path(file)
graph.add_libraries()

items = [(node, graph) for node in nodes]

with Pool(40) as p:
    graphs = list(
        tqdm(
            p.imap(fill_graph,
                   items),
            total=len(dirs),
            desc="projects",
        ))
    graph = nx.compose_all(graphs)
    directory = f"/home/atouchet/projects/PEARLS/dependencies"
    crosses = {}
    local, cross, unknown = graph.separate_dependencies()
    for dep, source, target in cross:
        source = source.context.revision.project_source.project_name
        target = target.context.revision.project_source.project_name
        if source not in crosses:
            crosses[source] = []
        crosses[source].append(target)
    with open("cross.json", "w") as f:
        json.dump(crosses, f)

    graph.dump_dependencies(directory)
