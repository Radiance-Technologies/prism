"""
Test module for prism.project.repo module.
"""
import os
import shutil
import unittest

import git

from prism.project import ProjectRepo, SentenceExtractionMethod
from prism.project.metadata import ProjectMetadata
from prism.project.repo import CommitIterator, CommitTraversalStrategy

TEST_DIR = os.path.dirname(__file__)
PROJECT_DIR = os.path.dirname(TEST_DIR)
PRISM_DIR = os.path.dirname(PROJECT_DIR)
REPO_DIR = os.path.dirname(PRISM_DIR)

GEOCOQ_COMMIT_138 = "09a02dc56715b3308689843dd872209262beb5af"
GEOCOQ_COMMIT_137 = "b67cdbb28c93286126bfda514d5aafc370f09f75"
GEOCOQ_COMMIT_136 = "f67bb0495882db6ad8c5cf6fb81c7ed8542541f7"
GEOCOQ_COMMIT_135 = "296c0a9ab3d8edb031979c6ab2a9951b8c0ee63d"
GEOCOQ_COMMIT_134 = "25917f56a3b46843690457b2bfd83168bed1321c"

GEOCOQ_COMMIT_1 = "86e2cfed3e7ad2308051f011f1d2a0c4799ea350"
GEOCOQ_COMMIT_2 = "bcbbc55554a4ef77da3d79949e1ac0d7e83a43d5"
GEOCOQ_COMMIT_3 = "212eee5df43a1b3c4fdfab8be5e0f3f9afb41c6d"
GEOCOQ_COMMIT_4 = "4948ebee64e375ea42c91798dc18d2f5b16ef669"
GEOCOQ_COMMIT_5 = "46ca71de544769ec2a50d4f5ac73f2bd27b0033c"

class TestCommitIter(unittest.TestCase):
    """
    Class for testing CommitIter class.
    """

    @classmethod
    def setUpClass(cls):
        """
        Use the base constructor, with some additions.
        """
        cls.test_path = os.path.dirname(__file__)
        # HEAD commits as of March 14, 2022
        cls.project_names = {"circuits",
                             "GeoCoq"}
        cls.master_hashes = {
            "circuits": "f2cec6067f2c58e280c5b460e113d738b387be15",
            "GeoCoq": "25917f56a3b46843690457b2bfd83168bed1321c"
        }
        cls.target_projects = {
            "circuits": "coq-contribs/circuits",
            "GeoCoq": "GeoCoq/GeoCoq"
        }
        cls.repo_paths = {}
        cls.repos = {}
        cls.projects = {}
        cls.metadatas = {}
        for project_name, project in cls.target_projects.items():
            project_path = os.path.join(cls.test_path, project_name)
            cls.repo_paths[project_name] = project_path
            try:
                repo = git.Repo.clone_from(
                    f"https://github.com/{project}",
                    project_path)
            except git.GitCommandError:
                repo = git.Repo(project_path)
            cls.repos[project_name] = repo
            # TODO: Use real metadata and test building
            cls.metadatas[project_name] = ProjectMetadata(
                project_name,
                ["make"],
                ["make install"],
                ["make clean"])
            cls.projects[project_name] = ProjectRepo(
                project_path,
                cls.metadatas[project_name],
                sentence_extraction_method=SentenceExtractionMethod.HEURISTIC)

    def test_iterator_newest_first(self):
        """
        Test iterator basic functionality.
        """
        repo = self.projects['GeoCoq']
        counter = 0
        hashes = [
            GEOCOQ_COMMIT_134,
            GEOCOQ_COMMIT_135,
            GEOCOQ_COMMIT_136,
            GEOCOQ_COMMIT_137,
            GEOCOQ_COMMIT_138
        ]
        for commit in CommitIterator(repo, GEOCOQ_COMMIT_134):
            if counter == 3:
                break
            print(counter, commit.hexsha, flush=True)
            self.assertTrue(commit.hexsha == hashes[counter])
            counter += 1

    def test_iterator_oldest_first(self):
        """
        Test iterator oldest first functionality.
        """
        repo = self.projects['GeoCoq']
        counter = 0
        hashes = [
            GEOCOQ_COMMIT_3,
            GEOCOQ_COMMIT_2,
            GEOCOQ_COMMIT_1,
            GEOCOQ_COMMIT_4,
            GEOCOQ_COMMIT_5
        ]
        for commit in CommitIterator(repo,
                                     GEOCOQ_COMMIT_3,
                                     CommitTraversalStrategy.OLD_FIRST):
            if counter == 5:
                break
            print(counter, commit.hexsha, flush=True)
            self.assertTrue(commit.hexsha == hashes[counter])
            counter += 1

    def test_iterator_curlicue_new(self):
        """
        Test iterator curlicue new functionality.
        """
        repo = self.projects['GeoCoq']
        counter = 0
        hashes = [
            GEOCOQ_COMMIT_3,
            GEOCOQ_COMMIT_2,
            GEOCOQ_COMMIT_4,
            GEOCOQ_COMMIT_1,
            GEOCOQ_COMMIT_5
        ]
        for commit in CommitIterator(repo,
                                     GEOCOQ_COMMIT_3,
                                     CommitTraversalStrategy.CURLICUE_NEW):
            if counter == 5:
                break
            print(counter, commit.hexsha, flush=True)
            self.assertTrue(commit.hexsha == hashes[counter])
            counter += 1

    def test_iterator_curlicue_old(self):
        """
        Test iterator curlicue old functionality.
        """
        repo = self.projects['GeoCoq']
        counter = 0
        hashes = [
            GEOCOQ_COMMIT_3,
            GEOCOQ_COMMIT_4,
            GEOCOQ_COMMIT_2,
            GEOCOQ_COMMIT_5,
            GEOCOQ_COMMIT_1
        ]
        for commit in CommitIterator(repo,
                                     GEOCOQ_COMMIT_3,
                                     CommitTraversalStrategy.CURLICUE_OLD):
            if counter == 5:
                break
            print(counter, commit.hexsha, flush=True)
            self.assertTrue(commit.hexsha == hashes[counter])
            counter += 1

    @classmethod
    def tearDownClass(cls):
        """
        Remove the cloned repos.
        """
        for project_name, repo in cls.repos.items():
            del repo
            shutil.rmtree(os.path.join(cls.repo_paths[project_name]))


if __name__ == "__main__":
    unittest.main()
