"""
Setup utilities, especially for repair mining.
"""
import os
from typing import List, Optional, Tuple, Union

from tqdm.contrib.concurrent import process_map

from prism.project.metadata.version_info import version_info
from prism.util.opam.api import OpamAPI
from prism.util.opam.switch import OpamSwitch


def _initialize_switch(args: Tuple[str, str]) -> OpamSwitch:
    """
    Unpack arguments for `initialize_switch`.
    """
    return initialize_switch(*args)


def initialize_switch(
        coq_version: str,
        compiler: str,
        opam_root: Optional[os.PathLike] = None) -> OpamSwitch:
    """
    Create a single OPAM switch based on designated Coq versions.

    If the switch already exists, then there is no effect.

    Parameters
    ----------
    coq_version : str
        Desired Coq versions for switch.
    compiler : str
        Desired compiler for switch.
    opam_root : os.PathLike | None, optional
        The OPAM root of the desired switch, by default the current
        globally set root.

    Returns
    -------
    OpamSwitch
        New OPAM switch.
    """
    # Create OPAM switch
    new_switch = OpamAPI.create_switch(
        "prism-%s" % coq_version,
        compiler,
        opam_root)

    # Determine SerAPI version to be used
    serapi_version = version_info.get_serapi_version(coq_version)

    # Pin Coq version and SerAPI version to OPAM switch
    new_switch.run("opam pin add coq %s -y" % coq_version)
    new_switch.run("opam pin add coq-serapi %s -y" % serapi_version)

    return new_switch


def create_switches(
        input_coq_versions: List[str],
        input_compilers: List[str],
        opam_roots: Optional[Union[os.PathLike,
                                   List[os.PathLike]]] = None,
        n_procs: int = 1) -> List[OpamSwitch]:
    """
    Create a list of OPAM switches based on designated Coq versions.

    If the switches already exist, then there is no effect.

    Parameters
    ----------
    input_coq_versions : List[str]
        List of desired Coq versions for switches.
    input_compilers : List[str]
        List of desired compilers for switches.
    n_procs : int, optional
        Number of processors to use, defaults to 1.
    opam_roots : Union[os.PathLike, List[os.PathLike]] | None, optional
        The OPAM roots of the desired switches, by default the current
        globally set root.

    Returns
    -------
    List[OpamSwitch]
        List of created OPAM switches.

    Raises
    ------
    ValueError
        If the lengths of the provided argument lists do not match.
    """
    if not isinstance(opam_roots, list):
        opam_roots = [opam_roots for _ in input_coq_versions]

    if len(input_coq_versions) != len(input_compilers):
        raise ValueError(
            "A compiler must be specified for each Coq version and vice versa.")
    elif len(input_coq_versions) != len(opam_roots):
        raise ValueError("A root must be specified for each switch.")

    job_list = zip(input_coq_versions, input_compilers, opam_roots)

    if n_procs != 1:
        # BUG: This may cause an OSError on program exit in Python 3.8
        # or earlier.
        switches = process_map(
            _initialize_switch,
            job_list,
            max_workers=n_procs)
    else:
        # do not make a subprocess if no concurrency
        switches = [_initialize_switch(job) for job in job_list]
    return switches


def create_default_switches(n_procs: int = 1) -> List[OpamSwitch]:
    """
    Create list of OPAM switches based on default Coq versions.

    If the switches already exist, then there is no effect.

    Parameters
    ----------
    n_procs : int, optional
        Number of processors to use, defaults to 1.

    Returns
    -------
    List[OpamSwitch]
        A list of the default OPAM switches.
    """
    switches = [
        '8.9.1',
        '8.10.2',
        '8.11.2',
        '8.12.2',
        '8.13.2',
        '8.14.1',
        '8.15.2'
    ]
    compilers = ['4.09.1' for _ in switches]
    switch_list = create_switches(switches, compilers, None, n_procs)
    return switch_list
