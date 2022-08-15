"""
Test module for `prism.data.commit_map` module.
"""
import time
import unittest
from typing import List, Optional

from prism.data.commit_map import ProjectCommitMapper
from prism.tests.factories import DatasetFactory

from ...project.repo import ProjectRepo


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


def get_multi_commit_iterator(p):
    """
    Get an iterator over multiple commits.
    """
    return [p.commit().hexsha, p.commit().hexsha]


def sleepy_process_commit(p: ProjectRepo,
                          c: str,
                          results: Optional[List[str]]) -> List[str]:
    """
    Either raise an error or sleep through a SIGTERM.
    """
    if p.name != 'bellantonicook':
        import random
        time.sleep(1 + random.random() * 3)
        if results is None:
            results = []
        results.append(f'Success {p.name}')
        return results
    else:
        time.sleep(0.25)
        raise Exception(f"Failure: {p.name}")


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
            process_commit,
            "Test mapping")
        result = project_looper()
        self.assertEqual(result,
                         {})

    def test_graceful_exit(self):
        """
        Test that processes can be concluded gracefully if one fails.
        """
        project_looper = ProjectCommitMapper(
            self.tester.dataset,
            get_commit_iterator,
            sleepy_process_commit,
            "Test graceful exits")
        # only one result expected per child
        expected_result = {'Success coq-cunit',
                           'Success circuits'}
        result = project_looper(3)
        self.assertEqual(set(result), expected_result)


if __name__ == "__main__":
    unittest.main()
