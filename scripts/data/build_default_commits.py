"""
Test module for `prism.data.commit_map` module.
"""
import logging
import traceback
from functools import partial
from multiprocessing import Pool
from pathlib import Path

import tqdm

from prism.data.build_cache import CoqProjectBuildCache
from prism.data.commit_map import ProjectCommitUpdateMapper
from prism.data.extract_cache import get_formula_from_metadata
from prism.data.setup import create_default_switches
from prism.project.base import SentenceExtractionMethod
from prism.project.exception import ProjectBuildError
from prism.project.metadata.storage import MetadataStorage
from prism.project.repo import ProjectRepo
from prism.util.swim import AdaptiveSwitchManager, SwitchManager

logging.basicConfig(level=logging.DEBUG)


class CommitBuilder:

    def __init__(
            self,
            build_cache: CoqProjectBuildCache,
            switch_manager: SwitchManager,
            metadata_storage: MetadataStorage,
            root_path: str):
        self.build_cache = build_cache
        self.switch_manager = switch_manager
        self.metadata_storage = metadata_storage
        self.root_path = root_path

    def get_project(self, project_name):
        repo_path = Path(self.root_path) / project_name
        return ProjectRepo(
            repo_path,
            self.metadata_storage,
            sentence_extraction_method=self.sentence_extraction_method)

    def get_commit_iterator(self, project):
        return self.metadata_storage.get_project_revisions(project.project_name)

    def process_commit(self, project, commit, results):
        project.git.checkout(commit)
        coq_version = project.metadata.coq_version
        # get a switch
        dependency_formula = get_formula_from_metadata(
            project.metadata,
            coq_version)
        project.opam_switch = self.switch_manager.get_switch(
            dependency_formula,
            variables={
                'build': True,
                'post': True,
                'dev': True
            })
        # process the commit
        try:
            _ = project.build()
        except ProjectBuildError as pbe:
            pass

    def __call__(self, project, commit, results):
        return self.process_commit(project, commit, results)


def get_project(root_path, metadata_storage, project_name):
    repo_path = Path(root_path) / project_name
    return ProjectRepo(
        repo_path,
        metadata_storage,
        sentence_extraction_method=SentenceExtractionMethod.SERAPI)


def get_project_func(root_path, metadata_storage):
    return partial(get_project, root_path, metadata_storage)


def get_commit_iterator(metadata_storage, project):
    return metadata_storage.get_project_revisions(project.metadata.project_name)


def get_commit_iterator_func(metadata_storage):
    return partial(get_commit_iterator, metadata_storage)


def process_commit(switch_manager, project, commit, results):
    try:
        project.git.checkout(commit)
        coq_version = project.metadata.coq_version
        # get a switch
        dependency_formula = get_formula_from_metadata(
            project.metadata,
            coq_version)
        project.opam_switch = switch_manager.get_switch(
            dependency_formula,
            variables={
                'build': True,
                'post': True,
                'dev': True
            })
        # process the commit
        _ = project.build()
    except Exception as exc:
        logging.debug(
            f"Skipping build for {project.metadata.project_name}:"
            f"{traceback.format_exc()}")
        pass


def get_process_commit_func(switch_manager):
    return partial(process_commit, switch_manager)


def main(root_path, storage_path, cache_dir):
    # Initialize from arguments
    build_cache = CoqProjectBuildCache(cache_dir)
    metadata_storage = MetadataStorage.load(storage_path)
    switch_manager = AdaptiveSwitchManager(create_default_switches(7))
    # Generate list of projects
    projects = list(
        tqdm.tqdm(
            Pool(20).imap(
                get_project_func(root_path,
                                 metadata_storage),
                metadata_storage.projects),
            desc="Initializing Project instances"))
    # Create commit mapper
    project_looper = ProjectCommitUpdateMapper(
        projects,
        get_commit_iterator_func(metadata_storage),
        get_process_commit_func(switch_manager),
        "Building projects")
    # Build projects in parallel
    result, metadata_storage = project_looper.update_map(30)
    metadata_storage.dump(
        metadata_storage,
        "/workspace/pearls/cache/msp/updated-metadata.yaml")
    print("Done")


if __name__ == "__main__":
    main(
        "/workspace/pearls/cache/msp/repos",
        "/workspace/datasets/pearls/metadata/agg/agg_coq_repos.yml",
        "/workspace/pearls/cache/msp/build_cache")
