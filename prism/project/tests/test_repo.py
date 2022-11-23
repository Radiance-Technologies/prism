"""
Test module for prism.project.repo module.
""" """
Test module for prism.data.project module.
"""
import itertools
import os
import shutil
import unittest

import git
import networkx as nx

import prism.util.radpytools.os
from prism.project import ProjectRepo, SentenceExtractionMethod
from prism.project.metadata import ProjectMetadata
from prism.project.metadata.storage import MetadataStorage
from prism.project.repo import (
    ChangedCoqCommitIterator,
    CommitIterator,
    CommitTraversalStrategy,
)
from prism.tests import _MINIMAL_METADATA, _MINIMAL_METASTORAGE
from prism.util.build_tools.coqdep import (
    is_valid_topological_sort,
    make_dependency_graph,
)

TEST_DIR = os.path.dirname(__file__)
PROJECT_DIR = os.path.dirname(TEST_DIR)
PRISM_DIR = os.path.dirname(PROJECT_DIR)
REPO_DIR = os.path.dirname(PRISM_DIR)

GEOCOQ_COMMIT_138 = "09a02dc56715b3308689843dd872209262beb5af"
GEOCOQ_COMMIT_137 = "b67cdbb28c93286126bfda514d5aafc370f09f75"
GEOCOQ_COMMIT_136 = "f67bb0495882db6ad8c5cf6fb81c7ed8542541f7"
GEOCOQ_COMMIT_135 = "296c0a9ab3d8edb031979c6ab2a9951b8c0ee63d"
GEOCOQ_COMMIT_134 = "9872a84f9fd54feb9f1be33638b5e49c1234bde0"

GEOCOQ_COMMIT_1 = "86e2cfed3e7ad2308051f011f1d2a0c4799ea350"
GEOCOQ_COMMIT_2 = "bcbbc55554a4ef77da3d79949e1ac0d7e83a43d5"
GEOCOQ_COMMIT_3 = "4ab82c0181856f270a031e1c0cf92472e34de7e9"
GEOCOQ_COMMIT_4 = "212eee5df43a1b3c4fdfab8be5e0f3f9afb41c6d"
GEOCOQ_COMMIT_5 = "4948ebee64e375ea42c91798dc18d2f5b16ef669"


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
            cls.metadata_storage = MetadataStorage()
            for metadata in cls.metadatas.values():
                cls.metadata_storage.insert(metadata)
            cls.projects[project_name] = ProjectRepo(
                project_path,
                cls.metadata_storage,
                sentence_extraction_method=SentenceExtractionMethod.HEURISTIC)

    def test_iterator_newest_first(self):
        """
        Test iterator basic functionality.
        """
        repo = self.projects['GeoCoq']
        hashes = [
            GEOCOQ_COMMIT_134,
            GEOCOQ_COMMIT_135,
            GEOCOQ_COMMIT_136,
            GEOCOQ_COMMIT_137,
            GEOCOQ_COMMIT_138
        ]
        hashes.reverse()
        commit_iter = CommitIterator(repo, GEOCOQ_COMMIT_138)
        hashes_test = list(itertools.islice(commit_iter, 5))
        self.assertEqual(hashes, hashes_test)

    def test_iterator_oldest_first(self):
        """
        Test iterator oldest first functionality.
        """
        repo = self.projects['GeoCoq']
        hashes = [
            GEOCOQ_COMMIT_1,
            GEOCOQ_COMMIT_2,
            GEOCOQ_COMMIT_3,
            GEOCOQ_COMMIT_4,
            GEOCOQ_COMMIT_5
        ]
        commit_iter = CommitIterator(
            repo,
            march_strategy=CommitTraversalStrategy.OLD_FIRST)
        hashes_test = list(itertools.islice(commit_iter, 5))
        self.assertEqual(hashes, hashes_test)

    def test_iterator_curlicue_new(self):
        """
        Test iterator curlicue new functionality.
        """
        repo = self.projects['GeoCoq']
        hashes = [
            GEOCOQ_COMMIT_3,
            GEOCOQ_COMMIT_4,
            GEOCOQ_COMMIT_2,
            GEOCOQ_COMMIT_5,
            GEOCOQ_COMMIT_1
        ]
        commit_iter = CommitIterator(
            repo,
            GEOCOQ_COMMIT_3,
            CommitTraversalStrategy.CURLICUE_NEW)
        hashes_test = list(itertools.islice(commit_iter, 5))
        self.assertEqual(hashes, hashes_test)

    def test_iterator_curlicue_old(self):
        """
        Test iterator curlicue old functionality.
        """
        repo = self.projects['GeoCoq']
        hashes = [
            GEOCOQ_COMMIT_3,
            GEOCOQ_COMMIT_2,
            GEOCOQ_COMMIT_4,
            GEOCOQ_COMMIT_1,
            GEOCOQ_COMMIT_5
        ]
        commit_iter = CommitIterator(
            repo,
            GEOCOQ_COMMIT_3,
            CommitTraversalStrategy.CURLICUE_OLD)
        hashes_test = list(itertools.islice(commit_iter, 5))
        self.assertEqual(hashes, hashes_test)

    def test_iterator_skipping_unchanged_coq(self):
        """
        Test skipping consecutive commits with the same Coq source code.
        """
        repo = self.projects['GeoCoq']
        hashes = [
            GEOCOQ_COMMIT_134,
            GEOCOQ_COMMIT_135,
        ]
        commit_iter = ChangedCoqCommitIterator(
            repo,
            GEOCOQ_COMMIT_134,
            march_strategy=CommitTraversalStrategy.OLD_FIRST)
        hashes_test = list(itertools.islice(commit_iter, 5))
        # these hashes are included
        self.assertEqual(hashes, hashes_test[: 2])
        # these hashes are not
        self.assertFalse(GEOCOQ_COMMIT_136 in hashes_test)
        self.assertFalse(GEOCOQ_COMMIT_137 in hashes_test)
        self.assertFalse(GEOCOQ_COMMIT_138 in hashes_test)

    @classmethod
    def tearDownClass(cls):
        """
        Remove the cloned repos.
        """
        for project_name, repo in cls.repos.items():
            del repo
            shutil.rmtree(os.path.join(cls.repo_paths[project_name]))


class TestProjectRepo(unittest.TestCase):
    """
    Class for testing `ProjectRepo`.
    """

    @classmethod
    def setUpClass(cls):
        """
        Resolve the module path and clone CompCert repo.
        """
        cls.meta_path = _MINIMAL_METADATA
        cls.metastorage_path = _MINIMAL_METASTORAGE
        cls.test_path = os.path.dirname(__file__)
        cls.repo_path = os.path.join(cls.test_path, "CompCert")
        try:
            cls.test_repo = git.Repo.clone_from(
                "https://github.com/AbsInt/CompCert.git",
                cls.repo_path)
        except git.GitCommandError:
            cls.test_repo = git.Repo(cls.repo_path)
        # Checkout HEAD of master as of March 14, 2022
        cls.master_hash = "9d3521b4db46773239a2c5f9f6970de826075508"
        cls.test_repo.git.checkout(cls.master_hash)
        cls.meta_storage = MetadataStorage.load(cls.metastorage_path)
        cls.project = ProjectRepo(
            cls.repo_path,
            metadata_storage=cls.meta_storage,
            sentence_extraction_method=SentenceExtractionMethod.HEURISTIC)

    def test_get_file(self):
        """
        Ensure get_file method returns a file as expected.
        """
        file_object = self.project.get_file(
            os.path.join(self.repo_path,
                         "cfrontend",
                         "Ctypes.v"))
        self.assertEqual(
            file_object.abspath,
            os.path.join(self.repo_path,
                         "cfrontend",
                         "Ctypes.v"))
        self.assertGreater(len(file_object.source_code), 0)

    def test_get_random_commit(self):
        """
        Ensure a sensible commit object is returned.
        """
        commit_hash = self.project.get_random_commit()
        self.assertEqual(len(commit_hash.hexsha), 40)

    def test_get_random_file(self):
        """
        Ensure a correctly-formed random file is returned.
        """
        random_file = self.project.get_random_file(commit_name=self.master_hash)
        self.assertTrue(random_file.abspath.endswith(".v"))
        self.assertGreater(len(random_file.source_code), 0)

    def test_get_random_sentence(self):
        """
        Ensure a properly-formed random sentence is returned.
        """
        random_sentence = self.project.get_random_sentence(
            commit_name=self.master_hash)
        self.assertIsInstance(random_sentence, str)
        self.assertTrue(random_sentence.endswith('.'))

    def test_get_random_sentence_pair(self):
        """
        Ensure correctly-formed sentence pairs are returned.
        """
        random_pair = self.project.get_random_sentence_pair_adjacent(
            commit_name=self.master_hash)
        for sentence in random_pair:
            self.assertIsInstance(sentence, str)
            self.assertTrue(sentence.endswith('.'))
            self.assertGreater(len(sentence), 0)

    @classmethod
    def tearDownClass(cls):
        """
        Remove the cloned CompCert repo.
        """
        del cls.test_repo
        shutil.rmtree(os.path.join(cls.repo_path))


class TestProjectRepoLambda(unittest.TestCase):
    """
    Class for testing `ProjectRepo` using Lambda repository.
    """

    @classmethod
    def setUpClass(cls):
        """
        Resolve the module path and clone Lambda repo.
        """
        cls.meta_path = _MINIMAL_METADATA
        cls.metastorage_path = _MINIMAL_METASTORAGE
        cls.test_path = os.path.dirname(__file__)
        cls.repo_path = os.path.join(cls.test_path, "lambda")
        try:
            cls.test_repo = git.Repo.clone_from(
                "https://github.com/coq-contribs/lambda.git",
                cls.repo_path)
        except git.GitCommandError:
            cls.test_repo = git.Repo(cls.repo_path)
        # Checkout HEAD of master as of March 14, 2022
        cls.master_hash = "f531eede1b2088eff15b856558ec40f177956b96"
        cls.test_repo.git.checkout(cls.master_hash)
        cls.meta_storage = MetadataStorage.load(cls.metastorage_path)
        cls.project = ProjectRepo(
            cls.repo_path,
            metadata_storage=cls.meta_storage,
            sentence_extraction_method=SentenceExtractionMethod.HEURISTIC)
        # HACK: stick some filler metadata in the storage for `lambda`
        cls.meta_storage.insert(cls.project.metadata)
        cls.meta_storage.update(cls.project.metadata, serapi_options="")
        cls.project._metadata = cls.project._get_fresh_metadata()

    def test_get_ordered_files(self):
        """
        Ensure files are extracted in topological order.
        """
        with prism.util.radpytools.os.pushd(self.repo_path):
            ordered = self.project.get_file_list(
                relative=True,
                dependency_order=True)
            files = os.listdir("./")
            files = [
                os.path.join(self.repo_path,
                             x) for x in files if x.endswith('.v')
            ]
            graph = make_dependency_graph(
                files,
                self.project.coq_options,
                self.project.opam_switch)
            self.assertTrue(len(list(nx.simple_cycles(graph))) == 0)
            self.assertTrue(
                is_valid_topological_sort(graph,
                                          ordered,
                                          reverse=True))

    @classmethod
    def tearDownClass(cls):
        """
        Remove the cloned Lambda repo.
        """
        del cls.test_repo
        shutil.rmtree(os.path.join(cls.repo_path))


if __name__ == "__main__":
    unittest.main()
