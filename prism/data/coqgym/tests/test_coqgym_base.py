"""
Test module for coqgym_interface.coqgym_base.
"""
import json
import os
import shutil
import unittest

import git

from prism.data.coqgym.dataset import CoqGymBaseDataset
from prism.data.document import CoqDocument
from prism.project.base import Project
from prism.project.dir import ProjectDir
from prism.project.repo import ProjectRepo
from prism.tests import _COQ_EXAMPLES_PATH


class TestProject(unittest.TestCase):
    """
    Class for testing coqgym_base module.
    """

    def setUp(self):
        """
        Set up class for testing coqgym_base module.
        """
        test_filename = os.path.join(_COQ_EXAMPLES_PATH, "simple.v")
        expected_filename = os.path.join(
            _COQ_EXAMPLES_PATH,
            "split_by_sentence_expected.json")
        with open(test_filename, "rt") as f:
            self.test_contents = f.read()
        self.document = CoqDocument(test_filename, self.test_contents)
        with open(expected_filename, "rt") as f:
            contents = json.load(f)
            self.test_list = contents["test_list"]

    def test_split_by_sentence(self):
        """
        Test method for splitting Coq code by sentence.
        """
        actual_outcome = Project.split_by_sentence(self.document)
        self.assertEqual(actual_outcome, self.test_list)


class TestProjectRepo(unittest.TestCase):
    """
    Class for testing `ProjectRepo`.
    """

    @classmethod
    def setUpClass(cls):
        """
        Resolve the module path and clone CompCert repo.
        """
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
        cls.project = ProjectRepo(cls.repo_path)

    def test_get_file(self):
        """
        Ensure get_file method returns a file as expected.
        """
        file_object = self.project.get_file(
            os.path.join(self.repo_path,
                         "cfrontend",
                         "Ctypes.v"),
            self.master_hash)
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
        cls.project = ProjectDir(cls.repo_path)

    def test_get_random_commit(self):
        """
        Ignore; this method is not implemented in `ProjectDir`.
        """
        pass


class TestCoqGymBaseDataset(unittest.TestCase):
    """
    Tests for `CoqGymBaseDataset`.
    """

    @classmethod
    def setUpClass(cls):
        """
        Use the base constructor, with some additions.
        """
        cls.test_path = os.path.dirname(__file__)
        cls.repo_path_1 = os.path.join(cls.test_path, "CompCert")
        try:
            cls.test_repo_1 = git.Repo.clone_from(
                "https://github.com/AbsInt/CompCert.git",
                cls.repo_path_1)
        except git.GitCommandError:
            cls.test_repo_1 = git.Repo(cls.repo_path_1)
        # Checkout HEAD of master as of March 14, 2022
        cls.master_hash_1 = "9d3521b4db46773239a2c5f9f6970de826075508"
        cls.test_repo_1.git.checkout(cls.master_hash_1)
        cls.project_1 = ProjectRepo(cls.repo_path_1)
        cls.repo_path_2 = os.path.join(cls.test_path, "circuits")
        try:
            cls.test_repo_2 = git.Repo.clone_from(
                "https://github.com/coq-contribs/circuits",
                cls.repo_path_2)
        except git.GitCommandError:
            cls.test_repo_2 = git.Repo(cls.repo_path_2)
        # Checkout HEAD of master as of March 14, 2022
        cls.master_hash_2 = "f2cec6067f2c58e280c5b460e113d738b387be15"
        cls.test_repo_2.git.checkout(cls.master_hash_2)
        cls.project_1 = ProjectRepo(cls.repo_path_1)
        cls.project_2 = ProjectRepo(cls.repo_path_2)
        cls.dataset = CoqGymBaseDataset(
            project_class=ProjectRepo,
            projects={
                "CompCert": cls.project_1,
                "circuits": cls.project_2
            })

    def test_get_file(self):
        """
        Ensure get_file method returns a file as expected.
        """
        file_object = self.dataset.get_file(
            os.path.join(self.repo_path_1,
                         "cfrontend",
                         "Ctypes.v"),
            'CompCert',
            self.master_hash_1)
        self.assertEqual(
            file_object.abspath,
            os.path.join(self.repo_path_1,
                         "cfrontend",
                         "Ctypes.v"))
        self.assertGreater(len(file_object.source_code), 0)

    def test_get_random_file(self):
        """
        Ensure a correctly-formed random file is returned.
        """
        random_file = self.dataset.get_random_file(
            project_name="circuits",
            commit_name=self.master_hash_2)
        self.assertTrue(random_file.abspath.endswith(".v"))
        self.assertGreater(len(random_file.source_code), 0)

    def test_get_random_sentence(self):
        """
        Ensure a properly-formed random sentence is returned.
        """
        random_sentence = self.dataset.get_random_sentence(
            project_name="CompCert",
            commit_name=self.master_hash_1)
        self.assertIsInstance(random_sentence, str)
        self.assertTrue(random_sentence.endswith('.'))

    def test_get_random_sentence_pair(self):
        """
        Ensure correctly-formed sentence pairs are returned.
        """
        random_pair = self.dataset.get_random_sentence_pair_adjacent(
            project_name="CompCert",
            commit_name=self.master_hash_1)
        for sentence in random_pair:
            self.assertIsInstance(sentence, str)
            self.assertTrue(sentence.endswith('.'))
            self.assertGreater(len(sentence), 0)

    def test_weights(self):
        """
        Make sure the weights for the projects are correct.
        """
        self.assertAlmostEqual(
            self.dataset.weights["CompCert"],
            36115894,
            delta=100000)
        self.assertAlmostEqual(
            self.dataset.weights["circuits"],
            264238,
            delta=100000)

    def test_init_with_project_dir_and_base_dir(self):
        """
        Test instantiation with `ProjectDir` using `base_dir` arg.
        """
        dataset = CoqGymBaseDataset(
            project_class=ProjectDir,
            base_dir=self.test_path)
        random_sentence = dataset.get_random_sentence(project_name="CompCert")
        self.assertIsInstance(random_sentence, str)
        self.assertTrue(random_sentence.endswith('.'))
        random_sentence = dataset.get_random_sentence(project_name="circuits")
        self.assertIsInstance(random_sentence, str)
        self.assertTrue(random_sentence.endswith('.'))

    def test_init_with_project_dir_and_dir_list(self):
        """
        Test instantiation with `ProjectDir` using `base_dir` arg.
        """
        dataset = CoqGymBaseDataset(
            project_class=ProjectDir,
            dir_list=[self.repo_path_1,
                      self.repo_path_2])
        random_sentence = dataset.get_random_sentence(project_name="CompCert")
        self.assertIsInstance(random_sentence, str)
        self.assertTrue(random_sentence.endswith('.'))
        random_sentence = dataset.get_random_sentence(project_name="circuits")
        self.assertIsInstance(random_sentence, str)
        self.assertTrue(random_sentence.endswith('.'))

    def test_init_with_project_repo_and_base_dir(self):
        """
        Test instantiation with `ProjectRepo` using `base_dir` arg.
        """
        dataset = CoqGymBaseDataset(
            project_class=ProjectRepo,
            base_dir=self.test_path)
        random_sentence = dataset.get_random_sentence(
            project_name="CompCert",
            commit_name=self.master_hash_1)
        self.assertIsInstance(random_sentence, str)
        self.assertTrue(random_sentence.endswith('.'))
        random_sentence = dataset.get_random_sentence(
            project_name="circuits",
            commit_name=self.master_hash_2)
        self.assertIsInstance(random_sentence, str)
        self.assertTrue(random_sentence.endswith('.'))

    def test_init_with_project_repo_and_dir_list(self):
        """
        Test instantiation with `ProjectRepo` using `base_dir` arg.
        """
        dataset = CoqGymBaseDataset(
            project_class=ProjectRepo,
            dir_list=[self.repo_path_1,
                      self.repo_path_2])
        random_sentence = dataset.get_random_sentence(
            project_name="CompCert",
            commit_name=self.master_hash_1)
        self.assertIsInstance(random_sentence, str)
        self.assertTrue(random_sentence.endswith('.'))
        random_sentence = dataset.get_random_sentence(
            project_name="circuits",
            commit_name=self.master_hash_2)
        self.assertIsInstance(random_sentence, str)
        self.assertTrue(random_sentence.endswith('.'))

    def test_coq_file_generator(self):
        """
        Ensure `CoqFileGenerator` produces sane output.
        """
        cfg = self.dataset.files()
        for file_obj in cfg:
            self.assertTrue(os.path.isfile(file_obj.abspath))
            self.assertIsInstance(file_obj.source_code, str)

    def test_coq_sentence_generator(self):
        """
        Ensure `CoqSentenceGenerator` produces sane output.
        """
        csg = self.dataset.sentences()
        for sentence in csg:
            self.assertGreater(len(sentence), 0)
            self.assertTrue(sentence.endswith('.'))

    @classmethod
    def tearDownClass(cls):
        """
        Remove the cloned repos.
        """
        del cls.test_repo_1
        shutil.rmtree(os.path.join(cls.repo_path_1))
        del cls.test_repo_2
        shutil.rmtree(os.path.join(cls.repo_path_2))


if __name__ == "__main__":
    unittest.main()
