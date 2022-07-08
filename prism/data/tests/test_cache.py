"""
Test module for prism.data.coqgym.dataset module.
"""
import os
import shutil
import unittest

import git

from prism.data.cache import Looper
from prism.data.dataset import CoqGymBaseDataset
from prism.project import ProjectRepo, SentenceExtractionMethod
from prism.project.metadata import ProjectMetadata
from prism.project.metadata.storage import MetadataStorage


class DatasetFactory:

    def __init__(cls):
        cls.test_path = os.path.dirname(__file__)
        # HEAD commits as of March 14, 2022
        cls.project_names = {"bellantonicook",
                             "circuits",
                             "coq-cunit"}
        cls.target_projects = {
            "bellantonicook": "davidnowak/bellantonicook",
            "circuits": "coq-contribs/circuits",
            "coq-cunit": "clarus/coq-cunit"
        }
        cls.commit_shas = {
            "bellantonicook": "1f03b9296104646ddc2b2b4b12e35a6619c17a99",
            "circuits": "f2cec6067f2c58e280c5b460e113d738b387be15",
            "coq-cunit": "fa20b6450f5efbd1e293d0f4e4f6ce599eeb25f0"
        }
        cls.build_cmds = {
            "bellantonicook": ["make"],
            "circuits": ["make"],
            "coq-cunit": ["./configure.sh", "make"]}

        cls.repo_paths = {}
        cls.repos = {}
        cls.projects = {}
        cls.metadatas = {}
        cls.metadata_storage = MetadataStorage()

        cls.init_repo_paths()
        cls.insert_metadata()
        cls.init_projects()
        cls.dataset = CoqGymBaseDataset(
            project_class=ProjectRepo,
            projects=cls.projects)

    def init_repo_paths(cls):
        for project_name, project in cls.target_projects.items():
            project_path = os.path.join(cls.test_path, project_name)
            cls.repo_paths[project_name] = project_path
            try:
                repo = git.Repo.clone_from(
                    f"https://github.com/{project}",
                    project_path)
            except git.GitCommandError:
                repo = git.Repo(project_path)
            cls.repos[project_name] = repo
            # TODO: Use real metadata and test building
            cls.metadatas[project_name] = ProjectMetadata(
                project_name,
                cls.build_cmds[project_name],
                ["make install"],
                ["make clean"],
                project_url=f"https://github.com/{project}",
                commit_sha=cls.commit_shas[project_name])

    def insert_metadata(cls):
        for project_metadata in cls.metadatas.values():
            print(project_metadata)
            cls.metadata_storage.insert(project_metadata)

    def init_projects(cls):
        for project_name in cls.metadatas.keys():
            cls.projects[project_name] = ProjectRepo(
                cls.repo_paths[project_name],
                cls.commit_shas[project_name],
                cls.metadata_storage,
                num_cores=8,
                sentence_extraction_method=SentenceExtractionMethod.HEURISTIC)


class TestLooper(unittest.TestCase):
    """
    Tests for `Looper`.
    """

    @classmethod
    def setUpClass(cls):
        """
        Use the base constructor, with some additions.
        """
        cls.tester = DatasetFactory()

    @classmethod
    def tearDownClass(cls):
        """
        Remove the cloned repos.
        """
        for project_name, repo in cls.tester.repos.items():
            del repo
            shutil.rmtree(os.path.join(cls.tester.repo_paths[project_name]))

    def test_looper(self):
        """
        Test instantiation with `ProjectRepo`.
        """
        looper = Looper(self.tester.dataset)
        looper()


if __name__ == "__main__":
    unittest.main()
