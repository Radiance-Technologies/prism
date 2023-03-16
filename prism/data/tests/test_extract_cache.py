"""
Module containing tests for the extract_cache module.
"""
import logging
import multiprocessing as mp
import os
import shutil
import typing
import unittest
from copy import deepcopy
from pathlib import Path
from typing import List

import pytest

from prism.data.build_cache import (
    CoqProjectBuildCacheClient,
    CoqProjectBuildCacheProtocol,
    CoqProjectBuildCacheServer,
    GoalIdentifiers,
    HypothesisIndentifiers,
    ProjectBuildEnvironment,
    ProjectBuildResult,
    ProjectCommitData,
    VernacCommandDataList,
    VernacSentence,
)
from prism.data.dataset import CoqProjectBaseDataset
from prism.data.document import CoqDocument
from prism.data.extract_cache import CommandExtractor, extract_cache
from prism.interface.coq.goals import Goals, GoalsDiff
from prism.interface.coq.ident import Identifier, IdentType
from prism.language.gallina.parser import CoqParser
from prism.language.heuristic.parser import CoqSentence
from prism.project.base import SEM, Project
from prism.project.metadata.storage import MetadataStorage
from prism.project.repo import ProjectRepo
from prism.tests import _COQ_EXAMPLES_PATH, _PROJECT_EXAMPLES_PATH
from prism.util.opam import OpamSwitch, OpamVersion
from prism.util.radpytools.os import pushd
from prism.util.swim import SwitchManager


class TestExtractCache(unittest.TestCase):
    """
    Tests for extract_cache module.
    """

    TEST_DIR = Path(__file__).parent
    CACHE_DIR = TEST_DIR / "project_build_cache"
    dir_list: List[Path]
    test_switch: OpamSwitch = OpamSwitch()
    serapi_version: str
    update_8_14: bool
    """
    Flag to update tests to Coq 8.14.
    """

    @classmethod
    def setUpClass(cls):
        """
        Set up persistent switch-related variables.
        """
        cls.serapi_version = cls.test_switch.get_installed_version("coq-serapi")
        assert cls.serapi_version is not None
        cls.update_8_14 = OpamVersion.less_than("8.13.2", cls.serapi_version)

    @classmethod
    def setUpCache(cls):
        """
        Set up an on-disk cache to share among all unit tests.
        """
        cls.swim = SwitchManager([cls.test_switch])
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
        # go ahead and checkout lambda
        coq_lambda = cls.dataset.projects['lambda']
        coq_lambda.git.checkout(cls.lambda_head)

    @classmethod
    def tearDownCache(cls):
        """
        Remove on-disk cache and project directories.
        """
        if os.path.exists(cls.CACHE_DIR):
            shutil.rmtree(cls.CACHE_DIR)
        for project_root in cls.dir_list:
            if os.path.exists(project_root):
                shutil.rmtree(project_root)

    def _extract_cache(self, build_error_expected: bool = False, **kwargs):
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
                None,
                None,
                {},
                ProjectBuildEnvironment(self.test_switch.export()),
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
                    lambda x: ({},
                               {}),
                    coq_version,
                    block=True,
                    worker_semaphore=semaphore,
                    **kwargs)
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
            if build_error_expected:
                self.assertEqual(
                    cache_client.get_status(
                        'lambda',
                        self.lambda_head,
                        coq_version),
                    "build error")
        return cache_client, cache_server

    @pytest.mark.coq_8_10_2
    def test_extract_cache_limited_runtime(self):
        """
        Test the function to extract cache from a project.
        """
        try:
            self.setUpCache()
            self._extract_cache(max_runtime=0, build_error_expected=True)
        finally:
            self.tearDownCache()

    @pytest.mark.coq_8_10_2
    def test_extract_cache_limited_memory(self):
        """
        Test the function to extract cache from a project.
        """
        try:
            self.setUpCache()
            self._extract_cache(max_memory=20000, build_error_expected=True)
        finally:
            self.tearDownCache()

    @pytest.mark.coq_8_10_2
    def test_extract_cache(self):
        """
        Test the function to extract cache from a project.
        """
        try:
            self.setUpCache()
            self._extract_cache(build_error_expected=False)
        finally:
            self.tearDownCache()

    @pytest.mark.coq_all
    def test_extract_vernac_commands(self):
        """
        Test the function to extract vernac commands from a project.
        """
        with pushd(_COQ_EXAMPLES_PATH):
            extracted_commands = CommandExtractor(
                "Alphabet.v",
                typing.cast(
                    List[CoqSentence],
                    Project.extract_sentences(
                        CoqDocument(
                            "Alphabet.v",
                            CoqParser.parse_source("Alphabet.v"),
                            _COQ_EXAMPLES_PATH),
                        sentence_extraction_method=SEM.HEURISTIC,
                        return_locations=True,
                        glom_proofs=False)),
                serapi_options="",
                opam_switch=self.test_switch).extracted_commands
        self.assertEqual(len(extracted_commands), 37)
        self.assertEqual(len([c for c in extracted_commands if c.proofs]), 9)
        with self.subTest("delayed_proof"):
            with pushd(_COQ_EXAMPLES_PATH):
                extracted_commands = CommandExtractor(
                    "delayed_proof.v",
                    typing.cast(
                        List[CoqSentence],
                        Project.extract_sentences(
                            CoqDocument(
                                "delayed_proof.v",
                                CoqParser.parse_source("delayed_proof.v"),
                                _COQ_EXAMPLES_PATH),
                            sentence_extraction_method=SEM.HEURISTIC,
                            return_locations=True,
                            glom_proofs=False)),
                    serapi_options="",
                    opam_switch=self.test_switch).extracted_commands
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
                "Fail Qed.",
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
                actual_vernac_commands = CommandExtractor(
                    'fermat4_mwe.v',
                    sentences,
                    serapi_options="",
                    opam_switch=self.test_switch).extracted_commands
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
        with self.subTest("extract_idents"):
            with pushd(_COQ_EXAMPLES_PATH):
                extracted_commands = CommandExtractor(
                    "shadowing.v",
                    typing.cast(
                        List[CoqSentence],
                        Project.extract_sentences(
                            CoqDocument(
                                "shadowing.v",
                                CoqParser.parse_source("shadowing.v"),
                                _COQ_EXAMPLES_PATH),
                            sentence_extraction_method=SEM.HEURISTIC,
                            return_locations=True,
                            glom_proofs=False)),
                    serapi_options="",
                    opam_switch=self.test_switch).extracted_commands
            self.assertEqual(len(extracted_commands), 4)
            expected_ids = [
                ["nat"],
                ["nat"],
                ["plus_0_n"],
                [],
            ]
            self.assertEqual(
                [c.identifier for c in extracted_commands],
                expected_ids)
            expected_qualids = [
                [
                    Identifier(IdentType.lident,
                               "Shadowing.nat"),
                    Identifier(IdentType.lident,
                               "Shadowing.n'"),
                    Identifier(IdentType.lname,
                               "Shadowing.n'"),
                    Identifier(IdentType.lname,
                               "Shadowing.m"),
                    Identifier(
                        IdentType.CRef,
                        # limitation of regex-based name resolution
                        "Shadowing.nat"),
                    #    "Coq.Init.Datatypes.nat"),
                    Identifier(
                        IdentType.CRef,
                        # limitation of regex-based name resolution
                        "Shadowing.nat"),
                    #    "Coq.Init.Datatypes.nat"),
                    Identifier(IdentType.CRef,
                               "Shadowing.n'"),
                    Identifier(IdentType.CPatAtom,
                               "Coq.Init.Datatypes.O"),
                    Identifier(IdentType.CRef,
                               "Shadowing.m"),
                    Identifier(IdentType.Ser_Qualid,
                               "Coq.Init.Datatypes.S"),
                    Identifier(IdentType.CPatAtom,
                               "Shadowing.p"),
                    Identifier(IdentType.CRef,
                               "Coq.Init.Datatypes.S"),
                    Identifier(IdentType.CRef,
                               "Shadowing.nat"),
                    Identifier(IdentType.CRef,
                               "Shadowing.p"),
                    Identifier(IdentType.CRef,
                               "Shadowing.m"),
                ],
                [
                    Identifier(IdentType.lident,
                               "Shadowing.nat"),
                ],
                [
                    Identifier(IdentType.lident,
                               "Shadowing.plus_0_n"),
                    Identifier(IdentType.lname,
                               "Shadowing.n"),
                    Identifier(IdentType.CRef,
                               "Coq.Init.Datatypes.nat"),
                    Identifier(IdentType.CRef,
                               "Shadowing.nat"),
                    Identifier(IdentType.CRef,
                               "Shadowing.n"),
                    Identifier(IdentType.CRef,
                               "Shadowing.n"),
                ],
                [
                    Identifier(IdentType.lident,
                               "Shadowing.nat"),
                ],
            ]
            self.assertEqual(
                [c.command.qualified_identifiers for c in extracted_commands],
                expected_qualids)
            expected_O_qualids = (
                [] if self.update_8_14 else
                [Identifier(IdentType.CRef,
                            "Coq.Init.Datatypes.O")])
            expected_eq_qualids = [
                Identifier(IdentType.Ser_Qualid,
                           "Coq.Init.Logic.eq"),
                Identifier(IdentType.CRef,
                           "Coq.Init.Datatypes.nat"),
            ]
            expected_qualids = [
                GoalIdentifiers(
                    [
                        Identifier(IdentType.lname,
                                   "Shadowing.n"),
                        Identifier(IdentType.CRef,
                                   "Coq.Init.Datatypes.nat"),
                    ] + expected_eq_qualids + [
                        Identifier(IdentType.CRef,
                                   "Shadowing.nat"),
                    ] + expected_O_qualids + [
                        Identifier(IdentType.CRef,
                                   "Shadowing.n"),
                        Identifier(IdentType.CRef,
                                   "Shadowing.n"),
                    ],
                    []),
                GoalIdentifiers([],
                                []),
                GoalIdentifiers(
                    expected_eq_qualids + [
                        Identifier(IdentType.CRef,
                                   "Shadowing.nat"),
                    ] + expected_O_qualids + [
                        Identifier(IdentType.CRef,
                                   "m"),
                        Identifier(IdentType.CRef,
                                   "m"),
                    ],
                    [
                        HypothesisIndentifiers(
                            None,
                            [
                                Identifier(
                                    IdentType.CRef,
                                    "Coq.Init.Datatypes.nat")
                            ])
                    ]),
                GoalIdentifiers(
                    expected_eq_qualids + [
                        Identifier(IdentType.CRef,
                                   "m"),
                        Identifier(IdentType.CRef,
                                   "m"),
                    ],
                    [
                        HypothesisIndentifiers(
                            None,
                            [
                                Identifier(
                                    IdentType.CRef,
                                    "Coq.Init.Datatypes.nat")
                            ])
                    ]),
                GoalIdentifiers([],
                                [])
            ]
            actual_goal_qualids = [
                list(tac.goals_qualified_identifiers.values())
                for tac in extracted_commands[2].proofs[0]
            ]
            [self.assertLessEqual(len(gqi), 1) for gqi in actual_goal_qualids]
            actual_goal_qualids = [
                gqi[0] if gqi else GoalIdentifiers([],
                                                   [])
                for gqi in actual_goal_qualids
            ]
            self.assertEqual(actual_goal_qualids, expected_qualids)

    @pytest.mark.coq_all
    def test_extract_aborted_proofs(self):
        """
        Verify that aborted proofs can be extracted.
        """
        with pushd(_COQ_EXAMPLES_PATH):
            extracted_commands = CommandExtractor(
                "aborted.v",
                typing.cast(
                    List[CoqSentence],
                    Project.extract_sentences(
                        CoqDocument(
                            "aborted.v",
                            CoqParser.parse_source("aborted.v"),
                            _COQ_EXAMPLES_PATH),
                        sentence_extraction_method=SEM.HEURISTIC,
                        return_locations=True,
                        glom_proofs=False)),
                serapi_options="",
                opam_switch=self.test_switch).extracted_commands
        expected_commands_text = [
            "Definition idw (A : Type) := A.",
            "Lemma foobar : unit.",
            "Set Nested Proofs Allowed.",
            "Lemma aux : forall A : Type, A -> unit.",
            "Lemma aux' : forall A : Type, A -> unit.",
            "Lemma foobar' : unit.",
            "Program Definition foo := let x := _ : unit in _ : x = tt.",
        ]
        actual_commands_text = [c.command.text for c in extracted_commands]
        self.assertEqual(expected_commands_text, actual_commands_text)

    @pytest.mark.coq_all
    def test_saved_proofs(self):
        """
        Verify that proofs concluded with Save have the correct ids.
        """
        with pushd(_COQ_EXAMPLES_PATH):
            extracted_commands = CommandExtractor(
                "save.v",
                typing.cast(
                    List[CoqSentence],
                    Project.extract_sentences(
                        CoqDocument(
                            "save.v",
                            CoqParser.parse_source("save.v"),
                            _COQ_EXAMPLES_PATH),
                        sentence_extraction_method=SEM.HEURISTIC,
                        return_locations=True,
                        glom_proofs=False)),
                serapi_options="",
                opam_switch=self.test_switch).extracted_commands
            self.assertTrue(
                any("foobaz" in ec.identifier for ec in extracted_commands))
            self.assertTrue(
                any("foobat" in ec.identifier for ec in extracted_commands))

    @pytest.mark.coq_8_15_2
    @pytest.mark.coq_8_14_1
    @pytest.mark.coq_8_13_2
    @pytest.mark.coq_8_12_2
    def test_saved_proofs_named(self):
        """
        Verify that named proofs concluded with Save have correct ids.

        This test is expected to work only with Coq 8.12 and later.
        """
        with pushd(_COQ_EXAMPLES_PATH):
            extracted_commands = CommandExtractor(
                "save_named_theorem.v",
                typing.cast(
                    List[CoqSentence],
                    Project.extract_sentences(
                        CoqDocument(
                            "save_named_theorem.v",
                            CoqParser.parse_source("save_named_theorem.v"),
                            _COQ_EXAMPLES_PATH),
                        sentence_extraction_method=SEM.HEURISTIC,
                        return_locations=True,
                        glom_proofs=False)),
                serapi_options="",
                opam_switch=self.test_switch).extracted_commands
            self.assertTrue(
                any("foobaz" in ec.identifier for ec in extracted_commands))
            self.assertTrue(
                any("foobat" in ec.identifier for ec in extracted_commands))

    @pytest.mark.coq_all
    def test_extract_solve_all_obligations(self):
        """
        Verify that programs are extracted when defined by side-effect.

        An example command that causes this is `Solve All Obligations`.
        """
        with pushd(_COQ_EXAMPLES_PATH):
            extracted_commands = CommandExtractor(
                "solve_all_obligations.v",
                Project.extract_sentences(
                    CoqDocument(
                        "solve_all_obligations.v",
                        CoqParser.parse_source("solve_all_obligations.v"),
                        _COQ_EXAMPLES_PATH),
                    sentence_extraction_method=SEM.HEURISTIC,
                    return_locations=True,
                    glom_proofs=False),
                serapi_options="",
                opam_switch=self.test_switch).extracted_commands
            self.assertEqual(len(extracted_commands), 2)
            self.assertEqual(
                set(['foo_obligation_1',
                     'foo_obligation_2',
                     'foo']),
                set(extracted_commands[1].identifier))
            self.assertEqual(
                extracted_commands[1].all_text(),
                '\n'.join(
                    [
                        "Program Definition foo := let x := _ : unit in _ : x = tt.",
                        "Solve All Obligations with try exact tt; simpl; "
                        "match goal with |- ?a = _ => now destruct a end."
                    ]))

    @pytest.mark.coq_all
    def test_goals_reconstruction(self):
        """
        Test the reconstruction of Goals from GoalsDiff.
        """

        def _sort(cmd_list: VernacCommandDataList) -> List[VernacSentence]:
            """
            Sort all commands' sentences by locations.
            """
            out: List[VernacSentence] = []
            for i, cmd in enumerate(cmd_list):
                out.extend(cmd.sorted_sentences(True, i))
            out = VernacSentence.sort_sentences(out)
            return out

        def _reconstruct_goals(
                sentences: List[VernacSentence]) -> List[VernacSentence]:
            """
            Apply diffs to goals in a copy of the given `sentences`.
            """
            sentences = deepcopy(sentences)
            previous_goals = Goals()
            for sentence in sentences:
                if isinstance(sentence.goals, Goals):
                    previous_goals = sentence.goals
                elif isinstance(sentence.goals, GoalsDiff):
                    patched_goals = sentence.goals.patch(previous_goals)
                    sentence.goals = patched_goals
                    previous_goals = sentence.goals
                else:
                    previous_goals = Goals()
            for sentence in sentences:
                if sentence.goals is not None:
                    self.assertIsInstance(sentence.goals, Goals)
            return sentences

        with pushd(_COQ_EXAMPLES_PATH):
            extracted_commands_no_diffs = CommandExtractor(
                "fermat4_mwe.v",
                typing.cast(
                    List[CoqSentence],
                    Project.extract_sentences(
                        CoqDocument(
                            "fermat4_mwe.v",
                            CoqParser.parse_source("fermat4_mwe.v"),
                            _COQ_EXAMPLES_PATH),
                        sentence_extraction_method=SEM.HEURISTIC,
                        return_locations=True,
                        glom_proofs=False)),
                serapi_options="",
                use_goals_diff=False,
                opam_switch=self.test_switch).extracted_commands
            extracted_commands_with_diffs = CommandExtractor(
                "fermat4_mwe.v",
                typing.cast(
                    List[CoqSentence],
                    Project.extract_sentences(
                        CoqDocument(
                            "fermat4_mwe.v",
                            CoqParser.parse_source("fermat4_mwe.v"),
                            _COQ_EXAMPLES_PATH),
                        sentence_extraction_method=SEM.HEURISTIC,
                        return_locations=True,
                        glom_proofs=False)),
                serapi_options="",
                use_goals_diff=True,
                opam_switch=self.test_switch).extracted_commands
            sentences_no_diffs = _sort(extracted_commands_no_diffs)
            sentences_with_diffs = _sort(extracted_commands_with_diffs)
            sentences_reconstructed = _reconstruct_goals(sentences_with_diffs)
            expected_goals_list = [s.goals for s in sentences_no_diffs]
            reconstructed_goals_list = [
                s.goals for s in sentences_reconstructed
            ]
            self.assertEqual(expected_goals_list, reconstructed_goals_list)


if __name__ == "__main__":
    unittest.main()
