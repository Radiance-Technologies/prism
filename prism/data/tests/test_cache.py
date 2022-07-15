"""
Test module for prism.data.dataset module.
"""
import unittest

from prism.data.cache import ProjectLooper
from prism.tests import DatasetFactory


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


class TestProjectLooper(unittest.TestCase):
    """
    Tests for `ProjectLooper`.
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

    def test_ProjectLooper(self):
        """
        Test instantiation with `ProjectRepo`.
        """
        project_looper = ProjectLooper(
            self.tester.dataset,
            get_commit_iterator,
            process_commit)
        project_looper(self.tester.test_path)


if __name__ == "__main__":
    unittest.main()
