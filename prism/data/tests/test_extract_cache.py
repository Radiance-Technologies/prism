"""
Module containing tests for the extract_cache module.
"""
import logging
import os
import shutil
import unittest
from pathlib import Path

from prism.data.build_cache import (
    CoqProjectBuildCache,
    ProjectBuildEnvironment,
    ProjectBuildResult,
    ProjectCommitData,
)
from prism.data.dataset import CoqProjectBaseDataset
from prism.data.document import CoqDocument
from prism.data.extract_cache import _extract_vernac_commands, extract_cache
from prism.language.gallina.parser import CoqParser
from prism.project.base import SEM, Project
from prism.project.metadata.storage import MetadataStorage
from prism.project.repo import ProjectRepo
from prism.tests import _COQ_EXAMPLES_PATH, _PROJECT_EXAMPLES_PATH
from prism.util.opam import OpamAPI
from prism.util.radpytools.os import pushd
from prism.util.swim import SwitchManager


class TestExtractCache(unittest.TestCase):
    """
    Tests for extract_cache module.
    """

    TEST_DIR = Path(__file__).parent
    CACHE_DIR = TEST_DIR / "project_build_cache"

    @classmethod
    def setUpClass(cls):
        """
        Set up an on-disk cache to share among all unit tests.
        """
        cls.cache = CoqProjectBuildCache(cls.CACHE_DIR)
        cls.swim = SwitchManager([OpamAPI.active_switch])
        cls.storage = MetadataStorage.load(
            _PROJECT_EXAMPLES_PATH / "project_metadata.yml")
        cls.dir_list = [
            _PROJECT_EXAMPLES_PATH / p for p in cls.storage.projects
        ]
        cls.dataset = CoqProjectBaseDataset(
            project_class=ProjectRepo,
            dir_list=cls.dir_list,
            metadata_storage=cls.storage,
            sentence_extraction_method=SEM.HEURISTIC)
        if not os.path.exists("./test_logs"):
            os.makedirs("./test_logs")
        cls.logger = logging.Logger(
            "test_extract_cache_logger",
            level=logging.DEBUG)
        cls.logger.addHandler(
            logging.FileHandler(
                "./test_logs/test_extract_cache_log.txt",
                mode="w"))
        cls.float_head = "a4b445bad8b8d0afb725d64472b194d234676ce0"
        cls.lambda_head = "f531eede1b2088eff15b856558ec40f177956b96"
        # go ahead and build lambda since it is shared between tests
        coq_lambda = cls.dataset.projects['lambda']
        coq_lambda.git.checkout(cls.lambda_head)
        return
        coq_lambda.build()

    @classmethod
    def tearDownClass(cls):
        """
        Remove on-disk cache and project directories.
        """
        shutil.rmtree(cls.CACHE_DIR)
        for project_root in cls.dir_list:
            shutil.rmtree(project_root)

    def test_extract_cache(self):
        """
        Test the function to extract cache from a project.
        """
        # fake pre-existing cached data for float
        coq_float = self.dataset.projects['float']
        coq_float.git.checkout(self.float_head)
        coq_version = coq_float.coq_version
        dummy_float_data = ProjectCommitData(
            coq_float.metadata,
            {},
            ProjectBuildEnvironment(OpamAPI.active_switch.export()),
            ProjectBuildResult(0,
                               "",
                               ""))
        self.cache.insert(dummy_float_data)
        coq_float.git.checkout(coq_float.reset_head)
        self.assertEqual(coq_float.commit_sha, coq_float.reset_head)
        # assert that lambda is not already cached
        self.assertFalse(
            self.cache.contains(('lambda',
                                 self.lambda_head,
                                 coq_version)))
        # only cache new lambda data
        for project_name, project in self.dataset.projects.items():
            if "float" in project_name.lower():
                head = self.float_head
            elif "lambda" in project_name.lower():
                head = self.lambda_head
            else:
                self.logger.debug(f"Project name: {project_name}")
                try:
                    self.logger.debug(f"Project remote: {project.remote_url}")
                except Exception:
                    pass
                self.logger.debug(f"Project folder: {project.dir_abspath}")
                continue
            project: ProjectRepo
            extract_cache(
                self.cache,
                self.swim,
                project,
                head,
                lambda x: {},
                coq_version)
            self.logger.debug(f"Success {project_name}")
        # assert that the other float commit was not checked out
        self.assertEqual(coq_float.commit_sha, coq_float.reset_head)
        # assert that float was not re-cached
        self.assertEqual(
            self.cache.get('float',
                           self.float_head,
                           coq_version),
            dummy_float_data)
        # assert that lambda was cached
        self.assertTrue(
            self.cache.contains(('lambda',
                                 self.lambda_head,
                                 coq_version)))

    def test_extract_vernac_commands(self):
        """
        Test the function to extract vernac commands from a project.
        """
        with pushd(_COQ_EXAMPLES_PATH):
            extracted_commands = _extract_vernac_commands(
                Project.extract_sentences(
                    CoqDocument(
                        "Alphabet.v",
                        CoqParser.parse_source("Alphabet.v"),
                        _COQ_EXAMPLES_PATH),
                    sentence_extraction_method=SEM.HEURISTIC,
                    return_locations=True,
                    glom_proofs=False),
                serapi_options="")
        self.assertEqual(len(extracted_commands), 37)
        self.assertEqual(len([c for c in extracted_commands if c.proofs]), 9)
        with self.subTest("delayed_proof"):
            with pushd(_COQ_EXAMPLES_PATH):
                extracted_commands = _extract_vernac_commands(
                    Project.extract_sentences(
                        CoqDocument(
                            "delayed_proof.v",
                            CoqParser.parse_source("delayed_proof.v"),
                            _COQ_EXAMPLES_PATH),
                        sentence_extraction_method=SEM.HEURISTIC,
                        return_locations=True,
                        glom_proofs=False),
                    serapi_options="")
            self.assertEqual(len(extracted_commands), 9)
            expected_ids = [
                [],
                [],
                [],
                [],
                ['P'],
                ['n',
                 'm',
                 'k'],
                ["p",
                 "h"],
                ["foobar"],
                ["foo_obligation_1",
                 "foo_obligation_2",
                 "foo"]
            ]
            self.assertEqual(
                [c.identifier for c in extracted_commands],
                expected_ids)
            expected_derived = [
                "Derive p SuchThat ((k*n)+(k*m) = p) As h.",
                "rewrite <- Nat.mul_add_distr_l.",
                "subst p.",
                "reflexivity.",
                "Qed.",
            ]
            self.assertEqual(
                [c.text for c in extracted_commands[-3].sorted_sentences()],
                expected_derived)
            expected_definition = [
                "Definition foobar : unit.",
                "Proof.",
                "exact tt.",
                "Defined.",
            ]
            self.assertEqual(
                [c.text for c in extracted_commands[-2].sorted_sentences()],
                expected_definition)
            expected_program = [
                "Program Definition foo := let x := _ : unit in _ : x = tt.",
                "Next Obligation.",
                "Next Obligation.",
                "exact tt.",
                "Qed.",
                "Next Obligation.",
                "simpl; match goal with |- ?a = _ => now destruct a end.",
                "Qed.",
                "Abort.",
            ]
            self.assertEqual(
                [c.text for c in extracted_commands[-1].sorted_sentences()],
                expected_program)


if __name__ == "__main__":
    unittest.main()
