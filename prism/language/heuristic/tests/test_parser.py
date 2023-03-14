"""
Test suite for heuristic parsers.
"""
import json
import typing
import unittest
from itertools import chain, repeat
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

from prism.language.gallina.analyze import SexpInfo
from prism.language.gallina.parser import CoqParser
from prism.language.heuristic.parser import (
    CoqComment,
    CoqSentence,
    HeuristicParser,
    SerAPIParser,
)
from prism.tests import _COQ_EXAMPLES_PATH
from prism.util.path import get_relative_path


class TestHeuristicParser(unittest.TestCase):
    """
    Test suite for `HeuristicParser`.
    """

    test_files: Dict[str, Path]
    test_contents: Dict[str, str]
    test_list: Dict[str, List[str]]
    test_glom_list: Dict[str, List[str]]
    test_comment_list: Dict[str, List[str]]

    @classmethod
    def setUpClass(cls) -> None:
        """
        Set up a common document for each test.
        """
        coq_example_files = [
            "simple",
            "nested",
            "Alphabet",
            "attribute_syntax",
            "notations"
        ]
        cls.test_files = {
            coq_file: Path(_COQ_EXAMPLES_PATH) / f"{coq_file}.v"
            for coq_file in coq_example_files
        }
        cls.test_contents = {
            name: CoqParser.parse_source(path) for name,
            path in cls.test_files.items()
        }
        cls.test_list = {}
        cls.test_glom_list = {}
        cls.test_comment_list = {}
        expected_filename = _COQ_EXAMPLES_PATH / "split_by_sentence_expected.json"
        for coq_file in coq_example_files:
            test_filename = cls.test_files[coq_file]
            with open(test_filename, "rt") as f:
                cls.test_contents[coq_file] = f.read()
            with open(expected_filename, "rt") as f:
                contents = json.load(f)
                try:
                    cls.test_list[coq_file] = contents[f"{coq_file}_test_list"]
                except KeyError:
                    pass
                try:
                    cls.test_glom_list[coq_file] = contents[
                        f"{coq_file}_test_glom_list"]
                except KeyError:
                    pass
                try:
                    cls.test_comment_list[coq_file] = contents[
                        f"{coq_file}_test_comment_list"]
                except KeyError:
                    pass

    def test_parsing(self) -> None:
        """
        Test accuracy of heuristic parsing on a number of examples.
        """
        for coq_file in self.test_list.keys():
            expected_parsed = self.test_list[coq_file] + self.test_comment_list[
                coq_file]
            test_file_name = self.test_files[coq_file]
            (sentences,
             comments) = typing.cast(
                 Tuple[List[CoqSentence],
                       List[CoqComment]],
                 HeuristicParser.parse_sentences_from_file(
                     test_file_name,
                     glom_proofs=False,
                     return_comments=True))
            actual_parsed = [str(s) for s in (sentences + comments)]
            (sentences,
             comments) = typing.cast(
                 Tuple[List[CoqSentence],
                       List[CoqComment]],
                 HeuristicParser.parse_sentences_from_file(
                     test_file_name,
                     glom_proofs=False,
                     return_locations=True,
                     return_comments=True))
            actual_parsed_with_locs = [str(s) for s in (sentences + comments)]
            self.assertEqual(actual_parsed, expected_parsed)
            self.assertEqual(actual_parsed_with_locs, expected_parsed)

    def test_proof_glomming(self) -> None:
        """
        Test accuracy of heuristic proof glomming on multiple examples.
        """
        for coq_file, expected_parsed in self.test_glom_list.items():
            test_file_name = self.test_files[coq_file]
            actual_parsed = [
                str(s) for s in HeuristicParser.parse_sentences_from_file(
                    test_file_name,
                    glom_proofs=True,
                    return_locations=False)
            ]
            with self.assertRaises(NotImplementedError):
                _ = [
                    str(s) for s in HeuristicParser.parse_sentences_from_file(
                        test_file_name,
                        glom_proofs=True,
                        return_locations=True)
                ]
            self.assertEqual(actual_parsed, expected_parsed)

    def test_simple_statistics(self) -> None:
        """
        Verify statistic match expectation for simple Coq file.
        """
        expected_stats = HeuristicParser.SentenceStatistics(
            depths=[
                0,
                1,
                2,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                3,
                2,
                2,
                3
            ],
            theorem_indices={1,
                             2,
                             3,
                             26},
            starter_indices={7},
            tactic_indices={5,
                            8,
                            11,
                            18,
                            19},
            ender_indices=[23],
            program_indices=[],
            obligation_indices=[],
            proof_indices={1,
                           2,
                           3,
                           5,
                           7,
                           8,
                           11,
                           18,
                           19,
                           23,
                           26},
            query_indices={4,
                           6,
                           9,
                           24},
            fail_indices=set(),
            nesting_allowed=[False for _ in range(27)],
            requirements=set(),
            custom_tactics=set())
        sentences = HeuristicParser._get_sentences(self.test_contents["simple"])
        actual_stats = HeuristicParser._compute_sentence_statistics(
            [str(s) for s in sentences])
        self.assertEqual(actual_stats, expected_stats)

    def test_nested_statistics(self):
        """
        Verify statistic match expectation for a Coq file with nesting.
        """
        expected_stats = HeuristicParser.SentenceStatistics(
            depths=[
                1,
                2,
                2,
                2,
                2,
                2,
                1,
                2,
                3,
                3,
                3,
                3,
                3,
                3,
                2,
                2,
                1,
            ],
            theorem_indices={0,
                             1,
                             7,
                             8},
            starter_indices={2,
                             9},
            tactic_indices={4,
                            10,
                            11,
                            12,
                            14},
            ender_indices=[5,
                           13,
                           15],
            program_indices=[],
            obligation_indices=[],
            proof_indices={0,
                           1,
                           2,
                           4,
                           5,
                           7,
                           8,
                           9,
                           10,
                           11,
                           12,
                           13,
                           14,
                           15},
            query_indices={16},
            fail_indices=set(),
            nesting_allowed=list(chain(repeat(False,
                                              6),
                                       repeat(True,
                                              11))),
            requirements={'Program'},
            custom_tactics=set())
        sentences = HeuristicParser._get_sentences(self.test_contents["nested"])
        actual_stats = HeuristicParser._compute_sentence_statistics(
            [str(s) for s in sentences])
        self.assertEqual(actual_stats, expected_stats)

    def test_Alphabet_statistics(self):
        """
        Verify statistic match expectation for a real Coq file.

        In particular, this file contains Programs and Obligations.
        """
        expected_theorem_indices = {
            4,
            10,
            11,
            24,
            47,
            60,
            61,
            70,
            71,
            83,
            154,
            155,
            157,
            161,
        }
        expected_starter_indices = {
            5,
            12,
            25,
            39,
            48,
            54,
            62,
            72,
            84,
            88,
            100,
            119,
            158,
            162,
        }
        expected_tactic_indices = set(
            chain(
                range(6,
                      9),
                range(13,
                      23),
                range(26,
                      38),
                range(40,
                      46),
                range(49,
                      53),
                range(55,
                      58),
                range(63,
                      69),
                range(73,
                      79),
                range(85,
                      87),
                range(89,
                      90),
                range(91,
                      93),
                range(94,
                      96),
                range(97,
                      99),
                range(101,
                      104),
                range(104,
                      105),
                range(106,
                      108),
                range(109,
                      119,
                      2),
                range(120,
                      128),
                range(129,
                      130),
                range(131,
                      132),
                range(133,
                      138),
                range(139,
                      144),
                range(159,
                      160),
                range(163,
                      164),
            ))
        expected_ender_indices = [
            9,
            23,
            38,
            46,
            53,
            58,
            69,
            79,
            87,
            99,
            118,
            144,
            160,
            164
        ]
        expected_program_indices = [24, 47, 83]
        expected_obligation_indices = [
            25,
            39,
            48,
            54,
            84,
            88,
            100,
            119,
        ]
        expected_stats = HeuristicParser.SentenceStatistics(
            depths=sum(
                [
                    list(lst) for lst in [
                        repeat(0,
                               4),
                        repeat(1,
                               7),
                        repeat(2,
                               13),
                        repeat(3,
                               23),
                        repeat(4,
                               12),
                        repeat(3,
                               1),
                        repeat(4,
                               1),
                        repeat(5,
                               10),
                        repeat(6,
                               9),
                        repeat(5,
                               3),
                        repeat(7,
                               62),
                        repeat(6,
                               9),
                        repeat(7,
                               1),
                        repeat(8,
                               2),
                        repeat(9,
                               8),
                        repeat(8,
                               5)
                    ]
                ],
                []),
            requirements={
                'FMapAVL',
                'Coq.List',
                'Coq.Relations',
                'OrderedTypeAlt',
                'FSetAVL',
                'Coq.ZArith',
                'Coq.RelationClasses'
            },
            theorem_indices=expected_theorem_indices,
            starter_indices=expected_starter_indices,
            tactic_indices=expected_tactic_indices,
            ender_indices=expected_ender_indices,
            program_indices=expected_program_indices,
            obligation_indices=expected_obligation_indices,
            proof_indices=expected_theorem_indices.union(
                expected_starter_indices,
                expected_tactic_indices,
                expected_ender_indices,
                expected_program_indices,
                expected_obligation_indices),
            query_indices=set(),
            fail_indices=set(),
            nesting_allowed=[False for _ in range(170)],
            custom_tactics=set())
        sentences = HeuristicParser._get_sentences(
            self.test_contents["Alphabet"])
        actual_stats = HeuristicParser._compute_sentence_statistics(
            [str(s) for s in sentences])
        self.assertEqual(actual_stats, expected_stats)

    def test_attribute_syntax_statistics(self):
        """
        Verify that non-legacy attributes are correctly detected.
        """
        expected_stats = HeuristicParser.SentenceStatistics(
            depths=[0,
                    0,
                    1,
                    1,
                    1,
                    1,
                    2,
                    2,
                    3,
                    3],
            theorem_indices={2,
                             6,
                             8},
            starter_indices=set(),
            tactic_indices=set(),
            ender_indices=[],
            program_indices=[8],
            obligation_indices=[],
            proof_indices={2,
                           6,
                           8},
            query_indices={3,
                           7},
            fail_indices={5},
            nesting_allowed=list(repeat(False,
                                        10)),
            requirements={'Coq.Program'},
            custom_tactics={"foo"})
        sentences = HeuristicParser._get_sentences(
            self.test_contents["attribute_syntax"])
        actual_stats = HeuristicParser._compute_sentence_statistics(
            [str(s) for s in sentences])
        self.assertEqual(actual_stats, expected_stats)

    def test_parser_return_location(self):
        """
        Ensure the heuristic parser can return sentences with locs.
        """
        simple_file = self.test_files['simple']
        sentences = HeuristicParser.parse_sentences_from_file(
            simple_file,
            project_path=_COQ_EXAMPLES_PATH,
            return_locations=True,
            glom_proofs=False)
        simple_filename = get_relative_path(simple_file, _COQ_EXAMPLES_PATH)
        expected_loc_results = {
            0: SexpInfo.Loc(
                filename=str(simple_filename),
                lineno=14,
                bol_pos=846,
                lineno_last=16,
                bol_pos_last=893,
                beg_charno=846,
                end_charno=946),
            4: SexpInfo.Loc(  # About seq.
                filename=str(simple_filename),
                lineno=26,
                bol_pos=1237,
                lineno_last=26,
                bol_pos_last=1237,
                beg_charno=1239,
                end_charno=1248),
            11: SexpInfo.Loc(  # trivial.
                filename=str(simple_filename),
                lineno=32,
                bol_pos=1317,
                lineno_last=32,
                bol_pos_last=1317,
                beg_charno=1321,
                end_charno=1328)
        }
        for i, v in expected_loc_results.items():
            self.assertEqual(sentences[i].location, v)


@pytest.mark.coq_all
class TestSerAPIParser(unittest.TestCase):
    """
    Unit test suite for the heuristic SerAPI parser.
    """

    test_files: Dict[str, Path]
    test_glom_ltac_list: Dict[str, List[str]]

    @classmethod
    def setUpClass(cls) -> None:
        """
        Set up a common document for each test.
        """
        coq_example_files = ["simple", "nested", "Alphabet"]
        cls.test_files = {
            coq_file: Path(_COQ_EXAMPLES_PATH) / f"{coq_file}.v"
            for coq_file in coq_example_files
        }
        expected_filename = Path(
            _COQ_EXAMPLES_PATH) / "split_by_sentence_expected.json"
        cls.test_glom_ltac_list = {}
        for coq_file in coq_example_files:
            with open(expected_filename, "rt") as f:
                contents = json.load(f)
                cls.test_glom_ltac_list[coq_file] = contents[
                    f"{coq_file}_test_glom_ltac_list"]

    def test_glom_ltac(self):
        """
        Verify that contiguous regions of ltac get glommed.
        """
        for coq_file, test_file in self.test_files.items():
            expected_glommed = self.test_glom_ltac_list[coq_file]
            with self.subTest(coq_file):
                actual_glommed = SerAPIParser.parse_sentences_from_file(
                    test_file,
                    project_path=_COQ_EXAMPLES_PATH,
                    glom_proofs=False,
                    glom_ltac=True,
                    return_asts=True,
                    return_locations=True)
                actual_glommed_sentences = [
                    " ".join(str(s).split()) for s in actual_glommed
                ]
                self.assertEqual(expected_glommed, actual_glommed_sentences)
                # assert some ltac ASTs got glommed
                self.assertTrue(
                    any(
                        s.ast is not None and s.ast.head() == "glommed_ltac"
                        for s in actual_glommed))
                # assert locations got glommed
                self.assertTrue(
                    all(s.location is not None for s in actual_glommed))


if __name__ == '__main__':
    unittest.main()
