"""
Test suite for `prism.data.build_cache`.
"""
import shutil
import unittest
from pathlib import Path
from typing import List

from prism.data.build_cache import (
    CoqProjectBuildCacheClient,
    CoqProjectBuildCacheProtocol,
    CoqProjectBuildCacheServer,
    ProjectBuildEnvironment,
    ProjectBuildResult,
    ProjectCommitData,
    VernacCommandData,
    VernacSentence,
)
from prism.data.dataset import CoqProjectBaseDataset
from prism.interface.coq.goals import Goals
from prism.language.heuristic.util import ParserUtils
from prism.language.sexp.list import SexpList
from prism.language.sexp.string import SexpString
from prism.project.base import SEM, SentenceExtractionMethod
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

    def test_project_build_cache(self):
        """
        Test all aspects of the cache with subtests.
        """
        projects: List[ProjectRepo] = list(self.dataset.projects.values())
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
                    file_commands: List[
                        VernacCommandData] = command_data.setdefault(
                            filename,
                            list())
                    for sentence in project.get_sentences(
                            filename,
                            sentence_extraction_method=SEM.HEURISTIC,
                            return_locations=True,
                            glom_proofs=False):
                        location = sentence.location
                        sentence = sentence.text
                        command_type, identifier = \
                            ParserUtils.extract_identifier(sentence)
                        file_commands.append(
                            VernacCommandData(
                                [identifier],
                                None,
                                VernacSentence(
                                    str(sentence),
                                    SexpList(
                                        [SexpString("foo"),
                                         SexpString("bar")]),
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
                    environment,
                    uneventful_result)
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
                with self.subTest(f"update_{project.name}_fail"):
                    self.assertFalse(
                        Path(cache_client.get_path_from_data(data)).exists())
                with self.subTest(f"insert_{project.name}"):
                    cache_client.insert(data, block=True)
                    self.assertTrue(
                        Path(cache_client.get_path_from_data(data)).exists())
                with self.subTest(f"update_{project.name}"):
                    cache_client.update(data, block=True)
                with self.subTest(f"get_{project.name}"):
                    retrieved = cache_client.get(
                        project.name,
                        data.project_metadata.commit_sha,
                        data.project_metadata.coq_version)
                    self.assertEqual(retrieved, data)

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
