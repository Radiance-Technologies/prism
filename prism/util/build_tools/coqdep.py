"""
Provides an object-oriented abstraction of OPAM switches.
"""
import re
from os import PathLike
from typing import List

import networkx as nx
from networkx.algorithms.dag import all_topological_sorts

from prism.util.opam.switch import OpamSwitch

_coq_file_regex = re.compile(r"(.*\.v)o{0,1}")


def check_valid_topological_sort(
        dep_graph: nx.DiGraph,
        dep_list: List[str]) -> bool:
    """
    Determine whether the given topological sort of files is valid.

    Parameters
    ----------
    dep_graph : networkx.DiGraph
        Graph representing the dependencies within some set of files.
    dep_list : List[str]
        A particular ordering of the nodes in the dependency graph.

    Returns
    -------
    bool
        Whether the ordering represents a topological sort.
    """
    return dep_list in list(all_topological_sorts(dep_graph))


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
        upon the former.

    See Also
    --------
    prism.project.iqr : For more about `IQR` flags.
    """
    dep_graph_dict = {}
    for file in files:
        if file[-3 :] == ".vo":
            file = file[:-1]
        deps = []
        deps = get_dependencies(file, switch, IQR, boot)

        deps = [_coq_file_regex.match(x).groups()[0] for x in deps]

        dep_graph_dict[file] = deps
    dep_graph = nx.DiGraph(dep_graph_dict)
    return dep_graph.reverse()


def get_dependencies(
        file: PathLike,
        switch: OpamSwitch,
        IQR: str = '',
        boot: bool = False) -> List[PathLike]:
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
    file_deps : List[PathLike]
        List of Coq files whose build artifacts (``.vo`` file) the
        supplied file depends upon.

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
        boot: bool = False) -> List[PathLike]:
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
    file_deps : List[PathLike]
        List of Coq files whose build artifacts (``.vo`` file) the
        supplied file depends upon.

    See Also
    --------
    prism.project.iqr : For more about `IQR` flags.
    """
    files = ' '.join(files)
    if boot:
        boot = '-boot'
    else:
        boot = ''
    command = "coqdep {0} -sort {1} {2}".format(files, IQR, boot)
    file_deps = switch.run(command)
    file_deps = file_deps.stdout.strip().split()
    file_deps = [_coq_file_regex.match(x).groups()[0] for x in file_deps]

    return file_deps
