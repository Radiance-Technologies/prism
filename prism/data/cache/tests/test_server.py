"""
Test suite for `prism.data.cache.server`.
"""
import os
import shutil
import typing
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List

from prism.data.cache.server import (
    CacheObjectStatus,
    CacheStatus,
    CoqProjectBuildCache,
    CoqProjectBuildCacheProtocol,
    CoqProjectBuildCacheServer,
)
from prism.data.cache.types import (
    VernacCommandData,
    VernacCommandDataList,
    VernacSentence,
)
from prism.data.cache.types.project import (
    ProjectBuildEnvironment,
    ProjectBuildResult,
    ProjectCommitData,
)
from prism.data.dataset import CoqProjectBaseDataset
from prism.interface.coq.goals import Goals
from prism.interface.coq.ident import Identifier, IdentType
from prism.language.heuristic.parser import CoqSentence
from prism.language.heuristic.util import ParserUtils
from prism.language.sexp.list import SexpList
from prism.language.sexp.string import SexpString
from prism.project.base import SEM, SentenceExtractionMethod
from prism.project.metadata import ProjectMetadata
from prism.project.metadata.storage import MetadataStorage
from prism.project.repo import ProjectRepo
from prism.tests import _PROJECT_EXAMPLES_PATH
from prism.util.opam import OpamAPI

TEST_DIR = Path(__file__).parent


class TestCoqProjectBuildCache(unittest.TestCase):
    """
    Test suite for `CoqProjectBuildCache`.
    """

    cache_dir = TEST_DIR / "project_build_cache"
    storage: MetadataStorage
    dir_list: List[Path]
    dataset: CoqProjectBaseDataset

    def test_project_build_cache(self):
        """
        Test all aspects of the cache with subtests.
        """
        projects = typing.cast(
            List[ProjectRepo],
            list(self.dataset.projects.values()))
        with CoqProjectBuildCacheServer() as cache_server:
            cache_client: CoqProjectBuildCacheProtocol = cache_server.Client(
                self.cache_dir)
            uneventful_result = ProjectBuildResult(0, "", "")
            environment = ProjectBuildEnvironment(
                OpamAPI.active_switch.export())
            for project in projects:
                command_data = {}
                project: ProjectRepo
                for filename in project.get_file_list():
                    file_commands: VernacCommandDataList = command_data.setdefault(
                        filename,
                        VernacCommandDataList())
                    for sentence in typing.cast(
                            List[CoqSentence],
                            project.get_sentences(
                                filename,
                                sentence_extraction_method=SEM.HEURISTIC,
                                return_locations=True,
                                glom_proofs=False)):
                        location = sentence.location
                        assert location is not None
                        sentence = sentence.text
                        command_type, identifier = \
                            ParserUtils.extract_identifier(sentence)
                        file_commands.append(
                            VernacCommandData(
                                [identifier],
                                None,
                                VernacSentence(
                                    str(sentence),
                                    str(
                                        SexpList(
                                            [
                                                SexpString("foo"),
                                                SexpString("bar")
                                            ])),
                                    [
                                        Identifier(
                                            IdentType.Ser_Qualid,
                                            f"{filename}.foo")
                                    ],
                                    location,
                                    command_type,
                                    Goals([],
                                          [],
                                          [],
                                          []))))
                    break  # one file is enough to test
                data = ProjectCommitData(
                    project.metadata,
                    command_data,
                    None,
                    None,
                    None,
                    environment,
                    uneventful_result)
                assert data.project_metadata.commit_sha is not None
                assert data.project_metadata.coq_version is not None
                expected_path = (
                    self.cache_dir / project.name
                    / data.project_metadata.commit_sha / '.'.join(
                        [
                            data.project_metadata.coq_version.replace(".",
                                                                      "_"),
                            "json"
                        ]))
                with self.subTest(f"get_path_{project.name}"):
                    self.assertEqual(
                        expected_path,
                        cache_client.get_path_from_data(data))
                with self.subTest(f"get_{project.name}_fail"):
                    self.assertFalse(
                        Path(cache_client.get_path_from_data(data)).exists())
                with self.subTest(f"write_{project.name}"):
                    cache_client.write(data, block=True)
                    self.assertTrue(
                        Path(cache_client.get_path_from_data(data)).exists())
                with self.subTest(f"get_{project.name}"):
                    retrieved = cache_client.get(
                        project.name,
                        data.project_metadata.commit_sha,
                        data.project_metadata.coq_version)
                    self.assertEqual(retrieved, data)

    def test_list_status(self):
        """
        Test methods in cache class to get information from cache.
        """
        with TemporaryDirectory() as temp_dir:
            with CoqProjectBuildCacheServer() as cache_server:
                cache: CoqProjectBuildCacheProtocol = cache_server.Client(
                    temp_dir)
                environment = ProjectBuildEnvironment(
                    OpamAPI.active_switch.export())
                metadata = self.dataset.projects["float"].metadata
                float_commit_sha = metadata.commit_sha
                assert float_commit_sha is not None
                item1 = ProjectCommitData(
                    metadata,
                    {},
                    None,
                    None,
                    None,
                    environment,
                    ProjectBuildResult(0,
                                       "",
                                       ""))
                cache.write(item1, block=True)
                metadata = self.dataset.projects["lambda"].metadata
                lambda_commit_sha = metadata.commit_sha
                assert lambda_commit_sha is not None
                cache.write_cache_error_log(
                    metadata,
                    True,
                    "Lambda cache error")
                metadata = self.dataset.projects["float"].metadata
                metadata.commit_sha = 40 * "a"
                cache.write_misc_error_log(metadata, True, "float misc error")
                metadata = self.dataset.projects["float"].metadata
                metadata.commit_sha = 40 * "b"
                failed_build_result = ProjectBuildResult(
                    1,
                    "build error",
                    "build_error")
                cache.write_build_error_log(metadata, True, failed_build_result)
                expected_project_list = ["float", "lambda"]
                expected_commit_lists = {
                    "float": [40 * "a",
                              float_commit_sha,
                              40 * "b"],
                    "lambda": [lambda_commit_sha]
                }
                expected_status_list = [
                    CacheObjectStatus(
                        "float",
                        float_commit_sha,
                        "8.10.2",
                        CacheStatus.SUCCESS),
                    CacheObjectStatus(
                        "float",
                        40 * "a",
                        "8.10.2",
                        CacheStatus.OTHER_ERROR),
                    CacheObjectStatus(
                        "float",
                        40 * "b",
                        "8.10.2",
                        CacheStatus.BUILD_ERROR),
                    CacheObjectStatus(
                        "lambda",
                        lambda_commit_sha,
                        "8.10.2",
                        CacheStatus.CACHE_ERROR)
                ]
                expected_status_list_success = list(
                    filter(
                        lambda x: x.status == CacheStatus.SUCCESS,
                        expected_status_list))
                expected_status_list_failed = list(
                    filter(
                        lambda x: x.status != CacheStatus.SUCCESS,
                        expected_status_list))
                project_list = cache.list_projects()
                commit_lists = cache.list_commits()
                status_list = cache.list_status()
                status_list_success = cache.list_status_success_only()
                status_list_failed = cache.list_status_failed_only()
                self.assertCountEqual(project_list, expected_project_list)
                self.assertCountEqual(commit_lists, expected_commit_lists)
                self.assertCountEqual(status_list, expected_status_list)
                self.assertCountEqual(
                    status_list_success,
                    expected_status_list_success)
                self.assertCountEqual(
                    status_list_failed,
                    expected_status_list_failed)

    def test_clear_error_files(self) -> None:
        """
        Verify clear_error_files method works as expected.

        Once an error log is written, it should not be cleared by
        clear_error_files until we artificially advance the cache's
        start_time, then it should get deleted.
        """
        with TemporaryDirectory() as temp_dir:
            cache = CoqProjectBuildCache(temp_dir)
            metadata: ProjectMetadata = self.dataset.projects["float"].metadata
            float_commit_sha = metadata.commit_sha
            assert float_commit_sha is not None
            failed_build_result = ProjectBuildResult(
                1,
                "warning",
                "a build error happened")
            writers = [
                cache.write_cache_error_log,
                cache.write_misc_error_log,
                cache.write_build_error_log
            ]
            messages = [
                "Float cache error",
                "Float misc error",
                failed_build_result
            ]
            expected_statuses = [
                CacheStatus.CACHE_ERROR,
                CacheStatus.OTHER_ERROR,
                CacheStatus.BUILD_ERROR
            ]
            for writer, message, expected_status in zip(
                    writers, messages, expected_statuses):
                with self.subTest(str(expected_status)):
                    writer(metadata, True, message)
                    status = cache.list_status()
                    cache.clear_error_files(metadata)
                    self.assertEqual(
                        status,
                        [
                            CacheObjectStatus(
                                "float",
                                float_commit_sha,
                                "8.10.2",
                                expected_status)
                        ])
                    cache.start_time += 1.
                    cache.clear_error_files(metadata)
                    self.assertCountEqual(cache.list_status(), [])
            self.assertEqual(
                os.listdir((Path(temp_dir) / 'float') / float_commit_sha),
                [])

    @classmethod
    def setUpClass(cls) -> None:
        """
        Set up an on-disk cache to share among all unit tests.
        """
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
    def tearDownClass(cls) -> None:
        """
        Remove on-disk cache and project directories.
        """
        shutil.rmtree(cls.cache_dir)
        for project_root in cls.dir_list:
            shutil.rmtree(project_root)


if __name__ == "__main__":
    unittest.main()
