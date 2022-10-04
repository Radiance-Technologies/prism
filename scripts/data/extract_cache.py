"""
Script to perform cache extraction.
"""
import argparse
import pathlib

from prism.data.extract_cache import CacheExtractor
from prism.data.setup import create_default_switches
from prism.util.swim import AutoSwitchManager

if __name__ == "__main__":
    # Get args
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default=str(pathlib.Path.home() / "projects" / "PEARLS"))
    args, _ = parser.parse_known_args()
    ROOT: str = args.root
    parser.add_argument(
        "--default-commits-path",
        default=f"{ROOT}/prism/pearls/dataset/default_commits.yml")
    parser.add_argument("--cache-dir", default=f"{ROOT}/caching")
    parser.add_argument(
        "--mds-file",
        default=f"{ROOT}/prism/pearls/dataset/agg_coq_repos.yml")
    parser.add_argument("--project-root-path", default=f"{ROOT}/repos_full")
    parser.add_argument("--log-dir", default=f"{ROOT}/caching/log")
    parser.add_argument("--extract-nprocs", default=8)
    parser.add_argument("--n-build-workers", default=1)
    parser.add_argument("--force-serial", action="store_true")
    parser.add_argument("--num-switches", default=7)
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
    # Do things
    create_default_switches(num_switches)
    swim = AutoSwitchManager()
    cache_extractor = CacheExtractor(
        cache_dir,
        mds_file,
        swim,
        default_commits_path)
    cache_extractor.run(
        project_root_path,
        log_dir,
        extract_nprocs=extract_nprocs,
        force_serial=force_serial,
        n_build_workers=n_build_workers)
