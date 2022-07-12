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
from prism.project import (
    Project,
    ProjectDir,
    ProjectRepo,
    SentenceExtractionMethod,
)
from prism.project.base import SEM
from prism.project.metadata.storage import MetadataStorage
from prism.tests import (
    _COQ_EXAMPLES_PATH,
    _MINIMAL_METADATA,
    _MINIMAL_METASTORAGE,
)


class TestProject(unittest.TestCase):
    """
    Class for testing coqgym_base module.
    """

    @classmethod
    def setUpClass(cls):
        """
        Set up class for testing coqgym_base module.
        """
        expected_filename = os.path.join(
            _COQ_EXAMPLES_PATH,
            "split_by_sentence_expected.json")
        cls.test_contents = {}
        cls.document = {}
        cls.test_list = {}
        cls.test_glom_list = {}
        coq_example_files = ["simple", "nested", "Alphabet"]
        for coq_file in coq_example_files:
            test_filename = os.path.join(_COQ_EXAMPLES_PATH, f"{coq_file}.v")
            with open(test_filename, "rt") as f:
                cls.test_contents[coq_file] = f.read()
            cls.document[coq_file] = CoqDocument(
                test_filename,
                cls.test_contents[coq_file],
                project_path=_COQ_EXAMPLES_PATH)
            with open(expected_filename, "rt") as f:
                contents = json.load(f)
                cls.test_list[coq_file] = contents[f"{coq_file}_test_list"]
                cls.test_glom_list[coq_file] = contents[
                    f"{coq_file}_test_glom_list"]

    def test_extract_sentences_heuristic(self):
        """
        Test method for splitting Coq code by sentence.
        """
        for coq_file, document in self.document.items():
            with self.subTest(coq_file):
                actual_outcome = Project.extract_sentences(
                    document,
                    glom_proofs=False,
                    sentence_extraction_method=SEM.HEURISTIC)
                self.assertEqual(actual_outcome, self.test_list[coq_file])

    def test_extract_sentences_heuristic_glom(self):
        """
        Test method for splitting Coq code by sentence.
        """
        for coq_file, document in self.document.items():
            with self.subTest(coq_file):
                actual_outcome = Project.extract_sentences(
                    document,
                    glom_proofs=True,
                    sentence_extraction_method=SEM.HEURISTIC)
                self.assertEqual(actual_outcome, self.test_glom_list[coq_file])

    def test_extract_sentences_serapi(self):
        """
        Test method for splitting Coq code using SERAPI.
        """
        test_path = os.path.dirname(__file__)
        repo_path = os.path.join(test_path, "circuits")
        if not os.path.exists(repo_path):
            test_repo = git.Repo.clone_from(
                "https://github.com/coq-contribs/circuits",
                repo_path)
        else:
            test_repo = git.Repo(repo_path)
        # Checkout HEAD of master as of March 14, 2022
        master_hash = "f2cec6067f2c58e280c5b460e113d738b387be15"
        test_repo.git.checkout(master_hash)
        old_dir = os.path.abspath(os.curdir)
        os.chdir(repo_path)
        subprocess.run("make")
        document = CoqDocument(name="ADDER/Adder.v", project_path=repo_path)
        with open(document.abspath, "rt") as f:
            document.source_code = f.read()
        sentences = Project.extract_sentences(
            document,
            sentence_extraction_method=SentenceExtractionMethod.SERAPI,
            glom_proofs=False)
        for sentence in sentences:
            self.assertTrue(
                sentence.endswith('.') or sentence == '{' or sentence == "}"
                or sentence.endswith("-") or sentence.endswith("+")
                or sentence.endswith("*"))
        # Clean up
        os.chdir(old_dir)
        del test_repo
        shutil.rmtree(os.path.join(repo_path))

    def test_extract_sentences_serapi_simple(self):
        """
        Test method for splitting Coq code using SERAPI.
        """
        for coq_file, document in self.document.items():
            with self.subTest(coq_file):
                actual_outcome = Project.extract_sentences(
                    document,
                    glom_proofs=False,
                    sentence_extraction_method=SEM.SERAPI)
                self.assertEqual(actual_outcome, self.test_list[coq_file])

    def test_extract_sentences_serapi_simple_glom(self):
        """
        Test proof glomming with serapi-based sentence extractor.
        """
        for coq_file, document in self.document.items():
            with self.subTest(coq_file):
                actual_outcome = Project.extract_sentences(
                    document,
                    glom_proofs=True,
                    sentence_extraction_method=SEM.SERAPI)
                self.assertEqual(actual_outcome, self.test_glom_list[coq_file])

    def test_extract_sentences_serapi_glom_nested(self):
        """
        Test glomming with serpai-based extractor w/ nested proofs.

        This test is disabled for now until a good caching scheme can be
        developed for a built GeoCoq. However, it does pass as of
        2022-04-19.
        """
        return
        project_name = "GeoCoq"
        master_hash = "25917f56a3b46843690457b2bfd83168bed1321c"
        target_project = "GeoCoq/GeoCoq"
        test_path = os.path.dirname(__file__)
        repo_path = os.path.join(test_path, project_name)
        if not os.path.exists(repo_path):
            test_repo = git.Repo.clone_from(
                "https://github.com/" + target_project,
                repo_path)
        else:
            test_repo = git.Repo(repo_path)
        # Checkout HEAD of master as of March 14, 2022
        test_repo.git.checkout(master_hash)
        old_dir = os.path.abspath(os.curdir)
        os.chdir(repo_path)
        subprocess.run("./configure.sh")
        subprocess.run("make")
        document = CoqDocument(
            name="Tactics/Coinc/CoincR.v",
            project_path=repo_path)
        with open(document.abspath, "rt") as f:
            document.source_code = f.read()
        actual_outcome = Project.extract_sentences(
            document,
            sentence_extraction_method=SentenceExtractionMethod.SERAPI,
            glom_proofs=True)
        for sentence in actual_outcome:
            self.assertTrue(sentence.endswith('.'))
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
        print(cls.meta_storage.get_project_revisions("CompCert", "https://github.com/AbsInt/CompCert"))
        cls.project = ProjectRepo(
            cls.repo_path,
            commit_sha=None,
            metadata_storage=cls.meta_storage,
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
            cls.meta_storage,
            sentence_extraction_method=SentenceExtractionMethod.HEURISTIC)

    def test_get_random_commit(self):
        """
        Ignore; this method is not implemented in `ProjectDir`.
        """
        pass


if __name__ == "__main__":
    unittest.main()
