"""
Test module for prism.project.repo module.
"""
import os
import unittest

from prism.project.repo import commit_dict_factory

TEST_DIR = os.path.dirname(__file__)
PROJECT_DIR = os.path.dirname(TEST_DIR)
PRISM_DIR = os.path.dirname(PROJECT_DIR)
REPO_DIR = os.path.dirname(PRISM_DIR)


class TestProject(unittest.TestCase):
    """
    Class for testing coqgym_base module.
    """

    @classmethod
    def setUpClass(cls):
        """
        Set up class for testing coqgym_base module.
        """

    def test_commit_dict(self):
        """
        Test factory function for commit_dict.
        """
        commit_dict = commit_dict_factory(REPO_DIR)
        first_hash = "1aa5cfb2240df880f6c1d457f66c4b0a01e0a1aa"
        first_node = commit_dict[first_hash]
        self.assertTrue(first_node.parent is None)
        self.assertTrue(first_node.child is not None)

        second_hash = "29a790c002f8e797a01fb87b64fc2db85d147e25"
        self.assertTrue(first_node.child.hexsha == second_hash)
        second_node = commit_dict[second_hash]

        third_hash = "d689b50282393a74d43ea811ba232e5f2206aa0e"
        self.assertTrue(second_node.parent.hexsha == first_hash)
        self.assertTrue(second_node.child.hexsha == third_hash)


if __name__ == "__main__":
    unittest.main()
