"""
Module containing tests for the extract_cache module.
"""
import logging
import os
import shutil
import unittest
from pathlib import Path

from prism.data.build_cache import (
    CoqProjectBuildCache,
    ProjectBuildEnvironment,
    ProjectBuildResult,
    ProjectCommitData,
)
from prism.data.dataset import CoqProjectBaseDataset
from prism.data.extract_cache import extract_cache, extract_vernac_commands
from prism.project.base import SentenceExtractionMethod
from prism.project.metadata.storage import MetadataStorage
from prism.project.repo import ProjectRepo
from prism.tests import _PROJECT_EXAMPLES_PATH
from prism.util.opam import OpamAPI


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
        if not os.path.exists("./test_logs"):
            os.makedirs("./test_logs")
        cls.logger = logging.Logger(
            "test_extract_cache_logger",
            level=logging.DEBUG)
        cls.logger.addHandler(
            logging.FileHandler(
                "./test_logs/test_extract_cache_log.txt",
                mode="w"))
        cls.float_head = "a4b445bad8b8d0afb725d64472b194d234676ce0"
        cls.lambda_head = "f531eede1b2088eff15b856558ec40f177956b96"
        # go ahead and build lambda since it is shared between tests
        coq_lambda = cls.dataset.projects['lambda']
        coq_lambda.git.checkout(cls.lambda_head)
        coq_lambda.build()

    @classmethod
    def tearDownClass(cls):
        """
        Remove on-disk cache and project directories.
        """
        shutil.rmtree(cls.CACHE_DIR)
        for project_root in cls.dir_list:
            shutil.rmtree(project_root)

    def test_extract_cache(self):
        """
        Test the function to extract cache from a project.
        """
        # fake pre-existing cached data for float
        coq_float = self.dataset.projects['float']
        coq_float.git.checkout(self.float_head)
        coq_version = coq_float.coq_version
        # don't test stdout and stderr
        dummy_float_data = ProjectCommitData(
            coq_float.metadata,
            {},
            ProjectBuildEnvironment(OpamAPI.active_switch.export()),
            ProjectBuildResult(0,
                               "",
                               ""))
        self.cache.insert(dummy_float_data)
        coq_float.git.checkout(coq_float.reset_head)
        self.assertEqual(coq_float.commit_sha, coq_float.reset_head)
        # assert that lambda is not already cached
        self.assertFalse(
            self.cache.contains(('lambda',
                                 self.lambda_head,
                                 coq_version)))
        # only cache new lambda data
        for project_name, project in self.dataset.projects.items():
            if "float" in project_name.lower():
                head = self.float_head
            elif "lambda" in project_name.lower():
                head = self.lambda_head
            else:
                self.logger.debug(f"Project name: {project_name}")
                try:
                    self.logger.debug(f"Project remote: {project.remote_url}")
                except Exception:
                    pass
                self.logger.debug(f"Project folder: {project.dir_abspath}")
                continue
            project: ProjectRepo
            extract_cache(self.cache,
                          project,
                          head,
                          lambda x: {},
                          coq_version)
            self.logger.debug(f"Success {project_name}")
        # assert that the other float commit was not checked out
        self.assertEqual(coq_float.commit_sha, coq_float.reset_head)
        # assert that float was not re-cached
        self.assertEqual(
            self.cache.get('float',
                           self.float_head,
                           coq_version),
            dummy_float_data)
        # assert that lambda was cached
        self.assertTrue(
            self.cache.contains(('lambda',
                                 self.lambda_head,
                                 coq_version)))

    def test_extract_vernac_commands(self):
        """
        Test the function to extract vernac commands from a project.
        """
        output = extract_vernac_commands(self.dataset.projects['lambda'])
        self.assertTrue(output)


if __name__ == "__main__":
    unittest.main()
