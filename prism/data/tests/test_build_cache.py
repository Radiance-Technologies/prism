"""
Test suite for `prism.data.build_cache`.
"""
import shutil
import typing
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import List, Optional, Union

import seutil.io as io

from prism.data.build_cache import (
    CacheObjectStatus,
    CoqProjectBuildCacheClient,
    CoqProjectBuildCacheProtocol,
    CoqProjectBuildCacheServer,
    ProjectBuildEnvironment,
    ProjectBuildResult,
    ProjectCommitData,
    VernacCommandData,
    VernacCommandDataList,
    VernacSentence,
)
from prism.data.dataset import CoqProjectBaseDataset
from prism.interface.coq.goals import Goals, GoalsDiff
from prism.interface.coq.ident import Identifier, IdentType, get_all_idents
from prism.interface.coq.serapi import SerAPI
from prism.language.gallina.analyze import SexpInfo
from prism.language.heuristic.util import ParserUtils
from prism.language.sexp.list import SexpList
from prism.language.sexp.string import SexpString
from prism.project.base import SEM, SentenceExtractionMethod
from prism.project.metadata.storage import MetadataStorage
from prism.project.repo import ProjectRepo
from prism.tests import _PROJECT_EXAMPLES_PATH
from prism.util.opam import OpamAPI

TEST_DIR = Path(__file__).parent


class TestVernacSentence(unittest.TestCase):
    """
    Test suite for `VernacSentence`.
    """

    def test_serialization(self) -> None:
        """
        Verify that `VernacSentence` can be serialize/deserialized.
        """
        goals: List[Optional[Union[Goals, GoalsDiff]]] = []
        asts = []
        commands = [
            "Lemma foobar : unit.",
            "shelve.",
            "Unshelve.",
            "exact tt.",
            "Qed."
        ]
        with SerAPI() as serapi:
            goals.append(serapi.query_goals())
            for c in commands:
                _, _, ast = serapi.execute(c, return_ast=True)
                goals.append(serapi.query_goals())
                asts.append(ast)
        # force multiple added goals
        assert isinstance(goals[1], Goals)
        assert isinstance(goals[2], Goals)
        goals[2].foreground_goals = [
            deepcopy(g) for g in goals[1].foreground_goals * 3
        ]
        goals[2].foreground_goals[0].id += 1
        goals[2].foreground_goals[1].id += 2
        goals[2].shelved_goals.append(goals[2].foreground_goals[0])
        goals = goals[0 : 1] + [
            GoalsDiff.compute_diff(g1,
                                   g2)
            if isinstance(g1,
                          Goals) and isinstance(g2,
                                                Goals) else g2 for g1,
            g2 in zip(goals,
                      goals[1 :])
        ]
        sentences = [
            VernacSentence(
                c,
                a,
                [
                    Identifier(IdentType.lident,
                               "lemma"),
                    Identifier(IdentType.CRef,
                               "unit")
                ],
                SexpInfo.Loc("test_build_cache.py",
                             0,
                             0,
                             0,
                             0,
                             0,
                             0),
                "CommandType",
                g,
                get_identifiers=lambda ast: typing.cast(
                    list,
                    get_all_idents(ast,
                                   True))) for c,
            a,
            g in zip(commands,
                     asts,
                     goals)
        ]
        with NamedTemporaryFile("w") as f:
            with self.subTest("serialize"):
                io.dump(f.name, sentences, fmt=io.Fmt.yaml)
            with self.subTest("deserialize"):
                loaded = io.load(f.name, io.Fmt.yaml, clz=List[VernacSentence])
                self.assertEqual(loaded, sentences)


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
            cache_client: CoqProjectBuildCacheProtocol = CoqProjectBuildCacheClient(
                cache_server,
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
                    for sentence in project.get_sentences(
                            filename,
                            sentence_extraction_method=SEM.HEURISTIC,
                            return_locations=True,
                            glom_proofs=False):
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
                            "yml"
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
                cache: CoqProjectBuildCacheProtocol = CoqProjectBuildCacheClient(
                    cache_server,
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
                item2 = ProjectCommitData(
                    metadata,
                    {},
                    None,
                    None,
                    None,
                    environment,
                    failed_build_result)
                cache.write_build_error_log(metadata, True, failed_build_result)
                cache.write(item2, block=True)
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
                        "success"),
                    CacheObjectStatus(
                        "float",
                        40 * "a",
                        "8.10.2",
                        "other error"),
                    CacheObjectStatus(
                        "float",
                        40 * "b",
                        "8.10.2",
                        "build error"),
                    CacheObjectStatus(
                        "lambda",
                        lambda_commit_sha,
                        "8.10.2",
                        "cache error")
                ]
                expected_status_list_success = list(
                    filter(
                        lambda x: x.status == "success",
                        expected_status_list))
                expected_status_list_failed = list(
                    filter(
                        lambda x: x.status != "success",
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
