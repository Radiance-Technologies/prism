"""
Provides an object-oriented abstraction of OPAM switches.
"""
import os
import re
from os import PathLike
from typing import List

import networkx as nx
from networkx.algorithms.dag import all_topological_sorts

from prism.util.opam.switch import OpamSwitch


def check_valid_topological_sort(
        dep_graph: nx.DiGraph,
        dep_list: List[str]) -> bool:
    """
    Determine whether the given topological sort of files is valid.

    Parameters
    ----------
    dep_graph : networkx.DiGraph
        Graph representing dependencies of the given set of files.
    dep_list : List[str]
        A particular ordering of the nodes in the dependency graph.

    Returns
    -------
    valid : bool
        Whether the ordering represents a topological sort.
    """
    return dep_list in list(all_topological_sorts(dep_graph))


def make_dependency_graph(
        files: List[PathLike],
        switch: OpamSwitch,
        IQR: str = '',
        boot: bool = False) -> nx.DiGraph:
    """
    Return directed graph of dependencies for supplied files.

    Parameters
    ----------
    files : List[PathLike]
        List of files to be submitted to coqdep
    switch : OpamSwitch
        Used for execution of coqdep in the proper environment
    IQR : str, optional
        IQR flags for coqdep
    boot : bool
        For coq developers, prints dependencies over coq
        library files (omitted by default).

    Returns
    -------
    dep_graph : networkx.DiGraph
        Networkx directed graph representing the dependencies
        between the given files.
    """
    dep_graph_dict = {}
    regex = re.compile(r"(.*\.v)o{0,1}")
    for file in files:
        if file[-3 :] == ".vo":
            file = file[:-1]
        deps = []
        deps = get_dependencies(file, switch, IQR, boot)
        deps = [regex.match(x).groups()[0] for x in deps]
        dep_graph_dict[file] = deps
    dep_graph = nx.DiGraph(dep_graph_dict)
    return dep_graph.reverse()


def get_dependencies(
        file: PathLike,
        switch: OpamSwitch,
        IQR: str = '',
        boot: bool = False) -> List[PathLike]:
    """
    Return dependencies for the given file.

    Parameters
    ----------
    file : PathLike
        Path of file to be submitted to coqdep
    switch : OpamSwitch
        Used for execution of coqdep in the proper environment
    IQR : str, optional
        IQR flags for coqdep
    boot : bool
        For coq developers, prints dependencies over coq
        library files (omitted by default).

    Returns
    -------
    file_deps : List[str]
        List of '.vo' files which the supplied file depend on.
    """
    if boot:
        boot = '-boot'
    else:
        boot = ''
    command = "coqdep {0} -sort {1} {2}".format(file, IQR, boot)
    file_deps = switch.run(command)
    file_deps = file_deps.stdout.strip().replace("./", "").split(" ")
    dirname = os.path.dirname(file)

    # The dirname may not be what coqdep is using
    # as its base directory. It may be using the working directory
    def join(f):
        return os.path.join(dirname, f)

    file_deps = [join(filename) for filename in file_deps]
    regex = re.compile(r"(.*\.v)o{0,1}")
    file_deps = [regex.match(x).groups()[0] for x in file_deps]

    if file in file_deps:
        file_deps.remove(file)
    return file_deps


def order_dependencies(
        files: List[PathLike],
        switch: OpamSwitch,
        IQR: str = '',
        boot: bool = False) -> List[PathLike]:
    """
    Return sorted dependencies for supplied files.

    Parameters
    ----------
    files : List[PathLike]
        List of files to be submitted to coqdep
    switch : OpamSwitch
        Used for execution of coqdep in the proper environment
    IQR : str, optional
        IQR flags for coqdep
    boot : bool
        For coq developers, prints dependencies over coq
        library files (omitted by default).

    Returns
    -------
    file_deps : List[str]
        List of '.vo' files in order of least to most dependent
    """
    files = ' '.join(files)
    if boot:
        boot = '-boot'
    else:
        boot = ''
    command = "coqdep {0} -sort {1} {2}".format(files, IQR, boot)
    file_deps = switch.run(command)
    file_deps = file_deps.stdout.strip().split(" ")

    regex = re.compile(r"(.*\.v)o{0,1}")
    file_deps = [regex.match(x).groups()[0] for x in file_deps]

    return file_deps
