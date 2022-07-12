"""
Test module for prism.data.dir module.
"""

import unittest

from prism.project.base import SentenceExtractionMethod
from prism.project.dir import ProjectDir
from prism.project.tests.test_repo import TestProjectRepo


class TestProjectDir(TestProjectRepo):
    """
    Tests for `ProjectDir`, based on `TestProjectRepo`.
    """

    @classmethod
    def setUpClass(cls):
        """
        Set the project to use `ProjectDir` instead of `ProjectRepo`.
        """
        super().setUpClass()
        cls.project = ProjectDir(
            cls.repo_path,
            cls.meta_storage,
            sentence_extraction_method=SentenceExtractionMethod.HEURISTIC)

    def test_get_random_commit(self):
        """
        Ignore; this method is not implemented in `ProjectDir`.
        """
        pass


if __name__ == '__main__':
    unittest.main()
