"""
Module containing tests for the extract_cache module.
"""
import logging
import multiprocessing as mp
import os
import shutil
import unittest
from pathlib import Path

from prism.data.build_cache import (
    CoqProjectBuildCacheClient,
    CoqProjectBuildCacheProtocol,
    CoqProjectBuildCacheServer,
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
        if os.path.exists(cls.CACHE_DIR):
            shutil.rmtree(cls.CACHE_DIR)
        for project_root in cls.dir_list:
            if os.path.exists(project_root):
                shutil.rmtree(project_root)

    def test_extract_cache(self):
        """
        Test the function to extract cache from a project.
        """
        manager = mp.Manager()
        with CoqProjectBuildCacheServer() as cache_server:
            cache_client: CoqProjectBuildCacheProtocol = CoqProjectBuildCacheClient(
                cache_server,
                self.CACHE_DIR)
            # fake pre-existing cached data for float
            coq_float = self.dataset.projects['float']
            coq_float.git.checkout(self.float_head)
            coq_version = coq_float.coq_version
            dummy_float_data = ProjectCommitData(
                coq_float.metadata,
                {},
                {},
                ProjectBuildEnvironment(OpamAPI.active_switch.export()),
                ProjectBuildResult(0,
                                   "",
                                   ""))
            cache_client.write(dummy_float_data)
            coq_float.git.checkout(coq_float.reset_head)
            self.assertEqual(coq_float.commit_sha, coq_float.reset_head)
            # assert that lambda is not already cached
            self.assertFalse(
                cache_client.contains(
                    ('lambda',
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
                        self.logger.debug(
                            f"Project remote: {project.remote_url}")
                    except Exception:
                        pass
                    self.logger.debug(f"Project folder: {project.dir_abspath}")
                    continue
                project: ProjectRepo
                semaphore = manager.BoundedSemaphore(4)
                extract_cache(
                    cache_client,
                    self.swim,
                    project,
                    head,
                    lambda x: {},
                    coq_version,
                    block=True,
                    worker_semaphore=semaphore)
                self.logger.debug(f"Success {project_name}")
            # assert that the other float commit was not checked out
            self.assertEqual(coq_float.commit_sha, coq_float.reset_head)
            # assert that float was not re-cached
            self.assertEqual(
                cache_client.get('float',
                                 self.float_head,
                                 coq_version),
                dummy_float_data)
            # assert that lambda was cached
            self.assertTrue(
                cache_client.contains(
                    ('lambda',
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
            self.assertEqual(len(extracted_commands), 11)
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
                 "foo"],
                [],
                ["foo'_obligation_1",
                 "foo'_obligation_2",
                 "foo'"],
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
                [c.text for c in extracted_commands[-5].sorted_sentences()],
                expected_derived)
            expected_definition = [
                "Definition foobar : unit.",
                "Proof.",
                "exact tt.",
                "Defined.",
            ]
            self.assertEqual(
                [c.text for c in extracted_commands[-4].sorted_sentences()],
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
                [c.text for c in extracted_commands[-3].sorted_sentences()],
                expected_program)
            expected_obligation_tactic = [
                "Obligation Tactic := try (exact tt); "
                "try (simpl; match goal with |- ?a = _ => now destruct a end)."
            ]
            self.assertEqual(
                [c.text for c in extracted_commands[-2].sorted_sentences()],
                expected_obligation_tactic)
            expected_program = [
                "Program Definition foo' := let x := _ : unit in _ : x = tt."
            ]
            self.assertEqual(
                [c.text for c in extracted_commands[-1].sorted_sentences()],
                expected_program)
        with self.subTest("bullets, braces, and other subproofs"):
            with pushd(_COQ_EXAMPLES_PATH):
                sentences = Project.extract_sentences(
                    CoqDocument(
                        "fermat4_mwe.v",
                        CoqParser.parse_source("fermat4_mwe.v"),
                        _COQ_EXAMPLES_PATH),
                    glom_proofs=False,
                    return_locations=True,
                    sentence_extraction_method=SEM.HEURISTIC)
                actual_vernac_commands = _extract_vernac_commands(sentences)
                actual_vernac_commands_text = {
                    avc.command.text for avc in actual_vernac_commands
                }
                expected_vernac_commands_text = {
                    r"Require Export Wf_nat.",
                    r"Require Export ZArith.",
                    r"Require Export Znumtheory.",
                    r"Require Export Reals.",
                    r"Open Scope Z_scope.",
                    r"Definition f_Z (x : Z) := Z.abs_nat x.",
                    r"Definition R_prime (x y : Z) := 1 < x /\ 1 < y /\ x < y.",
                    r"Lemma R_prime_wf : well_founded R_prime.",
                    r"Lemma ind_prime : forall P : Z -> Prop, (forall x : Z, "
                    r"(forall y : Z, (R_prime y x -> P y)) -> P x) -> "
                    r"forall x : Z, P x.",
                    r"Lemma not_rel_prime1 : forall x y : Z, ~ rel_prime x y"
                    r" -> exists d : Z, Zis_gcd x y d /\ d <> 1 /\ d <> -1.",
                    r"Lemma Zmult_neq_0 : forall a b : Z, a * b <> 0 -> a "
                    r"<> 0 /\ b <> 0.",
                    r"Lemma not_prime_gen : forall a b : Z, 1 < a -> 1 < b ->"
                    r" b < a -> ~ prime a -> (forall c : Z, b < c < a ->"
                    r" rel_prime c a) -> exists q : Z, exists b : Z, a = "
                    r"q * b /\ 1 < q /\ 1 < b.",
                    r"Lemma prime_dec_gen : forall a b : Z, 1 < b -> b < a ->"
                    r" (forall c : Z, b < c < a -> rel_prime c a) -> "
                    r"prime a \/ ~ prime a.",
                    r"Lemma prime_dec : forall a : Z, prime a \/ ~ prime a."
                }
                self.assertEqual(
                    actual_vernac_commands_text,
                    expected_vernac_commands_text)
                expected_proof_sentence_counts = [
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    3,
                    3,
                    3,
                    3,
                    33,
                    3,
                    3
                ]
                actual_proof_sentence_counts = [
                    len(avc.proofs[0]) if avc.proofs else 0
                    for avc in actual_vernac_commands
                ]
                self.assertEqual(
                    actual_proof_sentence_counts,
                    expected_proof_sentence_counts)


if __name__ == "__main__":
    unittest.main()
