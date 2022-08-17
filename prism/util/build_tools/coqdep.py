"""
Provides an object-oriented abstraction of OPAM switches.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
import warnings

import networkx as nx

from dataclasses import InitVar, dataclass, field, fields
from functools import cached_property
from os import PathLike
from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess
from typing import ClassVar, Dict, List, Optional, Tuple

from seutil import bash



@dataclass
class CoqDepAPI:
    """
    Wrapper for the Coq build utility `coqdep`.

    Note that Coq must be installed to use all of the features of this
    class.
    """
    def __init__(self):
        self.test_val = ""

    def order_dependencies(
            self,
            files: List[str],
            switch: OpamSwitch,
            IQR: Optional[str] = ''):
        results = []
        dep_graph = nx.DiGraph()
        regex = re.compile(
            "((?:.*\.(?:vo|v|glob|v.beautified|required_vo))*):((?:\s.*\.(?:vo|v))*)")
        for file in files:
            file = file.strip("./")
            dep_graph.add_node(file)
            command = "coqdep {0} {1}".format(file, IQR)
            file_deps = switch.run(command)
            file_deps = file_deps.stdout

            print("File deps: ", file_deps)

            lines = file_deps.split("\n")

            for line in lines:
                print(line)
                matchObj = regex.match(line)
                if matchObj:
                    depends = matchObj.groups()[1]
                    print("Depends: ", depends)
                    dep_files = depends.split(' ')
                    dep_files = [x.strip().strip("./") for x in dep_files]
                    dep_files = [x.replace(".vo", ".v") for x in dep_files]
                    print("Dep files: ", dep_files)
                    dep_edges = []
                    for x in dep_files:
                        if x is not '' and file != x:
                            dep_edges.append((file, x))
                    print("Edges: ", dep_edges)
                    dep_graph.add_edges_from(dep_edges)

        print(nx.to_dict_of_dicts(dep_graph))

        return list(nx.topological_sort(dep_graph))
