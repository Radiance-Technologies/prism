"""
Script to perform cache extraction.
"""
from prism.data.extract_cache import CacheExtractor
from prism.data.setup import create_default_switches
from prism.util.swim import AutoSwitchManager

if __name__ == "__main__":
    HOME = "/home/whenderson"
    default_commits_path = f"{HOME}/projects/PEARLS/prism/pearls/dataset/default_commits.yml"
    cache_dir = f"{HOME}/projects/PEARLS/caching"
    mds_file = f"{HOME}/projects/PEARLS/prism/pearls/dataset/agg_coq_repos.yml"
    create_default_switches(7)
    swim = AutoSwitchManager()
    project_root_path = f"{HOME}/projects/PEARLS/repos"
    log_dir = f"{HOME}/projects/PEARLS/caching/log"
    cache_extractor = CacheExtractor(
        cache_dir,
        mds_file,
        swim,
        default_commits_path)
    cache_extractor.run(project_root_path, log_dir, extract_nprocs=8)
