"""
Module containing tests for the extract_cache module.
"""
import unittest
from pathlib import Path

from prism.data.build_cache import CoqProjectBuildCache
from prism.data.dataset import CoqProjectBaseDataset
from prism.data.extract_cache import extract_cache, extract_vernac_commands
from prism.data.tests.test_dataset import TestCoqProjectBaseDataset
from prism.project.base import SentenceExtractionMethod
from prism.project.metadata.storage import MetadataStorage
from prism.project.repo import ProjectRepo
from prism.tests import _PROJECT_EXAMPLES_PATH

TEST_DIR = Path(__file__).parent
CACHE_DIR = TEST_DIR / "project_build_cache"


class TestExtractCache(unittest.TestCase):
    """
    Tests for extract_cache module.
    """

    # Borrow setup and teardown CMs from dataset tests
    setUpClass = classmethod(TestCoqProjectBaseDataset.setUpClass.__func__)
    tearDownClass = classmethod(
        TestCoqProjectBaseDataset.tearDownClass.__func__)

    def test_extract_vernac_commands(self):
        """
        Test the function to extract vernac commands from a project.
        """
        output = extract_vernac_commands(self.projects['circuits'])
        print(output)
        self.assertTrue(output)

    def test_extract_cache(self):
        """
        Test the function to extract cache from a project.
        """
        cache = CoqProjectBuildCache(CACHE_DIR)
        storage = MetadataStorage.load(
            _PROJECT_EXAMPLES_PATH / "project_metadata.yml")
        dir_list = [_PROJECT_EXAMPLES_PATH / p for p in storage.projects]
        dataset = CoqProjectBaseDataset(
            project_class=ProjectRepo,
            dir_list=dir_list,
            metadata_storage=storage,
            sentence_extraction_method=SentenceExtractionMethod.HEURISTIC)
        for project in dataset.projects.values():
            project: ProjectRepo
            extract_cache(
                '8.10.2',
                cache,
                project,
                project.reset_head,
                lambda x: None)


if __name__ == "__main__":
    # Using unittest.main() runs all the TestCoqProjectBaseDataset
    # tests since that class is imported, so I've gone a more direct
    # route for inovking the test class for debugging.
    # <TODO>: It would be cleaner to extract the setup and tear-down
    # from TestCoqProjectBaseDataset as separately importable functions
    # or something similar.
    test = TestExtractCache()
    test.setUpClass()
    test.test_extract_vernac_commands()
    test.test_extract_cache()
    test.tearDownClass()
