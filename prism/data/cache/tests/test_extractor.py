#
# Copyright (c) 2023 Radiance Technologies, Inc.
#
# This file is part of PRISM
# (see https://github.com/orgs/Radiance-Technologies/prism).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program. If not, see
# <http://www.gnu.org/licenses/>.
#
"""
Module containing tests for the extract_cache module.
"""
import logging
import multiprocessing as mp
import os
import shutil
import unittest
from pathlib import Path
from typing import List, Tuple

import pytest

from prism.data.cache.extractor import FALLBACK_EXCEPTION_MSG, extract_cache
from prism.data.cache.server import (
    CacheStatus,
    CoqProjectBuildCacheProtocol,
    CoqProjectBuildCacheServer,
)
from prism.data.cache.types.command import CommentDict, VernacDict
from prism.data.cache.types.project import (
    ProjectBuildEnvironment,
    ProjectBuildResult,
    ProjectCommitData,
)
from prism.data.dataset import CoqProjectBaseDataset
from prism.project.base import SEM
from prism.project.metadata.storage import MetadataStorage
from prism.project.repo import ProjectRepo
from prism.tests import _PROJECT_EXAMPLES_PATH
from prism.util.opam import OpamSwitch
from prism.util.swim import SwitchManager


class TestCacheExtractor(unittest.TestCase):
    """
    Tests for extract_cache module.
    """

    TEST_DIR = Path(__file__).parent
    CACHE_DIR = TEST_DIR / "project_build_cache"
    dir_list: List[Path]
    test_switch: OpamSwitch = OpamSwitch()
    dataset: CoqProjectBaseDataset
    float_head: str
    lambda_head: str
    logger: logging.Logger
    swim: SwitchManager

    @classmethod
    def setUpCache(cls):
        """
        Set up an on-disk cache to share among all unit tests.
        """
        cls.swim = SwitchManager([cls.test_switch])
        cls.storage = MetadataStorage.load(
            _PROJECT_EXAMPLES_PATH / "project_metadata.yml")
        cls.dir_list = [
            _PROJECT_EXAMPLES_PATH / p for p in cls.storage.projects
        ]
        cls.dataset = CoqProjectBaseDataset(
            project_class=ProjectRepo,
            dir_list=cls.dir_list,
            metadata_storage=cls.storage,
            sentence_extraction_method=SEM.HEURISTIC)
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
        # go ahead and checkout lambda
        coq_lambda = cls.dataset.projects['lambda']
        coq_lambda.git.checkout(cls.lambda_head)

    @classmethod
    def tearDownCache(cls):
        """
        Remove on-disk cache and project directories.
        """
        if os.path.exists(cls.CACHE_DIR):
            shutil.rmtree(cls.CACHE_DIR)
        for project_root in cls.dir_list:
            if os.path.exists(project_root):
                shutil.rmtree(project_root)

    def _extract_cache(self, build_error_expected: bool = False, **kwargs):
        """
        Test the function to extract cache from a project.
        """
        manager = mp.Manager()
        with CoqProjectBuildCacheServer() as cache_server:
            cache_client: CoqProjectBuildCacheProtocol = cache_server.Client(
                self.CACHE_DIR,
            )
            # fake pre-existing cached data for float
            coq_float = self.dataset.projects['float']
            coq_float.git.checkout(self.float_head)
            coq_version = coq_float.coq_version
            dummy_float_data = ProjectCommitData(
                coq_float.metadata,
                {},
                None,
                None,
                {},
                ProjectBuildEnvironment(self.test_switch.export()),
                ProjectBuildResult(0,
                                   "",
                                   ""))
            cache_client.write(dummy_float_data)
            coq_float.git.checkout(coq_float.reset_head)
            self.assertEqual(coq_float.commit_sha, coq_float.reset_head)
            # assert that lambda is not already cached
            self.assertFalse(
                cache_client.contains(
                    ('lambda',
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
                        self.logger.debug(
                            f"Project remote: {project.remote_url}")
                    except Exception:
                        pass
                    self.logger.debug(f"Project folder: {project.dir_abspath}")
                    continue
                semaphore = manager.BoundedSemaphore(4)

                def _fallback(
                        project: ProjectRepo) -> Tuple[VernacDict,
                                                       CommentDict]:
                    raise NotImplementedError(FALLBACK_EXCEPTION_MSG)

                extract_cache(
                    cache_client,
                    self.swim,
                    project,
                    head,
                    _fallback,
                    coq_version,
                    block=True,
                    worker_semaphore=semaphore,
                    **kwargs)
                self.logger.debug(f"Success {project_name}")
            # assert that the other float commit was not checked out
            self.assertEqual(coq_float.commit_sha, coq_float.reset_head)
            # assert that float was not re-cached
            self.assertEqual(
                cache_client.get('float',
                                 self.float_head,
                                 coq_version),
                dummy_float_data)
            # assert that lambda was cached
            if not build_error_expected:
                self.assertTrue(
                    cache_client.contains(
                        ('lambda',
                         self.lambda_head,
                         coq_version)))
            else:
                self.assertEqual(
                    cache_client.get_status(
                        'lambda',
                        self.lambda_head,
                        coq_version),
                    CacheStatus.BUILD_ERROR)
            self.assertTrue(
                cache_client.contains(
                    ('lambda',
                     self.lambda_head,
                     coq_version,
                     'txt')))

        return cache_client, cache_server

    @pytest.mark.coq_8_10_2
    def test_extract_cache_limited_runtime(self):
        """
        Test the function to extract cache from a project.
        """
        try:
            self.setUpCache()
            self._extract_cache(max_runtime=0, build_error_expected=True)
        finally:
            self.tearDownCache()

    @pytest.mark.coq_8_10_2
    def test_extract_cache_limited_memory(self):
        """
        Test the function to extract cache from a project.
        """
        try:
            self.setUpCache()
            self._extract_cache(max_memory=20000, build_error_expected=True)
        finally:
            self.tearDownCache()

    @pytest.mark.coq_8_10_2
    def test_extract_cache(self):
        """
        Test the function to extract cache from a project.
        """
        try:
            self.setUpCache()
            self._extract_cache(build_error_expected=False)
        finally:
            self.tearDownCache()


if __name__ == "__main__":
    unittest.main()
