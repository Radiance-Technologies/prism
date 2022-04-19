"""
Test module for prism.data.coqgym.dataset module.
"""
import os
import shutil
import unittest

import git

from prism.data.coqgym.dataset import CoqGymBaseDataset
from prism.data.project import ProjectDir, ProjectRepo, SentenceExtractionMethod


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
        cls.project_1 = ProjectRepo(
            cls.repo_path_1,
            sentence_extraction_method=SentenceExtractionMethod.HEURISTIC)
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
        cls.project_2 = ProjectRepo(
            cls.repo_path_2,
            sentence_extraction_method=SentenceExtractionMethod.HEURISTIC)
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
