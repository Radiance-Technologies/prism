"""
Provides an object-oriented abstraction of OPAM switches.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
import warnings
from dataclasses import InitVar, dataclass, field, fields
from functools import cached_property
from os import PathLike
from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess
from typing import ClassVar, Dict, List, Optional, Tuple

from seutil import bash


__all__ = ['OpamSwitch']

logger = logging.getLogger(__file__)
logger.setLevel(logging.DEBUG)



@dataclass
class CoqDepAPI:
    """
    Wrapper for the Coq build utility `coqdep`.

    Note that Coq must be installed to use all of the features of this
    class.
    """

    def order_dependencies(self, 
                          files: List[str],
                          switch: OpamSwitch,
                          i: Optional[str] = '',
                          q: Optional[str] = '',
                          r: Optional[str] = ''):
        results = []
        dep_graph = nx.DiGraph()
        regex = re.compile("((?:.*\.(?:vo|v|glob|v.beautified))*):((?:\s.*\.(?:vo|v))*)")
        for file in files:
            dep_graph.add_node(file)
            command = "coqdep {0} -I {1} -Q {2} -R {3}".format(file,
                                                               i,
                                                               q,
                                                               r)
            file_deps = switch.run(command)

            for line in file_deps:
                matchObj = regex.match(line)
                if matchObj:
                    depends = matchObj.groups()[1]
                    dep_files = depends.split(' ')
                    dep_files = [x.strip().strip("./") for x in dep_files]
                    dep_files = [x.replace(".vo", ".v") for x in dep_files]
                    dep_edges = [(file, x) for x in dep_files]
                    dep_graph.add_edges_from(dep_edges)

        return dep_graph.topological_sort()
        

