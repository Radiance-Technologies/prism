"""
Provides a limited Python interface to the `coqdep` executable.
"""
import os
import re
from typing import Hashable, List, Optional

import networkx as nx

from prism.util.opam.api import OpamAPI
from prism.util.opam.switch import OpamSwitch
from prism.util.path import get_relative_path
from prism.util.radpytools import PathLike

_coq_file_regex = re.compile(r"(.*\.v)o{0,1}")


def is_valid_topological_sort(
        G: nx.DiGraph,
        dep_list: List[Hashable],
        reverse: bool = False) -> bool:
    """
    Determine whether the given topological sort of a graph is valid.

    Parameters
    ----------
    G : networkx.DiGraph
        A directed acyclic graph.
    dep_list : List[Hashable]
        A particular ordering of the nodes in `G`.
    reverse : bool, optional
        Whether to consider reversed topological sort order or not, by
        default False.
        If True, then a node must appear after its neighbors.
        Otherwise, a node must appear before its neighbors.

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
        if (reverse and node_indices[v] > node_indices[u]) or (
                not reverse and node_indices[v] < node_indices[u]):
            return False
    return True


def make_dependency_graph(
        files: List[PathLike],
        IQR: str = '',
        switch: Optional[OpamSwitch] = None,
        cwd: Optional[str] = None,
        boot: bool = False) -> nx.DiGraph:
    """
    Get a directed graph of dependencies for supplied Coq files.

    The `coqdep` executable is used to construct the graph.

    Parameters
    ----------
    files : List[PathLike]
        A list of absolute Coq file paths.
    IQR : str, optional
        IQR flags for `coqdep` that bind physical paths to logical
        library names.
    switch : Optional[OpamSwitch], optional
        Used for execution of `coqdep` in the proper environment, by
        default the global active switch.
    cwd : Optional[str], optional
        The working directory in which to invoke `coqdep`, by default
        the current working directory of the parent process.
    boot : bool, optional
        Whether to print dependencies over Coq library files, by default
        False.

    Returns
    -------
    dep_graph : networkx.DiGraph
        NetworkX directed graph representing the dependencies between
        the given files where each node in the graph is a filepath and
        an edge exists from one node to another if the latter depends
        upon the former. Note that the nodes are paths relative to the
        current directory.

    See Also
    --------
    prism.project.iqr : For more about `IQR` flags.
    """
    dep_graph_dict = {}
    if cwd is None:
        cwd = os.getcwd()
    for file in files:
        file = str(get_relative_path(file, cwd))
        if file.endswith(".vo"):
            file = file[:-1]
        deps = get_dependencies(file, IQR, switch, cwd, boot)
        dep_graph_dict[file] = [
            _coq_file_regex.match(x).groups()[0] for x in deps
        ]
    dep_graph = nx.DiGraph(dep_graph_dict)
    return dep_graph.subgraph(dep_graph_dict.keys()).copy()


def get_dependencies(
        file: PathLike,
        IQR: str = '',
        switch: Optional[OpamSwitch] = None,
        cwd: Optional[str] = None,
        boot: bool = False) -> List[str]:
    """
    Return dependencies for the given file using `coqdep`.

    Parameters
    ----------
    file : PathLike
        The path to Coq file.
    IQR : str, optional
        IQR flags for `coqdep` that bind physical paths to logical
        library names.
    switch : Optional[OpamSwitch], optional
        Used for execution of `coqdep` in the proper environment, by
        default the global active switch.
    cwd : Optional[str], optional
        The working directory in which to invoke `coqdep`, by default
        the current working directory of the parent process.
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
    if switch is None:
        switch = OpamAPI.active_switch
    command = "coqdep {0} -sort {1} {2}".format(file, IQR, boot)
    file_deps = switch.run(command, cwd=cwd)
    file_deps = file_deps.stdout.strip().replace("./", "").split()
    file_deps = [_coq_file_regex.match(x).groups()[0] for x in file_deps]

    if file in file_deps:
        file_deps.remove(file)
    return file_deps


def order_dependencies(
        files: List[PathLike],
        IQR: str = '',
        switch: Optional[OpamSwitch] = None,
        cwd: Optional[str] = None,
        boot: bool = False) -> List[str]:
    """
    Sort the given files in dependency order using `coqdep`.

    Parameters
    ----------
    files : List[PathLike]
        A list of Coq files.
    IQR : str, optional
        IQR flags for `coqdep` that bind physical paths to logical
        library names.
    switch : Optional[OpamSwitch], optional
        Used for execution of `coqdep` in the proper environment, by
        default the global active switch.
    cwd : Optional[str], optional
        The working directory in which to invoke `coqdep`, by default
        the current working directory of the parent process.
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
    file_args = ' '.join([str(f) for f in files])
    if boot:
        boot_arg = '-boot'
    else:
        boot_arg = ''
    if switch is None:
        switch = OpamAPI.active_switch
    command = "coqdep {0} -sort {1} {2}".format(file_args, IQR, boot_arg)
    file_deps = switch.run(command, cwd=cwd)
    file_deps = file_deps.stdout.strip().split()
    file_deps = [_coq_file_regex.match(x).groups()[0] for x in file_deps]

    return file_deps
