"""
Module containing tests for the extract_cache module.
"""

import typing
import unittest
from copy import deepcopy
from itertools import chain
from typing import List

import pytest

from prism.data.cache.command_extractor import CommandExtractor
from prism.data.cache.types.command import (
    GoalIdentifiers,
    HypothesisIndentifiers,
    VernacCommandDataList,
    VernacSentence,
)
from prism.data.document import CoqDocument
from prism.interface.coq.goals import Goals, GoalsDiff
from prism.interface.coq.ident import Identifier, IdentType
from prism.interface.coq.options import SerAPIOptions
from prism.language.gallina.analyze import SexpInfo
from prism.language.gallina.parser import CoqParser
from prism.language.heuristic.parser import CoqSentence
from prism.project.base import SEM, Project
from prism.tests import _COQ_EXAMPLES_PATH
from prism.util.opam import OpamSwitch, OpamVersion
from prism.util.radpytools.os import pushd


class TestCommandExtractor(unittest.TestCase):
    """
    Tests for extract_cache module.
    """

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
                serapi_options=SerAPIOptions.empty(),
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
                    serapi_options=SerAPIOptions.empty(),
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
                sentences = typing.cast(
                    List[CoqSentence],
                    Project.extract_sentences(
                        CoqDocument(
                            "fermat4_mwe.v",
                            CoqParser.parse_source("fermat4_mwe.v"),
                            _COQ_EXAMPLES_PATH),
                        glom_proofs=False,
                        return_locations=True,
                        sentence_extraction_method=SEM.HEURISTIC))
                actual_vernac_commands = CommandExtractor(
                    'fermat4_mwe.v',
                    sentences,
                    serapi_options=SerAPIOptions.empty(),
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
                    serapi_options=SerAPIOptions.empty(),
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
                serapi_options=SerAPIOptions.empty(),
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
                serapi_options=SerAPIOptions.empty(),
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
                serapi_options=SerAPIOptions.empty(),
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
                typing.cast(
                    List[CoqSentence],
                    Project.extract_sentences(
                        CoqDocument(
                            "solve_all_obligations.v",
                            CoqParser.parse_source("solve_all_obligations.v"),
                            _COQ_EXAMPLES_PATH),
                        sentence_extraction_method=SEM.HEURISTIC,
                        return_locations=True,
                        glom_proofs=False)),
                serapi_options=SerAPIOptions.empty(),
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
    def test_extract_set_program_mode(self):
        """
        Verify that commands are extracted when ``Program Mode`` is on.
        """
        with pushd(_COQ_EXAMPLES_PATH):
            extracted_commands = CommandExtractor(
                "program_mode.v",
                typing.cast(
                    List[CoqSentence],
                    Project.extract_sentences(
                        CoqDocument(
                            "program_mode.v",
                            CoqParser.parse_source("program_mode.v"),
                            _COQ_EXAMPLES_PATH),
                        sentence_extraction_method=SEM.HEURISTIC,
                        return_locations=True,
                        glom_proofs=False)),
                serapi_options=SerAPIOptions.empty(),
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
            ["add"],
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
            "Fixpoint add (n' m:nat) {struct n'} : nat := "
            "match n' with "
            "| O => m "
            "| S p => S (add p m) "
            "end."
        ]
        self.assertEqual(
            [c.text for c in extracted_commands[-4].sorted_sentences()],
            expected_definition)
        expected_program = [
            "Definition foo := let x := _ : unit in _ : x = tt.",
            "Next Obligation.",
            "exact tt.",
            "Qed.",
            "Next Obligation.",
            "simpl; match goal with |- ?a = _ => now destruct a end.",
            "Qed.",
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
            "Definition foo' := let x := _ : unit in _ : x = tt."
        ]
        self.assertEqual(
            [c.text for c in extracted_commands[-1].sorted_sentences()],
            expected_program)

    @pytest.mark.coq_all
    def test_bug_396(self):
        """
        Verify that certain character-escaped goals can be extracted.

        Otherwise, one obtains a lexer error because a value was escaped
        twice.
        """
        with pushd(_COQ_EXAMPLES_PATH):
            extracted_commands = CommandExtractor(
                "bug-396.v",
                typing.cast(
                    List[CoqSentence],
                    Project.extract_sentences(
                        CoqDocument(
                            "bug-396.v",
                            CoqParser.parse_source("bug-396.v"),
                            _COQ_EXAMPLES_PATH),
                        sentence_extraction_method=SEM.HEURISTIC,
                        return_locations=True,
                        glom_proofs=False)),
                serapi_options=SerAPIOptions.empty(),
                opam_switch=self.test_switch).extracted_commands
            self.assertEqual(len(extracted_commands), 2)

    @pytest.mark.coq_all
    def test_bug_7900(self):
        """
        Verify that certain tactics are not inferred as commands.

        Otherwise, an extra command is extracted that actually
        corresponds to a rewrite tactic.
        """
        filename = "bug_7900.v"
        with pushd(_COQ_EXAMPLES_PATH):
            extracted_commands = CommandExtractor(
                filename,
                typing.cast(
                    List[CoqSentence],
                    Project.extract_sentences(
                        CoqDocument(
                            filename,
                            CoqParser.parse_source(filename),
                            _COQ_EXAMPLES_PATH),
                        sentence_extraction_method=SEM.HEURISTIC,
                        return_locations=True,
                        glom_proofs=False)),
                serapi_options=SerAPIOptions.empty(),
                opam_switch=self.test_switch).extracted_commands
            self.assertEqual(len(extracted_commands), 9)

    @pytest.mark.coq_all
    def test_extract_subproofs(self):
        """
        Verify that subproofs are correctly extracted.
        """
        with pushd(_COQ_EXAMPLES_PATH):
            extracted_commands = CommandExtractor(
                "subproofs.v",
                typing.cast(
                    List[CoqSentence],
                    Project.extract_sentences(
                        CoqDocument(
                            "subproofs.v",
                            CoqParser.parse_source("subproofs.v"),
                            _COQ_EXAMPLES_PATH),
                        sentence_extraction_method=SEM.HEURISTIC,
                        return_locations=True,
                        glom_proofs=False)),
                serapi_options=SerAPIOptions.empty(),
                opam_switch=self.test_switch).extracted_commands
            self.assertEqual(len(extracted_commands), 4)

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
                serapi_options=SerAPIOptions.empty(),
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
                serapi_options=SerAPIOptions.empty(),
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

    @pytest.mark.coq_all
    def test_skip_extraction(self) -> None:
        """
        Verify extraction of goals and qualified idents can be skipped.
        """
        with pushd(_COQ_EXAMPLES_PATH):
            extracted_commands_no_goals_or_idents = CommandExtractor(
                "simple.v",
                typing.cast(
                    List[CoqSentence],
                    Project.extract_sentences(
                        CoqDocument(
                            "simple.v",
                            CoqParser.parse_source("simple.v"),
                            _COQ_EXAMPLES_PATH),
                        sentence_extraction_method=SEM.HEURISTIC,
                        return_locations=True,
                        glom_proofs=False)),
                serapi_options=SerAPIOptions.empty(),
                extract_goals=False,
                extract_qualified_idents=False,
                opam_switch=self.test_switch).extracted_commands
        expected_command_text = [
            "Inductive seq : nat -> Set := "
            "| niln : seq 0 "
            "| consn : forall n : nat, nat -> seq n -> seq (S n).",
            "Fixpoint length (n : nat) (s : seq n) {struct s} : nat := "
            "match s with "
            "| niln => 0 "
            "| consn i _ s' => S (length i s') "
            "end.",
            "Let m := seq 0.",
            "Theorem length_corr : forall (n : nat) (s : seq n), length n s = n.",
            "Check length_corr.",
            "Notation \"n .+1\" := (S n)(at level 2, "
            "left associativity, format \"n .+1\"): nat_scope.",
            "Coercion b2Prop (x : bool) := x = true."
        ]
        self.assertEqual(
            [c.command.text for c in extracted_commands_no_goals_or_idents],
            expected_command_text)
        self.assertNotIn(
            False,
            [
                s.goals is None
                for c in extracted_commands_no_goals_or_idents
                for s in c.sentences_iter()
            ])
        self.assertEqual(
            [
                0 for c in extracted_commands_no_goals_or_idents
                for _ in c.sentences_iter()
            ],
            [
                len(s.qualified_identifiers)
                for c in extracted_commands_no_goals_or_idents
                for s in c.sentences_iter()
            ])
        self.assertEqual(
            [
                0 for c in extracted_commands_no_goals_or_idents
                for _ in c.sentences_iter()
            ],
            [
                len(s.goals_qualified_identifiers)
                for c in extracted_commands_no_goals_or_idents
                for s in c.sentences_iter()
            ])

    @pytest.mark.coq_all
    def test_rollback(self) -> None:
        """
        Test rolling back extraction of commands and sentences.
        """
        with pushd(_COQ_EXAMPLES_PATH):
            sentences = typing.cast(
                List[CoqSentence],
                Project.extract_sentences(
                    CoqDocument(
                        "nested.v",
                        CoqParser.parse_source("nested.v"),
                        _COQ_EXAMPLES_PATH),
                    sentence_extraction_method=SEM.HEURISTIC,
                    return_locations=True,
                    glom_proofs=False))
            with CommandExtractor("nested.v",
                                  serapi_options=SerAPIOptions.empty(),
                                  use_goals_diff=False,
                                  opam_switch=self.test_switch) as extractor:
                assert extractor.serapi is not None
                for sentence in sentences:
                    extractor.extract_vernac_sentence(sentence)
                extracted_commands = VernacCommandDataList(
                    list(extractor.extracted_commands))
                extracted_sentences = extractor.extracted_sentences
                with self.subTest("command"):
                    with self.assertRaises(IndexError):
                        extractor.rollback(30)
                    with self.assertRaises(IndexError):
                        extractor.rollback(-1)
                    rolled_back_commands, rolled_back_sentences = extractor.rollback()
                    self.assertFalse(rolled_back_sentences)
                    self.assertEqual(
                        rolled_back_commands,
                        extracted_commands[-1 :])
                    self.assertEqual(len(extractor.serapi.frame_stack), 7)
                with self.subTest("nested_command"):
                    # both the innter and outer nested proof should be
                    # rolled back together
                    rolled_back_commands, rolled_back_sentences = extractor.rollback()
                    self.assertFalse(rolled_back_sentences)
                    self.assertEqual(
                        rolled_back_commands,
                        extracted_commands[-3 :-1])
                    self.assertEqual(len(extractor.serapi.frame_stack), 5)
                with self.subTest("sentences"):
                    with self.assertRaises(IndexError):
                        extractor.rollback_sentences(30)
                    with self.assertRaises(IndexError):
                        extractor.rollback_sentences(-1)
                    (rolled_back_commands,
                     rolled_back_sentences) = extractor.rollback_sentences(2)
                    self.assertEqual(
                        rolled_back_commands,
                        extracted_commands[-4 :-3])
                    self.assertEqual(
                        rolled_back_sentences,
                        extracted_sentences[5 : 6])
                    self.assertEqual(len(extractor.serapi.frame_stack), 3)
                for sentence in chain(rolled_back_sentences,
                                      rolled_back_commands.to_CoqSentences()):
                    extractor.extract_vernac_sentence(sentence)
                with self.subTest("location"):
                    # rollback to the start of the proof of foobar
                    bad_location = SexpInfo.Loc(
                        "_nested.v",
                        2,
                        103,
                        2,
                        110,
                        103,
                        110)
                    large_location = SexpInfo.Loc(
                        "nested.v",
                        2000,
                        103000,
                        2000,
                        110000,
                        103000,
                        110000)
                    location = SexpInfo.Loc(
                        "nested.v",
                        2,
                        103,
                        2,
                        110,
                        103,
                        110)
                    with self.assertRaises(RuntimeError):
                        extractor.rollback_to_location(bad_location)
                    (rolled_back_commands,
                     rolled_back_sentences
                     ) = extractor.rollback_to_location(large_location)
                    self.assertFalse(rolled_back_commands)
                    self.assertFalse(rolled_back_sentences)
                    (rolled_back_commands,
                     rolled_back_sentences
                     ) = extractor.rollback_to_location(location)
                    self.assertEqual(
                        rolled_back_commands,
                        extracted_commands[-4 :-3])
                    self.assertEqual(
                        rolled_back_sentences,
                        extracted_sentences[2 : 6])
                    extractor.pre_proof_id = "foobar"


if __name__ == "__main__":
    unittest.main()