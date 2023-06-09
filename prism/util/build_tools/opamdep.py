"""
Heuristics for managing/detecting Opam dependencies.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

from seutil import bash

from prism.interface.coq.iqr import IQR
from prism.util.build_tools.mappings import LogicalMappings, RequiredLibrary
from prism.util.opam import Version
from prism.util.path import get_relative_path
from prism.util.radpytools import PathLike

_require_pattern = re.compile(
    r"(?:From\s*(?P<prefix>[^\s]+)\s*)?Require\s+(?:Import|Export)?\s(?P<suffixes>.+)\."
)


def get_required_libraries(
        root: PathLike,
        cwd: Optional[PathLike] = None) -> Dict[Path,
                                                Set[RequiredLibrary]]:
    """
    Get a set of libraries required in each Coq file with a directory.

    Parameters
    ----------
    root : PathLike
        The directory in which to search for library requirements.
    cwd : Optional[PathLike], optional
        The current working directory to which all paths, including
        `root` are relative.
        If None, then the current process's working directory is used.

    Returns
    -------
    Dict[PathLike, Set[Tuple[Optional[str], str]]]
        A map from filepaths relative to `cwd` to sets of pairs of
        library prefixes and suffixes as used within import statements.
        Prefixes are optional and refer to "Prefix" in the following
        example: "From Prefix Require Import Suffix".
    """
    if cwd is None:
        cwd = os.getcwd()
    r = bash.run(f"grep -RH --include '*.v' 'Require' {root}", cwd=cwd)
    if r.returncode != 0 and r.returncode != 1:
        # grep returns 1 if there are no results
        r.check_returncode()
    required_libs: Dict[PathLike,
                        Set[Tuple[Optional[str],
                                  str]]] = {}
    lines: List[str] = r.stdout.splitlines()
    for line in lines:
        filename, line = line.split(":", maxsplit=1)
        filename = get_relative_path(filename, cwd)
        file_requires = required_libs.setdefault(filename, set())
        for m in re.finditer(_require_pattern, line):
            prefix = m['prefix']
            suffixes = m['suffixes']
            for suffix in suffixes.split():
                file_requires.add((prefix, suffix))
    return required_libs


def guess_opam_packages(
        libraries: Union[Dict[PathLike,
                              Set[RequiredLibrary]],
                         Set[RequiredLibrary]],
        iqr_flags: Optional[IQR] = None,
        coq_version: Optional[Union[str,
                                    Version]] = None) -> Set[str]:
    r"""
    Guess opam packages that are implied by given required libraries.

    Parameters
    ----------
    libraries : Union[Dict[PathLike, Set[RequiredLibrary]], \
                      Set[RequiredLibrary]]
        Either a map from Coq file paths to the libraries that each
        requires or a set of library requirements.
    iqr_flags : Optional[IQR], optional
        Local physical path bindings that may shadow the usual logical
        library paths for comman opam packages, by default None.
    coq_version : Optional[Union[str, Version]], optional
        The Coq version in which to perform the inference.
        Standard Coq libraries may shadow opam packages for certain
        Require statements, so this parameter is key to eliminating
        ambiguity.
        If not given, then

    Returns
    -------
    Set[str]
        The set of opam packages, if any, that are likely required to be
        installed before executing Coq files that require the given
        `libraries`.
    """
    if isinstance(libraries, dict):
        libraries = {v for vs in libraries.values() for v in vs}
    if iqr_flags is not None:
        local_libraries = iqr_flags.local_libraries()
    else:
        local_libraries = []
    shadowed_packages = set()
    for local_lib in local_libraries:
        matching_packages = LogicalMappings.opam.search(None, local_lib)
        if len(matching_packages) == 1:
            shadowed_packages.update(matching_packages)
    # load Coq mappings
    coq_libraries = None
    if coq_version is not None:
        coq_libraries = LogicalMappings.get_coq_mappings(coq_version)
    local_mapping = LogicalMappings(
        {k: "_local_project_" for k in local_libraries})
    packages = set()
    for prefix, suffix in libraries:
        # search local libraries first
        if local_mapping.search(prefix, suffix):
            # TODO: match semantics of Q and R, i.e., non-exact matches
            # are allowed for Q-bound libraries only if a From keyword
            # is present
            continue
        # then search Coq standard libaries
        if coq_libraries is not None and coq_libraries.search(prefix, suffix):
            continue
        # if no local or stdlib match, try to find opam package
        matching_packages = LogicalMappings.opam.search(prefix, suffix)
        if len(matching_packages) == 1:
            packages.update(matching_packages)
    # special handling
    if "coq-menhirlib" in packages or "coq-menhirlib" in shadowed_packages:
        packages.add("menhir")
    return packages
