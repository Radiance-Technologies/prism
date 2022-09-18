"""
Provides an object-oriented abstraction of OPAM switches.
"""
import os
import re
from os import PathLike
from typing import Hashable, List

import networkx as nx

from prism.util.opam.switch import OpamSwitch
from prism.util.path import get_relative_path

_coq_file_regex = re.compile(r"(.*\.v)o{0,1}")


def check_valid_topological_sort(
        G: nx.DiGraph,
        dep_list: List[Hashable]) -> bool:
    """
    Determine whether the given topological sort of a graph is valid.

    Parameters
    ----------
    G : networkx.DiGraph
        A directed acyclic graph.
    dep_list : List[Hashable]
        A particular ordering of the nodes in `G`.

    Returns
    -------
    bool
        Whether the ordering represents a topological sort.
    """
    # Validate based on definition of topological sort:
    # if there exists an edge (or path) from one node to another, then
    # the former appears in the list before the latter.
    # Memoize sorted indices for constant-time verification of edge
    # order instead of linear in the number of vertices.
    # Final algorithmic complexity is O(V + E)
    node_indices = {v: i for (i,
                              v) in enumerate(dep_list)}
    for u, v in G.edges():
        if node_indices[v] < node_indices[u]:
            return False
    return True


def make_dependency_graph(
        files: List[PathLike],
        switch: OpamSwitch,
        IQR: str = '',
        boot: bool = False) -> nx.DiGraph:
    """
    Get a directed graph of dependencies for supplied Coq files.

    The `coqdep` executable is used to construct the graph.

    Parameters
    ----------
    files : List[PathLike]
        A list of Coq files.
    switch : OpamSwitch
        Used for execution of `coqdep` in the proper environment.
    IQR : str, optional
        IQR flags for `coqdep` that bind physical paths to logical
        library names.
    boot : bool, optional
        Whether to print dependencies over Coq library files, by default
        False.

    Returns
    -------
    dep_graph : networkx.DiGraph
        Networkx directed graph representing the dependencies between
        the given files where each node in the graph is a filepath and
        an edge exists from one node to another if the latter depends
        upon the former. Note that the nodes are paths relative to the
        current directory.

    See Also
    --------
    prism.project.iqr : For more about `IQR` flags.
    """
    dep_graph_dict = {}
    cwd = os.getcwd()
    for file in files:
        file = str(get_relative_path(file, cwd))
        if file.endswith(".vo"):
            file = file[:-1]
        deps = get_dependencies(file, switch, IQR, boot)
        dep_graph_dict[file] = [
            _coq_file_regex.match(x).groups()[0] for x in deps
        ]
    dep_graph = nx.DiGraph(dep_graph_dict)
    return dep_graph.reverse()


def get_dependencies(
        file: PathLike,
        switch: OpamSwitch,
        IQR: str = '',
        boot: bool = False) -> List[str]:
    """
    Return dependencies for the given file using `coqdep`.

    Parameters
    ----------
    file : PathLike
        The path to Coq file.
    switch : OpamSwitch
        Used for execution of `coqdep` in the proper environment.
    IQR : str, optional
        IQR flags for `coqdep` that bind physical paths to logical
        library names.
    boot : bool, optional
        Whether to print dependencies over Coq library files, by default
        False.

    Returns
    -------
    file_deps : List[str]
        List of absolute Coq file paths whose build artifacts (``.vo``
        file) the supplied file depends upon relative to the current
        working directory.

    See Also
    --------
    prism.project.iqr : For more about `IQR` flags.
    """
    if boot:
        boot = '-boot'
    else:
        boot = ''
    command = "coqdep {0} -sort {1} {2}".format(file, IQR, boot)
    file_deps = switch.run(command)
    file_deps = file_deps.stdout.strip().replace("./", "").split()
    file_deps = [_coq_file_regex.match(x).groups()[0] for x in file_deps]

    if file in file_deps:
        file_deps.remove(file)
    return file_deps


def order_dependencies(
        files: List[PathLike],
        switch: OpamSwitch,
        IQR: str = '',
        boot: bool = False) -> List[str]:
    """
    Sort the given files in dependency order using `coqdep`.

    Parameters
    ----------
    files : List[PathLike]
        A list of Coq files.
    switch : OpamSwitch
        Used for execution of `coqdep` in the proper environment.
    IQR : str, optional
        IQR flags for `coqdep` that bind physical paths to logical
        library names.
    boot : bool, optional
        Whether to print dependencies over Coq library files, by default
        False.

    Returns
    -------
    file_deps : List[str]
        The given filepaths in dependency order.

    See Also
    --------
    prism.project.iqr : For more about `IQR` flags.
    """
    files = ' '.join([str(f) for f in files])
    if boot:
        boot = '-boot'
    else:
        boot = ''
    command = "coqdep {0} -sort {1} {2}".format(files, IQR, boot)
    file_deps = switch.run(command)
    file_deps = file_deps.stdout.strip().split()
    file_deps = [_coq_file_regex.match(x).groups()[0] for x in file_deps]

    return file_deps
