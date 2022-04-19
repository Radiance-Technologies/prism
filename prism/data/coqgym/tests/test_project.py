"""
Test module for prism.data.project module.
"""
import json
import os
import shutil
import subprocess
import unittest

import git

from prism.data.document import CoqDocument
from prism.data.project import (
    ProjectBase,
    ProjectDir,
    ProjectRepo,
    SentenceExtractionMethod,
)
from prism.tests import _COQ_EXAMPLES_PATH


class TestProjectBase(unittest.TestCase):
    """
    Class for testing coqgym_base module.
    """

    def test_extract_sentences_heuristic(self):
        """
        Test method for splitting Coq code by sentence.
        """
        test_filename = os.path.join(_COQ_EXAMPLES_PATH, "simple.v")
        expected_filename = os.path.join(
            _COQ_EXAMPLES_PATH,
            "split_by_sentence_expected.json")
        with open(test_filename, "rt") as f:
            self.test_contents = f.read()
        document = CoqDocument(test_filename, self.test_contents)
        with open(expected_filename, "rt") as f:
            contents = json.load(f)
            self.test_list = contents["test_list"]
        actual_outcome = ProjectBase.extract_sentences(
            document,
            sentence_extraction_method=SentenceExtractionMethod.HEURISTIC)
        self.assertEqual(actual_outcome, self.test_list)

    def test_extract_sentences_serapi(self):
        """
        Test method for splitting Coq code using SERAPI.
        """
        test_path = os.path.dirname(__file__)
        repo_path = os.path.join(test_path, "circuits")
        test_repo = git.Repo.clone_from(
            "https://github.com/coq-contribs/circuits",
            repo_path)
        # Checkout HEAD of master as of March 14, 2022
        master_hash = "f2cec6067f2c58e280c5b460e113d738b387be15"
        test_repo.git.checkout(master_hash)
        old_dir = os.path.abspath(os.curdir)
        os.chdir(repo_path)
        subprocess.run("make")
        document = CoqDocument(name="ADDER/Adder.v", project_path=repo_path)
        with open(document.abspath, "rt") as f:
            document.source_code = f.read()
        sentences = ProjectBase.extract_sentences(
            document,
            sentence_extraction_method=SentenceExtractionMethod.SERAPI)
        for sentence in sentences:
            self.assertTrue(
                sentence.endswith('.') or sentence == '{' or sentence == "}"
                or sentence.endswith("-") or sentence.endswith("+")
                or sentence.endswith("*"))
        # Clean up
        os.chdir(old_dir)
        del test_repo
        shutil.rmtree(os.path.join(repo_path))


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
        cls.project = ProjectRepo(
            cls.repo_path,
            sentence_extraction_method=SentenceExtractionMethod.HEURISTIC)

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
        cls.project = ProjectDir(
            cls.repo_path,
            sentence_extraction_method=SentenceExtractionMethod.HEURISTIC)

    def test_get_random_commit(self):
        """
        Ignore; this method is not implemented in `ProjectDir`.
        """
        pass


if __name__ == "__main__":
    unittest.main()
