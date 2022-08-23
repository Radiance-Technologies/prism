"""
Test module for `prism.data.commit_map` module.
"""
from pathlib import Path

from prism.data.build_cache import CoqProjectBuildCache
from prism.data.commit_map import ProjectCommitUpdateMapper
from prism.data.extract_cache import get_formula_from_metadata
from prism.data.setup import create_default_switches
from prism.project.base import SentenceExtractionMethod
from prism.project.exception import ProjectBuildError
from prism.project.metadata.storage import MetadataStorage
from prism.project.repo import ProjectRepo
from prism.util.swim import AdaptiveSwitchManager, SwitchManager


class CommitBuilder:

    def __init__(
            self,
            build_cache: CoqProjectBuildCache,
            switch_manager: SwitchManager,
            metadata_storage: MetadataStorage):
        self.build_cache = build_cache
        self.switch_manager = switch_manager
        self.metadata_storage = metadata_storage

    def build(self, project, commit, results):
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
        return self.build(project, commit, results)


def main(root_path, storage_path, cache_dir):
    """
    Test instantiation with `ProjectRepo`.
    """
    # Initialize from arguments
    build_cache = CoqProjectBuildCache(cache_dir)
    metadata_storage = MetadataStorage.load(storage_path)
    switch_manager = AdaptiveSwitchManager(create_default_switches(7))
    # Initialize builder
    builder = CommitBuilder(build_cache, switch_manager, metadata_storage)
    # Generate list of projects
    projects = []
    revisions = {}
    for project_name in metadata_storage.projects:
        revisions[project_name] = metadata_storage.get_project_revisions(
            project_name)
        repo_path = Path(root_path) / project_name
        repo = ProjectRepo(
            repo_path,
            metadata_storage,
            sentence_extraction_method=SentenceExtractionMethod.SERAPI)
        projects.append(repo)

    project_looper = ProjectCommitUpdateMapper(
        projects,
        lambda p: revisions[p.project_name],
        builder,
        "Building projects")
    result, metadata_storage = project_looper.update_map(1)
    metadata_storage.dump(
        metadata_storage,
        "/workspace/pearls/cache/msp/updated-metadata.yaml")
    print("Done")


if __name__ == "__main__":
    main(
        "/workspace/pearls/cache/msp/repos",
        "/workspace/datasets/pearls/metadata/agg/agg_coq_repos.yml",
        "/workspace/pearls/cache/msp/build_cache")
