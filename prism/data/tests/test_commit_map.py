"""
Test module for `prism.data.commit_map` module.
"""
import time
import unittest
from copy import copy, deepcopy
from typing import List, Optional

from prism.data.commit_map import (
    Except,
    ProjectCommitMapper,
    ProjectCommitUpdateMapper,
)
from prism.project.repo import ProjectRepo
from prism.tests.factories import DatasetFactory


def get_commit_iterator(p):
    """
    Get commit iterator (this is an example).
    """
    return [p.commit().hexsha]


def process_commit(p, c, _):
    """
    Process commit (this is an example).
    """
    p.git.checkout(c)
    p.build()
    return 1


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

    Ensure that one project fails quickly (before the other two can
    finish their first commit) to verify that subprocesses are allowed
    to finish the last commit they are working on. Also ensure that the
    failing project at least partially succeeds to verify that partial
    results can be returned with an exception.
    """
    if p.name != 'bellantonicook':
        import random
        time.sleep(1 + random.random() * 3)
        if results is None:
            results = []
        results.append(f'Success {p.name}')
        return results
    elif results is None:
        results = [f'Success {p.name}']
        return results
    else:
        time.sleep(0.25)
        raise Exception(f"Failure: {p.name}")


def volatile_process_commit(p: ProjectRepo, c: str, results: None) -> None:
    """
    Introduce fake metadata for each project.
    """
    metadata = copy(p.metadata)
    metadata.commit_sha = f"fake_{p.name}_commit"
    p.metadata_storage.insert(metadata)


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
        cls.project_names = {p for p in cls.tester.dataset.projects.keys()}

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
            self.tester.dataset.projects.values(),
            get_commit_iterator,
            process_commit,
            "Test mapping")
        result = project_looper(2)
        self.assertEqual(result,
                         {p: 1 for p in self.project_names})

    def test_graceful_exit(self):
        """
        Test that processes can be concluded gracefully if one fails.
        """
        project_looper = ProjectCommitMapper(
            self.tester.dataset.projects.values(),
            get_multi_commit_iterator,
            sleepy_process_commit,
            "Test graceful exits")
        failed_project = 'bellantonicook'
        # only one result expected per child
        expected_result = {p: [f"Success {p}"] for p in self.project_names}
        expected_result[failed_project] = Except(
            expected_result[failed_project],
            Exception(f"Failure: {failed_project}"))
        result = project_looper(3)
        self.assertEqual(
            {k: v for k,
             v in result.items() if k != failed_project},
            {k: v for k,
             v in expected_result.items() if k != failed_project})
        self.assertEqual(
            result[failed_project].value,
            expected_result[failed_project].value)
        self.assertEqual(
            type(result[failed_project].exception),
            type(expected_result[failed_project].exception))
        self.assertEqual(
            result[failed_project].exception.args,
            expected_result[failed_project].exception.args)

    def test_ProjectCommitUpdateMapper(self):
        """
        Verify that the metadata repository can be changed with maps.

        Also verify that `ProjectCommitMapper` is incapable of updating
        the metadata repo.
        """
        initial_metadata = list(
            self.tester.dataset.projects.values())[0].metadata_storage
        with self.subTest("without_update"):
            project_looper = ProjectCommitMapper(
                self.tester.dataset.projects.values(),
                get_commit_iterator,
                volatile_process_commit,
                "Test mapping without updating")
            result = project_looper(2)
            self.assertEqual(result,
                             {p: None for p in self.project_names})
            for p in project_looper.projects:
                self.assertEqual(p.metadata_storage, initial_metadata)
        expected_metadata = deepcopy(initial_metadata)
        for p in project_looper.projects:
            metadata = copy(p.metadata)
            metadata.commit_sha = f"fake_{p.name}_commit"
            expected_metadata.insert(metadata)
        expected_metadata = set(expected_metadata)
        with self.subTest("with_update"):
            project_looper = ProjectCommitUpdateMapper(
                self.tester.dataset.projects.values(),
                get_commit_iterator,
                volatile_process_commit,
                "Test mapping with updating")
            result = project_looper(2)
            self.assertEqual(result,
                             {p: None for p in self.project_names})
            for p in project_looper.projects:
                self.assertNotEqual(p.metadata_storage, initial_metadata)
                self.assertEqual(set(p.metadata_storage), expected_metadata)


if __name__ == "__main__":
    unittest.main()
