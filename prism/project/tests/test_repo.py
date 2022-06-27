"""
Test module for prism.project.repo module.
"""
import os
import unittest

from git import Commit, Repo

from prism.project.repo import commit_dict_factory, CommitIterator

TEST_DIR = os.path.dirname(__file__)
PROJECT_DIR = os.path.dirname(TEST_DIR)
PRISM_DIR = os.path.dirname(PROJECT_DIR)
REPO_DIR = os.path.dirname(PRISM_DIR)

FIRST_HASH  = "1aa5cfb2240df880f6c1d457f66c4b0a01e0a1aa"
SECOND_HASH = "29a790c002f8e797a01fb87b64fc2db85d147e25"
THIRD_HASH  = "d689b50282393a74d43ea811ba232e5f2206aa0e"
FOURTH_HASH = "248a03133252d6a3063dc61e2ee73af228cc58aa"
FIFTH_HASH  = "7219a28b131dd91aafc9daf67ef2c295ecbff910"

HASHES = [FIRST_HASH, 
          SECOND_HASH, 
          THIRD_HASH, 
          FOURTH_HASH, 
          FIFTH_HASH]

class TestCommitIter(unittest.TestCase):
    """
    Class for testing CommitIter class.
    """

    @classmethod
    def setUpClass(cls):
        """
        Set up class for testing CommitIter class.
        """

    def test_commit_dict(self):
        """
        Test factory function for commit_dict.
        """

        commit_dict = commit_dict_factory(REPO_DIR)
        first_node = commit_dict[FIRST_HASH]
        self.assertTrue(first_node.parent is None)
        self.assertTrue(first_node.child is not None)

        self.assertTrue(first_node.child.hexsha == SECOND_HASH)
        second_node = commit_dict[SECOND_HASH]

        self.assertTrue(second_node.parent.hexsha == FIRST_HASH)
        self.assertTrue(second_node.child.hexsha == THIRD_HASH)

    def test_iterator_newest_first(self):
        """
        Test iterator basic functionality.
        """
        repo = Repo(REPO_DIR)
        counter = 0
        hashes = [THIRD_HASH, FOURTH_HASH, FIFTH_HASH]
        for commit in CommitIterator(repo, THIRD_HASH):
            if counter == 4:
                break
            self.assertTrue(commit.hexsha == hashes[counter])
            counter += 1




if __name__ == "__main__":
    unittest.main()
