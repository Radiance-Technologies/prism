"""
Script to perform cache extraction.
"""
import argparse
import json
import logging
import typing
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from prism.data.extract_cache import (
    CacheExtractor,
    cache_extract_commit_iterator,
)
from prism.data.setup import create_default_switches
from prism.project.repo import CommitTraversalStrategy, ProjectRepo
from prism.util.swim import (
    AutoSwitchManager,
    SharedSwitchManagerClient,
    SharedSwitchManagerServer,
)


def load_opam_projects() -> List[str]:
    """
    Load project names from opam_projects.txt.

    Returns
    -------
    List[str]
        Project names from opam_projects.txt
    """
    opam_projects_file_path = (
        Path(__name__).parent.parent.parent / "dataset") / "opam_projects.txt"
    with open(opam_projects_file_path, "r") as f:
        projects_to_use = f.readlines()[1 :]
    return [p.strip() for p in projects_to_use]


def load_files_to_use_file(json_file: str) -> Dict[str, Iterable[str]]:
    """
    Load files to use from a JSON file.

    The JSON file should contain a single object with keys corresponding
    to project names and values being lists of files to load for those
    projects.

    Parameters
    ----------
    json_file : str
        JSON file to load

    Returns
    -------
    Dict[str, Iterable[str]]
        Loaded dictionary
    """
    with open(json_file, "rt") as f:
        obj = json.load(f)
    return obj


load_commits_to_use_file = load_files_to_use_file
"""
Load commits to use from a JSON file.

The JSON file should contain a single object with keys corresponding
to project names and values being lists of commits to load for those
projects.

Parameters
----------
json_file : str
    JSON file to load

Returns
-------
Dict[str, Iterable[str]]
    Loaded dictionary
"""

if __name__ == "__main__":
    # Get args
    parser = argparse.ArgumentParser(
        description="Extract Coq Proof Assistant state line-by-linea cross a range of "
        "project repositories, commits, and Coq versions.\n"
        "Note that commits are currently limited to those created in 2019 "
        "or later; use a different commit iterator if other behavior is "
        "desired. ")
    parser.add_argument(
        "--root",
        default=str(Path.home() / "projects" / "PEARLS"),
        type=str,
        help="Root directory for extraction. If your directory structure is"
        " arranged in a certain way, you can provide this argument and"
        " otherwise ignore '--default-commits-path', '--cache-dir',"
        " '--mds-file', '--project-root-path', and '--log-dir'. See these"
        " arguments' defaults to understand what directory structure is"
        " expected. This argument is effectively ignored if all other"
        " paths are provided.")
    args, _ = parser.parse_known_args()
    ROOT = Path(args.root)
    parser.add_argument(
        "--default-commits-path",
        default=str(ROOT / "prism/pearls/dataset/default_commits.yml"),
        type=str,
        help="Path to a yaml file containing default commits for each project."
        " Each key should be a project name, and each value should be a"
        " list of default commits. The first item is used as the default."
        " If no commits are provided for a project, it is ignored.")
    parser.add_argument(
        "--cache-dir",
        default=str(ROOT / "build_cache"),
        type=str,
        help="The directory to read cache from and write new cache to.")
    parser.add_argument(
        "--opam-root",
        default=None,
        type=str,
        help="The root for opam switches.")
    parser.add_argument(
        "--mds-file",
        default=str(ROOT / "prism/pearls/dataset/agg_coq_repos.yml"),
        type=str,
        help="The storage file to load metadata from for these projects.")
    parser.add_argument(
        "--project-root-path",
        default=str(ROOT / "repos_full"),
        type=str,
        help="The path to the project root directory, where project repos"
        " either already exist or will be cloned into.")
    parser.add_argument(
        "--log-dir",
        default=str(ROOT / "caching/log"),
        type=str,
        help="Directory to store log files in.")
    parser.add_argument(
        "--extract-nprocs",
        default=8,
        type=int,
        help="Number of concurrent workers to allow for extraction.")
    parser.add_argument(
        "--n-build-workers",
        default=1,
        type=int,
        help="Number of workers to allow for building projects, per project.")
    parser.add_argument(
        "--force-serial",
        action="store_true",
        help="Use this argument to force serial operation to the extent"
        " possible. This argument also forces certain exceptions to be"
        " raised instead of ignored. Useful for debugging.")
    parser.add_argument(
        "--num-switches",
        default=7,
        type=int,
        help="Number of processes used to set up the set of default Opam"
        " switches.")
    parser.add_argument(
        "--project-names",
        nargs="*",
        default=[],
        help="A list of projects to extract cache for. If this argument is not"
        " provided, all projects in the metadata storage and default"
        " commits file will have cache extracted. This arg overrides "
        "--opam-projects-only if both are given.")
    parser.add_argument(
        "--max-num-commits",
        default=None,
        type=int,
        help="If provided, the number of commits per project is capped at"
        " this number.")
    parser.add_argument(
        "--coq-versions",
        nargs="*",
        default=[],
        help="A list of Coq versions that will be considered for each commit."
        " If not provided, then all supported versions are considered."
        " Currently, only Coq 8.9.X to 8.15.Y are supported.")
    parser.add_argument(
        "--updated-md-storage-file",
        default=None,
        type=str,
        help="If provided, the metadata storage, which may be updated as cache"
        " is extracted, will be saved to the file given. If not provided, the"
        " --mds-file will be updated.")
    parser.add_argument(
        "--max-switch-pool-size",
        default=100,
        type=int,
        help="Maximum number of switches to allow. Set somewhat"
        " conservatively to avoid running out of disk space.")
    parser.add_argument(
        "--max-procs-file-level",
        default=128,
        type=int,
        help="Maximum number of active workers to allow at once on the "
        "file-level of extraction.")
    parser.add_argument(
        "--max-proj-build-memory",
        default=None,
        type=int,
        help="Maximum amount of memory (bytes) allowed in subprocess used to "
        "execute  a project build command. Exceeding limit results in a "
        "MemoryError captured within a ProjectBuildError")
    parser.add_argument(
        "--max-proj-build-runtime",
        default=None,
        type=int,
        help="Maximum amount of CPU time (seconds) allowed by subprocess used "
        "to execute a project build command. Exceeding limit results in a "
        "TimeoutExpired exception instead of ProjectBuildError")
    parser.add_argument(
        "--opam-projects-only",
        action="store_true",
        help="If provided, only use the projects listed in 'opam_projects.txt'."
        " This arg is overridden by --project-names if provided.")
    parser.add_argument(
        "--files-to-use-file",
        default=None,
        help="If provided, this should be a JSON file containing project-keyed "
        "lists of files to use for extraction. If not provided, use all files "
        "in projects. Keys of the form 'project@commit' can be used to restrict "
        "files on a per-commit basis.")
    parser.add_argument(
        "--commits-to-use-file",
        default=None,
        help="If provided, this should be a JSON file containing project-keyed "
        "lists of commits to use for extraction. If not provided, use the commit "
        "iteration defined by other arguments.")
    parser.add_argument(
        "--commit-iterator-march-strategy",
        default="CURLICUE_NEW",
        choices=["NEW_FIRST",
                 "OLD_FIRST",
                 "CURLICUE_NEW",
                 "CURLICUE_OLD"],
        help="Commit traversal strategy to use for the commit iterator. See the "
        "documentation for prism.project.repo.CommitTraversalStrategy for "
        "details on how each option works.")
    parser.add_argument(
        "--limit-commits-by-date",
        action="store_true",
        help="If provided, limit commits to those that were made on or after "
        "January 1, 2019, which roughly coincides with the release date of the "
        "earliest supported version of Coq, 8.9. This date limit was "
        "introduced as a stopgap measure to prevent runaway resource usage "
        "during the build of certain projects prior to the introduction of "
        "explicit memory-limiting functionality.")
    args = parser.parse_args()
    default_commits_path: str = args.default_commits_path
    cache_dir: str = args.cache_dir
    mds_file: str = args.mds_file
    project_root_path: str = args.project_root_path
    log_dir = Path(args.log_dir)
    extract_nprocs: int = args.extract_nprocs
    n_build_workers: int = args.n_build_workers
    force_serial: bool = args.force_serial
    num_switches: int = args.num_switches
    max_memory: Optional[int] = args.max_proj_build_memory
    max_runtime: Optional[int] = args.max_proj_build_runtime
    # Projects to extract
    if args.project_names:
        project_names = args.project_names
    elif args.opam_projects_only:
        project_names = load_opam_projects()
    else:
        project_names = None
    coq_version_iterator = (
        lambda _,
        __: args.coq_versions) if args.coq_versions else None
    max_num_commits: Optional[int] = \
        args.max_num_commits if args.max_num_commits else None
    if args.updated_md_storage_file:
        updated_md_storage_file = args.updated_md_storage_file
    else:
        updated_md_storage_file = mds_file
    updated_md_storage_file = Path(updated_md_storage_file)
    updated_md_storage_file.parent.mkdir(parents=True, exist_ok=True)
    max_pool_size: int = args.max_switch_pool_size
    max_procs_file_level: int = args.max_procs_file_level
    files_to_use: Optional[Dict[str, Iterable[str]]]
    if args.files_to_use_file is not None:
        files_to_use = load_files_to_use_file(args.files_to_use_file)
    else:
        files_to_use = None
    commits_to_use: Optional[Dict[str, Iterable[str]]]
    if args.commits_to_use_file is not None:
        commits_to_use = load_commits_to_use_file(args.commits_to_use_file)
    else:
        commits_to_use = None
    commit_iterator_march_strategy = CommitTraversalStrategy[
        args.commit_iterator_march_strategy]
    limit_commits_by_date: bool = args.limit_commits_by_date
    # Force redirect the root logger to a file
    # This might break due to multiprocessing. If so, it should just
    # be disabled
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file_name = f"extraction_log_{timestamp}.log"
    log_file_path = log_dir / log_file_name
    if not log_dir.exists():
        log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=log_file_path, force=True)
    # Do things
    create_default_switches(num_switches, args.opam_root)
    if force_serial:
        swim = AutoSwitchManager()
    else:
        swim_server = SharedSwitchManagerServer(AutoSwitchManager)
        swim = SharedSwitchManagerClient(
            swim_server,
            max_pool_size=max_pool_size)

    default_commit_iterator_factory = typing.cast(
        Callable[[ProjectRepo,
                  str],
                 Iterable[str]],
        partial(
            cache_extract_commit_iterator,
            march_strategy=commit_iterator_march_strategy,
            date_limit=limit_commits_by_date,
            max_num_commits=max_num_commits))

    if commits_to_use is None:
        commit_iterator_factory = default_commit_iterator_factory
    else:
        commits_to_use_arg = typing.cast(
            Dict[str,
                 Iterable[str]],
            commits_to_use)

        def commit_iterator_factory(
                project: ProjectRepo,
                starting_commit_sha: str) -> Iterable[str]:
            """
            Try to use commits loaded from file.

            Otherwise use default iteration.
            """
            try:
                return iter(commits_to_use_arg[project.name])
            except KeyError:
                return default_commit_iterator_factory(
                    project,
                    starting_commit_sha)

    cache_extractor = CacheExtractor(
        cache_dir,
        mds_file,
        swim,
        default_commits_path,
        commit_iterator_factory,
        coq_version_iterator=coq_version_iterator,
        files_to_use=files_to_use)
    cache_extractor.run(
        project_root_path,
        log_dir,
        extract_nprocs=extract_nprocs,
        force_serial=force_serial,
        n_build_workers=n_build_workers,
        project_names=project_names,
        updated_md_storage_file=updated_md_storage_file,
        max_procs_file_level=max_procs_file_level,
        max_memory=max_memory,
        max_runtime=max_runtime,
    )
