"""
Test module for `prism.data.commit_map` module.
"""
import logging
import traceback
from functools import partial
from multiprocessing import Pool
from os import PathLike
from pathlib import Path
from typing import Callable, Set

import tqdm

from prism.data.commit_map import Except, ProjectCommitUpdateMapper
from prism.data.extract_cache import get_formula_from_metadata
from prism.data.setup import create_default_switches
from prism.project.base import SentenceExtractionMethod
from prism.project.metadata.storage import MetadataStorage
from prism.project.repo import ProjectRepo
from prism.util.swim import AutoSwitchManager, SwitchManager

logging.basicConfig(level=logging.DEBUG)


def get_project(
        root_path: PathLike,
        metadata_storage: MetadataStorage,
        project_name: str) -> ProjectRepo:
    repo_path = Path(root_path) / project_name
    return ProjectRepo(
        repo_path,
        metadata_storage,
        sentence_extraction_method=SentenceExtractionMethod.SERAPI)


def get_project_func(
        root_path: PathLike,
        metadata_storage: MetadataStorage) -> Callable[[str],
                                                       ProjectRepo]:
    return partial(get_project, root_path, metadata_storage)


def get_commit_iterator(
        metadata_storage: MetadataStorage,
        project: ProjectRepo) -> Set[str]:
    return metadata_storage.get_project_revisions(project.metadata.project_name)


def get_commit_iterator_func(
        metadata_storage: MetadataStorage) -> Callable[[ProjectRepo],
                                                       Set[str]]:
    return partial(get_commit_iterator, metadata_storage)


def process_commit(
        switch_manager: SwitchManager,
        project: ProjectRepo,
        commit: str,
        results: None) -> None:
    try:
        project.git.checkout(commit)
        coq_version = project.metadata_storage.get_project_coq_versions(
            project.name,
            project.remote_url,
            project.commit_sha)
        try:
            coq_version = coq_version.pop()
        except KeyError:
            coq_version = '8.10.2'
        print(f'Choosing "coq.{coq_version}" for {project.name}')
        # get a switch
        dependency_formula = get_formula_from_metadata(
            project.metadata,
            coq_version)
        original_switch = project.opam_switch
        project.opam_switch = switch_manager.get_switch(
            dependency_formula,
            variables={
                'build': True,
                'post': True,
                'dev': True
            })
        # process the commit
        _ = project.build()
    except Exception:
        logging.debug(
            f"Skipping build for {project.metadata.project_name}:"
            f"{traceback.format_exc()}")
        raise
    finally:
        switch_manager.release_switch(project.opam_switch)
        project.opam_switch = original_switch


def get_process_commit_func(
        switch_manager: SwitchManager) -> Callable[[ProjectRepo,
                                                    str,
                                                    None],
                                                   None]:
    return partial(process_commit, switch_manager)


def main(root_path: PathLike, storage_path: PathLike) -> None:
    # Initialize from arguments
    metadata_storage = MetadataStorage.load(storage_path)
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
        get_commit_iterator_func(metadata_storage),
        get_process_commit_func(switch_manager),
        "Building projects")
    # Build projects in parallel
    results, metadata_storage = project_looper.update_map(30)
    for p, result in results.items():
        if isinstance(result, Except):
            print(f"{type(result.exception)} encountered in project {p}:")
            print(result.trace)
    storage_dir = Path(storage_path).parent
    metadata_storage.dump(
        metadata_storage,
        storage_dir / "updated_metadata.yaml")
    print("Done")


if __name__ == "__main__":
    main(
        "/workspace/pearls/cache/msp/repos",
        Path(f"{__file__}/../../../dataset/agg_coq_repos.yml").resolve())
