"""
Module containing tests for the extract_cache module.
"""
import shutil
import unittest
from pathlib import Path

from prism.data.build_cache import CoqProjectBuildCache
from prism.data.dataset import CoqProjectBaseDataset
from prism.data.extract_cache import extract_cache, extract_vernac_commands
from prism.project.base import SentenceExtractionMethod
from prism.project.metadata.storage import MetadataStorage
from prism.project.repo import ProjectRepo
from prism.tests import _PROJECT_EXAMPLES_PATH


class TestExtractCache(unittest.TestCase):
    """
    Tests for extract_cache module.
    """

    TEST_DIR = Path(__file__).parent
    CACHE_DIR = TEST_DIR / "project_build_cache"

    @classmethod
    def setUpClass(cls):
        """
        Set up an on-disk cache to share among all unit tests.
        """
        cls.cache = CoqProjectBuildCache(cls.CACHE_DIR)
        cls.storage = MetadataStorage.load(
            _PROJECT_EXAMPLES_PATH / "project_metadata.yml")
        cls.dir_list = [
            _PROJECT_EXAMPLES_PATH / p for p in cls.storage.projects
        ]
        cls.dataset = CoqProjectBaseDataset(
            project_class=ProjectRepo,
            dir_list=cls.dir_list,
            metadata_storage=cls.storage,
            sentence_extraction_method=SentenceExtractionMethod.HEURISTIC)

    @classmethod
    def tearDownClass(cls):
        """
        Remove on-disk cache and project directories.
        """
        shutil.rmtree(cls.CACHE_DIR)
        for project_root in cls.dir_list:
            shutil.rmtree(project_root)

    def test_extract_vernac_commands(self):
        """
        Test the function to extract vernac commands from a project.
        """
        output = extract_vernac_commands(self.dataset.projects['float'])
        self.assertTrue(output)

    def test_extract_cache(self):
        """
        Test the function to extract cache from a project.
        """
        for project in self.dataset.projects.values():
            if project.name.lower() == "float":
                head = "a4b445bad8b8d0afb725d64472b194d234676ce0"
            elif project.name.lower() == "lambda":
                head = "f531eede1b2088eff15b856558ec40f177956b96"
            else:
                head = 'master'
            project: ProjectRepo
            extract_cache(self.cache,
                          project,
                          head,
                          lambda x: {})


if __name__ == "__main__":
    unittest.main()
