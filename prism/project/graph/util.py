"""
Utilities for project graph.
"""
from typing import Any

import networkx as nx

from prism.project.graph.node import NodeId


def resolve_attr(graph: nx.Graph, node: NodeId, attr_name: str) -> Any:
    """
    Get the attribute value for the given attribute and node.
    """
    return graph.nodes[node][attr_name]
