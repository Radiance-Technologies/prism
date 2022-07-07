"""
Test module for prism.data.coqgym.dataset module.
"""
import os
import shutil
import unittest

import git

from prism.data.dataset import CoqGymBaseDataset
from prism.project import ProjectRepo, SentenceExtractionMethod
from prism.project.metadata import ProjectMetadata
from prism.project.metadata.storage import MetadataStorage

from prism.data.cache import Looper


class TestCoqGymBaseDataset(unittest.TestCase):
    """
    Tests for `CoqGymBaseDataset`.
    """

    @classmethod
    def setUpClass(cls):
        """
        Use the base constructor, with some additions.
        """
        cls.test_path = os.path.dirname(__file__)
        # HEAD commits as of March 14, 2022
        cls.project_names = {"CompCert",
                             "circuits",
                             "GeoCoq"}
        cls.master_hashes = {
            "CompCert": "9d3521b4db46773239a2c5f9f6970de826075508",
            "circuits": "f2cec6067f2c58e280c5b460e113d738b387be15",
            "GeoCoq": "25917f56a3b46843690457b2bfd83168bed1321c"
        }
        cls.target_projects = {
            "CompCert": "AbsInt/CompCert",
            "circuits": "coq-contribs/circuits",
            "GeoCoq": "GeoCoq/GeoCoq"
        }
        cls.repo_paths = {}
        cls.repos = {}
        cls.projects = {}
        cls.metadatas = {}
        cls.metadata_storage = MetadataStorage()
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
                ["make"],
                ["make install"],
                ["make clean"])
        for project_metadata in cls.metadatas.values():
            cls.metadata_storage.insert(project_metadata)
        for project_name in cls.metadatas.keys():
            cls.projects[project_name] = ProjectRepo(
                cls.repo_paths[project_name],
                cls.metadata_storage,
                sentence_extraction_method=SentenceExtractionMethod.HEURISTIC)
        cls.dataset = CoqGymBaseDataset(
            project_class=ProjectRepo,
            projects=cls.projects)

    @classmethod
    def tearDownClass(cls):
        """
        Remove the cloned repos.
        """
        for project_name, repo in cls.repos.items():
            del repo
            shutil.rmtree(os.path.join(cls.repo_paths[project_name]))

    def test_init_with_project_repo_and_dir_list(self):
        """
        Test instantiation with `ProjectRepo` using `base_dir` arg.
        """
        dataset = CoqGymBaseDataset(
            project_class=ProjectRepo,
            dir_list=self.repo_paths.values(),
            metadata_storage=MetadataStorage(),
            sentence_extraction_method=SentenceExtractionMethod.HEURISTIC)
        looper = Looper(dataset)
        looper()
        self.fail()


if __name__ == "__main__":
    unittest.main()
