"""
Script to perform cache extraction.
"""
import pathlib

from prism.data.extract_cache import CacheExtractor
from prism.data.setup import create_default_switches
from prism.util.swim import AutoSwitchManager

if __name__ == "__main__":
    ROOT = pathlib.Path.home() / "projects" / "PEARLS"
    default_commits_path = \
        f"{ROOT}/prism/pearls/dataset/default_commits.yml"
    cache_dir = f"{ROOT}/caching"
    mds_file = f"{ROOT}/prism/pearls/dataset/agg_coq_repos.yml"
    create_default_switches(7)
    swim = AutoSwitchManager()
    project_root_path = f"{ROOT}/repos"
    log_dir = f"{ROOT}/caching/log"
    cache_extractor = CacheExtractor(
        cache_dir,
        mds_file,
        swim,
        default_commits_path)
    cache_extractor.run(project_root_path, log_dir, extract_nprocs=8)
