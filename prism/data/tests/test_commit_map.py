"""
Test module for `prism.data.commit_map` module.
"""
import unittest

from prism.data.commit_map import ProjectCommitMapper
from prism.tests.factories import DatasetFactory


def get_commit_iterator(p):
    """
    Get commit iterator (this is an example).
    """
    return [p.commit().hexsha]


def process_commit(p, c):
    """
    Process commit (this is an example).
    """
    p.git.checkout(c)
    p.build()


class TestProjectCommitMapper(unittest.TestCase):
    """
    Tests for `ProjectCommitMapper`.
    """

    @classmethod
    def setUpClass(cls):
        """
        Use the base constructor, with some additions.
        """
        cls.tester = DatasetFactory()

    @classmethod
    def tearDownClass(cls):
        """
        Remove the cloned repos.
        """
        cls.tester.cleanup()

    def test_ProjectCommitMapper(self):
        """
        Test instantiation with `ProjectRepo`.
        """
        project_looper = ProjectCommitMapper(
            self.tester.dataset,
            get_commit_iterator,
            process_commit)
        project_looper(self.tester.test_path)


if __name__ == "__main__":
    unittest.main()
