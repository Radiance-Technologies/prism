"""
Util module for creating sample objects.
"""
import os

import git

from prism.data.dataset import CoqProjectBaseDataset
from prism.project import ProjectRepo, SentenceExtractionMethod
from prism.project.metadata import ProjectMetadata
from prism.project.metadata.storage import MetadataStorage


class BaseFactory:
    def __init__(self):
        self.test_path = os.path.dirname(__file__)
        # HEAD commits as of March 14, 2022
        self.project_names = {"bellantonicook",
                              "circuits",
                              "coq-cunit"}
        self.target_projects = {
            "bellantonicook": "davidnowak/bellantonicook",
            "circuits": "coq-contribs/circuits",
            "coq-cunit": "clarus/coq-cunit"
        }
        self.commit_shas = {
            "bellantonicook": "1f03b9296104646ddc2b2b4b12e35a6619c17a99",
            "circuits": "f2cec6067f2c58e280c5b460e113d738b387be15",
            "coq-cunit": "fa20b6450f5efbd1e293d0f4e4f6ce599eeb25f0"
        }
        self.build_cmds = {
            "bellantonicook": ["make"],
            "circuits": ["make"],
            "coq-cunit": ["./configure.sh",
                          "make"]
        }


class RepoFactory(BaseFactory):
    def __init__(self):
        super().__init__()
        self.repos = {}
        self.repo_paths = {}
        self.init_repo_paths()

    def init_repo_paths(self):
        """
        Initialize repo paths.
        """
        for project_name, project in self.target_projects.items():
            project_path = os.path.join(self.test_path, project_name)
            self.repo_paths[project_name] = project_path
            try:
                repo = git.Repo.clone_from(
                    f"https://github.com/{project}",
                    project_path)
            except git.GitCommandError:
                repo = git.Repo(project_path)
            self.repos[project_name] = repo


class MetadataFactory(RepoFactory):
    def __init__(self):
        super().__init__()
        self.metadatas = {}
        self.init_metadatas()

    def init_metadatas(self):
        for project_name, project in self.target_projects.items():
            # TODO: Use real metadata and test building
            self.metadatas[project_name] = ProjectMetadata(
                project_name,
                self.build_cmds[project_name],
                ["make install"],
                ["make clean"],
                project_url=f"https://github.com/{project}",
                commit_sha=self.commit_shas[project_name])


class MetadataStorageFactory(MetadataFactory):
    def __init__(self):
        super().__init__()
        self.metadata_storage = MetadataStorage()
        self.insert_metadata()

    def insert_metadata(self):
        """
        Insert metadata into metadata storage.
        """
        for project_metadata in self.metadatas.values():
            self.metadata_storage.insert(project_metadata)


class ProjectFactory(MetadataStorageFactory):
    def __init__(self):
        super().__init__()
        self.projects = {}
        self.init_projects()

    def init_projects(self):
        """
        Initialize Projects.
        """
        for project_name in self.metadatas.keys():
            self.projects[project_name] = ProjectRepo(
                self.repo_paths[project_name],
                self.commit_shas[project_name],
                self.metadata_storage,
                num_cores=8,
                sentence_extraction_method=SentenceExtractionMethod.HEURISTIC)


class DatasetFactory(ProjectFactory):
    """
    Create test dataset.

    Useful for debugging if interactability is desired in an interpreter
    session.
    """

    def __init__(self):
        super().__init__()
        self.dataset = CoqProjectBaseDataset(
            project_class=ProjectRepo,
            projects=self.projects)
