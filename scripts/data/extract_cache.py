"""
Script to perform cache extraction.
"""
import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from prism.data.extract_cache import (
    CacheExtractor,
    cache_extract_commit_iterator,
)
from prism.data.setup import create_default_switches
from prism.util.swim import (
    AutoSwitchManager,
    SharedSwitchManagerClient,
    SharedSwitchManagerServer,
)

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
        " commits file will have cache extracted.")
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
        " If not provided, then only Coq 8.10[.2] is considered."
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
    project_names = args.project_names if args.project_names else None
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
    max_pool_size = args.max_switch_pool_size
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
    create_default_switches(num_switches)
    if force_serial:
        swim = AutoSwitchManager()
    else:
        swim_server = SharedSwitchManagerServer(AutoSwitchManager)
        swim = SharedSwitchManagerClient(
            swim_server,
            max_pool_size=max_pool_size)
    cache_extractor = CacheExtractor(
        cache_dir,
        mds_file,
        swim,
        default_commits_path,
        cache_extract_commit_iterator,
        coq_version_iterator=coq_version_iterator)
    cache_extractor.run(
        project_root_path,
        log_dir,
        extract_nprocs=extract_nprocs,
        force_serial=force_serial,
        n_build_workers=n_build_workers,
        project_names=project_names,
        max_num_commits=max_num_commits,
        updated_md_storage_file=updated_md_storage_file)
