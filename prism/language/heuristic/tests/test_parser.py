"""
Test suite for heuristic parsers.
"""
import unittest
from itertools import chain, repeat
from pathlib import Path

from prism.language.gallina.parser import CoqParser
from prism.language.heuristic.parser import HeuristicParser
from prism.tests import _COQ_EXAMPLES_PATH


class TestHeuristicParser(unittest.TestCase):
    """
    Test suite for `HeuristicParser`.
    """

    def setUp(self) -> None:
        """
        Set up a common document for each test.
        """
        coq_example_files = ["simple", "nested", "Alphabet"]
        self.test_files = {
            coq_file: Path(_COQ_EXAMPLES_PATH) / f"{coq_file}.v"
            for coq_file in coq_example_files
        }
        self.test_contents = {
            name: CoqParser.parse_source(path) for name,
            path in self.test_files.items()
        }

    def test_simple_statistics(self):
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
                2
            ],
            theorem_indices={1,
                             2,
                             3},
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
                           23},
            query_indices=[4,
                           6,
                           9,
                           24],
            fail_indices={},
            nesting_allowed=[False for _ in range(25)],
            custom_tactics=set())
        sentences = HeuristicParser._get_sentences(self.test_contents["simple"])
        actual_stats = HeuristicParser._compute_sentence_statistics(sentences)
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
            query_indices=[16],
            fail_indices={},
            nesting_allowed=list(chain(repeat(False,
                                              6),
                                       repeat(True,
                                              11))),
            custom_tactics=set())
        sentences = HeuristicParser._get_sentences(self.test_contents["nested"])
        actual_stats = HeuristicParser._compute_sentence_statistics(sentences)
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
            query_indices=[],
            fail_indices={},
            nesting_allowed=[False for _ in range(170)],
            custom_tactics=set())
        sentences = HeuristicParser._get_sentences(
            self.test_contents["Alphabet"])
        actual_stats = HeuristicParser._compute_sentence_statistics(sentences)
        self.assertEqual(actual_stats, expected_stats)


if __name__ == '__main__':
    unittest.main()
