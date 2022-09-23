"""
Test module for `prism.data.commit_map` module.
"""
import logging
from functools import partial
from multiprocessing import Pool
from os import PathLike
from pathlib import Path
from typing import Callable, Dict, List

import tqdm
from seutil import io

from prism.data.commit_map import Except, ProjectCommitUpdateMapper
from prism.data.setup import create_default_switches
from prism.data.util import (
    build_commit,
    get_default_commit_iterator_func,
    get_project_func,
)
from prism.project.metadata.storage import MetadataStorage
from prism.project.repo import ProjectRepo
from prism.util.swim import AutoSwitchManager, SwitchManager

logging.basicConfig(level=logging.DEBUG)


def get_process_commit_func(  # noqa: D103
    switch_manager: SwitchManager) -> Callable[[ProjectRepo,
                                                str,
                                                None],
                                               None]:
    return partial(build_commit, switch_manager)


def main(
        root_path: PathLike,
        storage_path: PathLike,
        default_commits_path: PathLike) -> None:
    """
    Build all projects at `root_path` and save updated metadata.

    Parameters
    ----------
    root_path : PathLike
        The root directory containing each project's directory.
        The project directories do not need to already exist.
    storage_path : PathLike
        The path to a file containing metadata for each project to be
        built at `root_path`.
    default_commits_path : PathLike
        The path to a file identifying the default commits for each
        project in the storage.
    """
    # Initialize from arguments
    metadata_storage = MetadataStorage.load(storage_path)
    default_commits: Dict[str,
                          List[str]] = io.load(
                              default_commits_path,
                              clz=dict)
    create_default_switches(7)
    switch_manager = AutoSwitchManager()
    # Generate list of projects
    projects = list(
        tqdm.tqdm(
            Pool(20).imap(
                get_project_func(root_path,
                                 metadata_storage),
                metadata_storage.projects),
            desc="Initializing Project instances",
            total=len(metadata_storage.projects)))
    # Create commit mapper
    project_looper = ProjectCommitUpdateMapper(
        projects,
        get_default_commit_iterator_func(default_commits),
        get_process_commit_func(switch_manager),
        "Building projects",
        terminate_on_except=False)
    # Build projects in parallel
    results, metadata_storage = project_looper.update_map(30)
    storage_dir = Path(storage_path).parent
    # report errors
    with open(storage_dir / "build_error_log.txt") as f:
        for p, result in results.items():
            if isinstance(result, Except):
                print(f"{type(result.exception)} encountered in project {p}:")
                print(result.trace)
                f.write(
                    '\n'.join(
                        [
                            "###################################################",
                            f"{type(result.exception)} encountered in project {p}:",
                            result.trace
                        ]))
    # update metadata
    metadata_storage.dump(
        metadata_storage,
        storage_dir / "updated_metadata.yaml")
    print("Done")


if __name__ == "__main__":
    dataset_path = Path(f"{__file__}/../../../dataset").resolve()
    main(
        "/workspace/pearls/cache/msp/repos",
        dataset_path / "agg_coq_repos.yml",
        dataset_path / "default_commits.yml")
