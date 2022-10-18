"""
Module to project setup utilities.
"""

from inspect import signature
from os import PathLike
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Union

from tqdm.contrib.concurrent import process_map

from prism.project.base import Project, SentenceExtractionMethod
from prism.project.metadata.storage import MetadataStorage
from prism.project.repo import ProjectRepo


def _initialize_project(args: Tuple[str, str]) -> Project:
    """
    Unpack arguments for `initialize_project`.
    """
    nargs = len(args)
    if nargs < 3:
        raise RuntimeError(
            "The following arguments are required:"
            " root_path, project_name, and metadata_storage.")
    nparam = len(signature(initialize_project).parameters)
    args = args + (nparam - nargs) * (None,)
    return initialize_project(*args)


def initialize_project(
    root_path: str,
    project_name: str,
    metadata_storage: MetadataStorage,
    sentence_extraction_method: SentenceExtractionMethod,
    n_build_workers: int,
) -> ProjectRepo:
    """
    Initialize project from parent directory and project name.

    Initializes project using current commit.

    Parameters
    ----------
    root_path : str
        Directory containing project folder
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
        metadata_storage: Union[PathLike,
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

    job_list = zip(root_paths, projects, metadata_storages, n_build_workers)

    if n_procs != 1:
        # BUG: This may cause an OSError on program exit in Python 3.8
        # or earlier.
        switches = process_map(
            _initialize_project,
            job_list,
            max_workers=n_procs,
            desc="Initializing switches",
            total=nproj)
    else:
        # do not make a subprocess if no concurrency
        switches = [_initialize_project(job) for job in job_list]
    return switches
