"""
Setup utilities, especially for repair mining.
"""
import os
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Union

from tqdm.contrib.concurrent import process_map

from prism.project.base import Project, SentenceExtractionMethod
from prism.project.metadata.storage import MetadataStorage
from prism.project.metadata.version_info import version_info
from prism.project.repo import ProjectRepo
from prism.util.opam.api import OpamAPI
from prism.util.opam.switch import OpamSwitch


def _initialize_switch(
        args: Tuple[str,
                    str,
                    Optional[os.PathLike]]) -> OpamSwitch:
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
    new_switch.add_repo("coq-released", "https://coq.inria.fr/opam/released")

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


def _initialize_project(
    args: Tuple[str,
                str,
                MetadataStorage,
                Optional[SentenceExtractionMethod],
                Optional[int]]
) -> ProjectRepo:
    """
    Unpack arguments for `initialize_project`.
    """
    return initialize_project(*args)


def initialize_project(
    root_path: str,
    project_name: str,
    metadata_storage: MetadataStorage,
    sentence_extraction_method: Optional[SentenceExtractionMethod] = None,
    n_build_workers: Optional[int] = None,
) -> ProjectRepo:
    """
    Initialize project from parent directory and project name.

    Initializes project using current commit.

    Parameters
    ----------
    root_path: str
        Root path containing project root directories
        with names matching project names.
    project_name: str
        Name of project to be initialized.
    metadata_storage: MetadataStorage
        A metadata storage instance.
    sentence_extraction_method: SentenceExtractionMethod | None
        Project sentence extraction method. If None, the default
        SentenceExtractionMethod will be used.
    n_build_workers: int | None
        Number of process to build with. If None, the default
        number of processes will be used.

    Returns
    -------
    ProjectRepo
        Initialized project with specified sentence extraction method,
        build worker count, and metadata storage.
    """
    repo_path = Path(root_path) / project_name
    # Quietly allow user to avoid overriding defaults.
    kwargs = {}
    if sentence_extraction_method is not None:
        kwargs['sentence_extraction_method'] = sentence_extraction_method
    if n_build_workers is not None:
        kwargs['num_cores'] = n_build_workers
    return ProjectRepo(repo_path, metadata_storage, **kwargs)


def initialize_projects(
        root_path: str,
        metadata_storage: Union[os.PathLike,
                                MetadataStorage],
        projects: Optional[List[str]] = None,
        sentence_extraction_methods: Optional[Union[
            SentenceExtractionMethod,
            List[SentenceExtractionMethod]]] = None,
        n_build_workers: Optional[Union[int,
                                        List[int]]] = None,
        n_procs: int = 1) -> List[Project]:
    """
    Initialize projects that are subdirectories of `root_path`.

    Parameters
    ----------
    root_path: str
        Root path containing project root directories
        with names matching project names.
    metadata_storage: Union[PathLike, MetadataStorage]
        A metadata storage instance or a path to a serialized
        metadata storage file.
    projects: Optional[List[str]]
        Projects to be initialized. If None, then all projects
        in metadata storage will be initialized.
    sentence_extraction_methods: Optional[SentenceExtractionMethod],
        Project sentence extraction method. If None, the default
        SentenceExtractionMethod will be used.
    n_build_workers: Optional[int] = None,
        Number of process to build with. If None, the default
        number of processes will be used.
    n_procs : int, optional
        Number of processors to use, defaults to 1.

    Returns
    -------
    List[Project]
        List of initialized projects.

    Raises
    ------
    ValueError
        If the lengths of the provided argument lists do not match.
    """
    if isinstance(metadata_storage, (str, Path)):
        metadata_storage = MetadataStorage.load(metadata_storage)
    if projects is None:
        projects = metadata_storage.projects
    nproj = len(projects)
    # Make sure all arguments can be zipped together
    root_paths = nproj * (root_path,)
    metadata_storages = nproj * (metadata_storage,)
    if not isinstance(sentence_extraction_methods, Iterable):
        sentence_extraction_methods = nproj * (sentence_extraction_methods,)
    if not isinstance(n_build_workers, Iterable):
        n_build_workers = nproj * (n_build_workers,)
    if len(n_build_workers) != nproj:
        raise ValueError(
            "Number of build workers should be specified"
            "once (int), for each project (Tuple[int]), or not at all (None)")
    if len(sentence_extraction_methods) != nproj:
        raise ValueError(
            "Sentence extraction method should be specified"
            "once (int), for each project (Tuple[int]), or not at all (None)")

    job_list = zip(
        root_paths,
        projects,
        metadata_storages,
        sentence_extraction_methods,
        n_build_workers)

    if n_procs != 1:
        # BUG: This may cause an OSError on program exit in Python 3.8
        # or earlier.
        projects = process_map(
            _initialize_project,
            job_list,
            max_workers=n_procs,
            desc="Initializing Projects",
            total=nproj)
    else:
        # do not make a subprocess if no concurrency
        projects = [_initialize_project(job) for job in job_list]
    return projects
