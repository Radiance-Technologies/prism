"""
Test suite for `prism.data.build_cache`.
"""
import shutil
import unittest
from pathlib import Path
from typing import Set

from prism.data.build_cache import (
    CoqProjectBuildCache,
    ProjectCommitData,
    VernacCommandData,
)
from prism.data.dataset import CoqProjectBaseDataset
from prism.language.gallina.analyze import SexpInfo
from prism.language.heuristic.util import ParserUtils
from prism.project import ProjectRepo
from prism.project.base import SentenceExtractionMethod
from prism.project.metadata.storage import MetadataStorage
from prism.tests import _PROJECT_EXAMPLES_PATH

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
        for project in self.dataset.projects.values():
            command_data = {}
            for filename in project.get_file_list():
                file_commands: Set[VernacCommandData] = command_data.setdefault(
                    filename,
                    set())
                doc = project.get_file(filename)
                beg_char_idx = 0
                end_char_idx = 0
                for (sentence_idx,
                     sentence) in enumerate(project.extract_sentences(
                         doc,
                         sentence_extraction_method=project
                         .sentence_extraction_method)):
                    end_char_idx += len(sentence)
                    command_type, identifier = ParserUtils.extract_identifier(sentence)
                    file_commands.add(
                        VernacCommandData(
                            identifier,
                            command_type,
                            SexpInfo.Loc(
                                filename,
                                sentence_idx,
                                0,
                                sentence_idx,
                                0,
                                beg_char_idx,
                                end_char_idx),
                            None))
                    beg_char_idx = end_char_idx
                break  # one file is enough to test
            data = ProjectCommitData(project.metadata, command_data)
            expected_path = (
                self.cache_dir / project.name / data.project_metadata.commit_sha
                / '.'.join(
                    [
                        data.project_metadata.coq_version.replace(".",
                                                                  "_"),
                        self.cache.fmt_ext
                    ]))
            with self.subTest(f"get_path_{project.name}"):
                self.assertEqual(
                    expected_path,
                    self.cache.get_path_from_data(data))
            with self.subTest(f"update_{project.name}_fail"):
                with self.assertRaises(RuntimeError):
                    self.cache.update(data)
                self.assertFalse(
                    Path(self.cache.get_path_from_data(data)).exists())
            with self.subTest(f"insert_{project.name}"):
                self.cache.insert(data)
                with self.assertRaises(RuntimeError):
                    self.cache.insert(data)
                self.assertTrue(
                    Path(self.cache.get_path_from_data(data)).exists())
            with self.subTest(f"update_{project.name}"):
                self.cache.update(data)
            with self.subTest(f"get_{project.name}"):
                retrieved = self.cache.get(
                    project.name,
                    data.project_metadata.commit_sha,
                    data.project_metadata.coq_version)
                self.assertEqual(retrieved, data)

    @classmethod
    def setUpClass(cls) -> None:
        """
        Set up an on-disk cache to share among all unit tests.
        """
        cls.cache = CoqProjectBuildCache(cls.cache_dir)
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
