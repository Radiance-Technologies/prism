"""
Script to perform cache extraction.
"""
import argparse
import logging
import os
import pathlib
from datetime import datetime
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
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default=str(pathlib.Path.home() / "projects" / "PEARLS"),
        help="Root directory for extraction. If your directory structure is"
        " arranged in a certain way, you can provide this argument and"
        " otherwise ignore '--default-commits-path', '--cache-dir',"
        " '--mds-file', '--project-root-path', and '--log-dir'. See these"
        " arguments' defaults to understand what directory structure is"
        " expected. This argument is effectively ignored if all other"
        " paths are provided.")
    args, _ = parser.parse_known_args()
    ROOT: str = args.root
    parser.add_argument(
        "--default-commits-path",
        default=f"{ROOT}/prism/pearls/dataset/default_commits.yml",
        help="Path to a yaml file containing default commits for each project."
        " Each key should be a project name, and each value should be a"
        " list of default commits. The first item is used as the default."
        " If no commits are provided for a project, it is ignored.")
    parser.add_argument(
        "--cache-dir",
        default=f"{ROOT}/caching",
        help="The directory to read cache from and write new cache to.")
    parser.add_argument(
        "--mds-file",
        default=f"{ROOT}/prism/pearls/dataset/agg_coq_repos.yml",
        help="The storage file to load metadata from for these projects.")
    parser.add_argument(
        "--project-root-path",
        default=f"{ROOT}/repos_full",
        help="The path to the project root directory, where project repos"
        " either already exist or will be cloned into.")
    parser.add_argument(
        "--log-dir",
        default=f"{ROOT}/caching/log",
        help="Directory to store log files in.")
    parser.add_argument(
        "--extract-nprocs",
        default=8,
        help="Number of concurrent workers to allow for extraction.")
    parser.add_argument(
        "--n-build-workers",
        default=1,
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
        help="Number of default switches to set up for the AutoSwitchManager."
        " Leave as 7 unless you have a good reason to do otherwise. This"
        " argument does not limit the number of switches used overall.")
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
        help="If provided, the number of commits per project is capped at"
        " this number.")
    parser.add_argument(
        "--updated-md-storage-file",
        default=None,
        help="If provided, the metadata storage, which may be updated as cache"
        " is extracted, will be saved to the file given.")
    args = parser.parse_args()
    default_commits_path: str = args.default_commits_path
    cache_dir: str = args.cache_dir
    mds_file: str = args.mds_file
    project_root_path: str = args.project_root_path
    log_dir: str = args.log_dir
    extract_nprocs: int = int(args.extract_nprocs)
    n_build_workers: int = int(args.n_build_workers)
    force_serial: bool = bool(args.force_serial)
    num_switches: int = int(args.num_switches)
    project_names = args.project_names if args.project_names else None
    max_num_commits: Optional[int] = int(args.max_num_commits)
    updated_md_storage_file: Optional[str] = args.updated_md_storage_file
    if updated_md_storage_file:
        os.makedirs(pathlib.Path(updated_md_storage_file).parent, exist_ok=True)
    # Force redirect the root logger to a file
    # This might break due to multiprocessing. If so, it should just
    # be disabled
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file_name = f"extraction_log_{timestamp}.log"
    log_file_path = os.path.join(log_dir, log_file_name)
    logging.basicConfig(filename=log_file_path, force=True)
    # Do things
    create_default_switches(num_switches)
    if force_serial:
        swim = AutoSwitchManager()
    else:
        swim_server = SharedSwitchManagerServer(AutoSwitchManager)
        swim = SharedSwitchManagerClient(swim_server)
    cache_extractor = CacheExtractor(
        cache_dir,
        mds_file,
        swim,
        default_commits_path,
        cache_extract_commit_iterator)
    cache_extractor.run(
        project_root_path,
        log_dir,
        extract_nprocs=extract_nprocs,
        force_serial=force_serial,
        n_build_workers=n_build_workers,
        project_names=project_names,
        max_num_commits=max_num_commits,
        updated_md_storage_file=updated_md_storage_file)
