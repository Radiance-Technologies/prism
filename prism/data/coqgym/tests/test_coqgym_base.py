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
from prism.data.project import ProjectBase, ProjectDir, ProjectRepo
from prism.tests import _COQ_EXAMPLES_PATH


class TestProjectBase(unittest.TestCase):
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
        actual_outcome = ProjectBase.split_by_sentence(self.document)
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
        # HEAD commits as of March 14, 2022
        cls.project_names = {"CompCert",
                             "circuits",
                             "GeoCoq"}
        cls.master_hashes = {
            "CompCert": "9d3521b4db46773239a2c5f9f6970de826075508",
            "circuits": "f2cec6067f2c58e280c5b460e113d738b387be15",
            "GeoCoq": "25917f56a3b46843690457b2bfd83168bed1321c"
        }
        cls.target_projects = {
            "CompCert": "AbsInt/CompCert",
            "circuits": "coq-contribs/circuits",
            "GeoCoq": "GeoCoq/GeoCoq"
        }
        cls.repo_paths = {}
        cls.repos = {}
        cls.projects = {}
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
            cls.projects[project_name] = ProjectRepo(project_path)
        cls.dataset = CoqGymBaseDataset(
            project_class=ProjectRepo,
            projects=cls.projects)

    def test_get_file(self):
        """
        Ensure get_file method returns a file as expected.
        """
        file_object = self.dataset.get_file(
            os.path.join(self.repo_paths["CompCert"],
                         "cfrontend",
                         "Ctypes.v"),
            'CompCert',
            self.master_hashes["CompCert"])
        self.assertEqual(
            file_object.abspath,
            os.path.join(self.repo_paths["CompCert"],
                         "cfrontend",
                         "Ctypes.v"))
        self.assertGreater(len(file_object.source_code), 0)

    def test_get_random_file(self):
        """
        Ensure a correctly-formed random file is returned.
        """
        random_file = self.dataset.get_random_file(
            project_name="circuits",
            commit_name=self.master_hashes["circuits"])
        self.assertTrue(random_file.abspath.endswith(".v"))
        self.assertGreater(len(random_file.source_code), 0)

    def test_get_random_sentence(self):
        """
        Ensure a properly-formed random sentence is returned.
        """
        random_sentence = self.dataset.get_random_sentence(
            project_name="CompCert",
            commit_name=self.master_hashes["CompCert"])
        self.assertIsInstance(random_sentence, str)
        self.assertTrue(random_sentence.endswith('.'))

    def test_get_random_sentence_pair(self):
        """
        Ensure correctly-formed sentence pairs are returned.
        """
        random_pair = self.dataset.get_random_sentence_pair_adjacent(
            project_name="CompCert",
            commit_name=self.master_hashes["CompCert"])
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
        self.assertAlmostEqual(
            self.dataset.weights["GeoCoq"],
            12236477,
            delta=100000)

    def test_init_with_project_dir_and_base_dir(self):
        """
        Test instantiation with `ProjectDir` using `base_dir` arg.
        """
        dataset = CoqGymBaseDataset(
            project_class=ProjectDir,
            base_dir=self.test_path)
        for project_name in self.project_names:
            with self.subTest(project_name):
                random_sentence = dataset.get_random_sentence(
                    project_name=project_name)
                self.assertIsInstance(random_sentence, str)
                self.assertTrue(random_sentence.endswith('.'))

    def test_init_with_project_dir_and_dir_list(self):
        """
        Test instantiation with `ProjectDir` using `base_dir` arg.
        """
        dataset = CoqGymBaseDataset(
            project_class=ProjectDir,
            dir_list=self.repo_paths.values())
        for project_name in self.project_names:
            with self.subTest(project_name):
                random_sentence = dataset.get_random_sentence(
                    project_name=project_name)
                self.assertIsInstance(random_sentence, str)
                self.assertTrue(random_sentence.endswith('.'))

    def test_init_with_project_repo_and_base_dir(self):
        """
        Test instantiation with `ProjectRepo` using `base_dir` arg.
        """
        dataset = CoqGymBaseDataset(
            project_class=ProjectRepo,
            base_dir=self.test_path)
        for project_name in self.project_names:
            with self.subTest(project_name):
                random_sentence = dataset.get_random_sentence(
                    project_name=project_name,
                    commit_name=self.master_hashes[project_name])
                self.assertIsInstance(random_sentence, str)
                self.assertTrue(random_sentence.endswith('.'))

    def test_init_with_project_repo_and_dir_list(self):
        """
        Test instantiation with `ProjectRepo` using `base_dir` arg.
        """
        dataset = CoqGymBaseDataset(
            project_class=ProjectRepo,
            dir_list=self.repo_paths.values())
        for project_name in self.project_names:
            with self.subTest(project_name):
                random_sentence = dataset.get_random_sentence(
                    project_name=project_name,
                    commit_name=self.master_hashes[project_name])
                self.assertIsInstance(random_sentence, str)
                self.assertTrue(random_sentence.endswith('.'))

    def test_coq_file_generator(self):
        """
        Ensure `CoqFileGenerator` produces sane output.
        """
        cfg = self.dataset.files()
        for file_obj in cfg:
            self.assertTrue(os.path.isfile(file_obj.abspath))
            source_code_bytes = file_obj.source_code
            self.assertIsInstance(source_code_bytes, bytes)
            source_code_str = ProjectBase._decode_byte_stream(source_code_bytes)
            self.assertIsInstance(source_code_str, str)

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
        for project_name, repo in cls.repos.items():
            del repo
            shutil.rmtree(os.path.join(cls.repo_paths[project_name]))


if __name__ == "__main__":
    unittest.main()
