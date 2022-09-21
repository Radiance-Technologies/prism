"""
Test module for `prism.data.commit_map` module.
"""
import logging
import traceback
from functools import partial
from multiprocessing import Pool
from os import PathLike
from pathlib import Path
from typing import Callable, Dict, List, Set

import tqdm
from seutil import io

from prism.data.commit_map import Except, ProjectCommitUpdateMapper
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
    """
    Get the identified project's `ProjectRepo` representation.
    """
    repo_path = Path(root_path) / project_name
    return ProjectRepo(
        repo_path,
        metadata_storage,
        sentence_extraction_method=SentenceExtractionMethod.SERAPI)


def get_project_func(  # noqa: D103
        root_path: PathLike,
        metadata_storage: MetadataStorage) -> Callable[[str],
                                                       ProjectRepo]:
    from seutil import io
    io.dump()
    return partial(get_project, root_path, metadata_storage)


def get_commit_iterator(
        default_commits: Dict[str,
                              List[str]],
        project: ProjectRepo) -> Set[str]:
    """
    Get an iterator over a project's default commits.
    """
    return default_commits[project.metadata.project_name]


def get_commit_iterator_func(  # noqa: D103
    default_commits: Dict[str,
                          List[str]]) -> Callable[[ProjectRepo],
                                                  List[str]]:
    return partial(get_commit_iterator, default_commits)


def process_commit(
        switch_manager: SwitchManager,
        project: ProjectRepo,
        commit: str,
        results: None) -> None:
    """
    Build the project at the given commit.
    """
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
        project.infer_opam_dependencies()  # force inference
        dependency_formula = project.get_dependency_formula(
            coq_version,
            project.ocaml_version)
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


def get_process_commit_func(  # noqa: D103
    switch_manager: SwitchManager) -> Callable[[ProjectRepo,
                                                str,
                                                None],
                                               None]:
    return partial(process_commit, switch_manager)


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
        get_commit_iterator_func(default_commits),
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
