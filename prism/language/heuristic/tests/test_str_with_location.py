"""
Tests for the StrWithLocation class.
"""
import unittest
from pathlib import Path

from prism.data.document import CoqDocument
from prism.language.gallina.analyze import SexpInfo
from prism.language.gallina.parser import CoqParser
from prism.language.heuristic.util import ParserUtils
from prism.tests import _COQ_EXAMPLES_PATH


class TestStrWithLocation(unittest.TestCase):
    """
    Tests for StrWithLocation.
    """

    @classmethod
    def setUpClass(cls):
        """
        Set up common test data.
        """
        cls.simple_file: Path = _COQ_EXAMPLES_PATH / "simple.v"
        cls.simple_doc = CoqDocument(
            cls.simple_file,
            CoqParser.parse_source(cls.simple_file),
            project_path=_COQ_EXAMPLES_PATH)
        cls.located_str_simple = \
            ParserUtils.StrWithLocation.create_from_file_contents(
                cls.simple_doc.source_code)
        # Yes, I know the phrase isn't quite right. By the time I
        # counted up all the expected indices, I couldn't bring myself
        # to fix it and re-count everything.
        cls.example = ParserUtils.StrWithLocation.create_from_file_contents(
            "The quick red\nfox jumps\n\nover the\tlazy dog.")

    def test_init(self):
        """
        Test object init.
        """
        self.assertEqual(
            len(self.located_str_simple),
            len(self.simple_doc.source_code))

    def test_re_split(self):
        """
        Test re_split class method.
        """
        split_result_1 = ParserUtils.StrWithLocation.re_split(
            r"\b[a-z]{3}\b",
            self.example)
        expected_result_1_str = [
            "The quick ",
            "\n",
            " jumps\n\nover ",
            "\tlazy ",
            "."
        ]
        expected_result_1_ind = [
            [(i,
              i + 1) for i in range(10)],
            [(13,
              14)],
            [(i,
              i + 1) for i in range(17,
                                    30)],
            [(i,
              i + 1) for i in range(33,
                                    39)],
            [(42,
              43)]
        ]
        expected_result_1 = [
            ParserUtils.StrWithLocation(i,
                                        j) for i,
            j in zip(expected_result_1_str,
                     expected_result_1_ind)
        ]
        self.assertEqual(split_result_1, expected_result_1)
        split_result_2 = ParserUtils.StrWithLocation.re_split(
            r"(\b[a-z]{3}\b)",
            self.example,
            maxsplit=1)
        expected_result_2_str = [
            "The quick ",
            "red",
            "\nfox jumps\n\nover the\tlazy dog."
        ]
        expected_result_2_ind = [
            [(i,
              i + 1) for i in range(10)],
            [(i,
              i + 1) for i in range(10,
                                    13)],
            [(i,
              i + 1) for i in range(13,
                                    43)]
        ]
        expected_result_2 = [
            ParserUtils.StrWithLocation(i,
                                        j) for i,
            j in zip(expected_result_2_str,
                     expected_result_2_ind)
        ]
        self.assertEqual(split_result_2, expected_result_2)

    def test_re_sub(self):
        """
        Test re_sub class method.
        """
        sub_result_1 = ParserUtils.StrWithLocation.re_sub(
            " ",
            "  ",
            self.example,
            count=2)
        expected_result_1_indices = [(i, i + 1) for i in range(43)]
        expected_result_1_indices.insert(3, (3, 4))
        expected_result_1_indices.insert(10, (9, 10))
        expected_result_1 = ParserUtils.StrWithLocation(
            "The  quick  red\nfox jumps\n\nover the\tlazy dog.",
            expected_result_1_indices)
        self.assertEqual(sub_result_1, expected_result_1)
        sub_result_2 = ParserUtils.StrWithLocation.re_sub(
            r"red\nfox jumps",
            "*",
            self.example)
        expected_result_2_indices = [(i, i + 1) for i in range(43)]
        expected_result_2_indices = expected_result_2_indices[: 10] + [
            (10,
             23)
        ] + expected_result_2_indices[23 :]
        expected_result_2 = ParserUtils.StrWithLocation(
            "The quick *\n\nover the\tlazy dog.",
            expected_result_2_indices)
        self.assertEqual(sub_result_2, expected_result_2)

    def test_strip(self):
        """
        Ensure strip, lstrip, and rstrip methods work as they should.
        """
        example = ParserUtils.StrWithLocation(
            "    \ta b c \t \t ",
            [(i,
              i + 1) for i in range(15)])
        lstrip_result = example.lstrip()
        rstrip_result = example.rstrip()
        strip_result = example.strip()
        lstrip_expected = example[5 :]
        rstrip_expected = example[: 10]
        strip_expected = example[5 : 10]
        self.assertEqual(lstrip_result, lstrip_expected)
        self.assertEqual(rstrip_result, rstrip_expected)
        self.assertEqual(strip_result, strip_expected)

    def test_get_location(self):
        """
        Ensure locations are generated properly from indices.
        """
        split_result = ParserUtils.StrWithLocation.re_split(
            "Check",
            self.located_str_simple)
        loc_results = []
        for res in split_result:
            loc_results.append(
                res.get_location(
                    self.simple_doc.source_code,
                    str(self.simple_file)))
        expected_loc_results = [
            SexpInfo.Loc(
                filename=str(self.simple_file),
                lineno=0,
                bol_pos=0,
                lineno_last=28,
                bol_pos_last=0,
                beg_charno=0,
                end_charno=1265),
            SexpInfo.Loc(
                filename=str(self.simple_file),
                lineno=28,
                bol_pos=7,
                lineno_last=39,
                bol_pos_last=0,
                beg_charno=1271,
                end_charno=1399),
            SexpInfo.Loc(
                filename=str(self.simple_file),
                lineno=39,
                bol_pos=5,
                lineno_last=44,
                bol_pos_last=0,
                beg_charno=1405,
                end_charno=1546)
        ]
        self.assertEqual(loc_results, expected_loc_results)
        split_result_2 = ParserUtils.StrWithLocation.re_split(
            ": seq",
            self.located_str_simple,
            maxsplit=1)
        loc_results_2 = []
        for res in split_result_2:
            loc_results_2.append(
                res.get_location(
                    self.simple_doc.source_code,
                    str(self.simple_file)))
        expected_loc_results_2 = [
            SexpInfo.Loc(
                filename=str(self.simple_file),
                lineno=0,
                bol_pos=0,
                lineno_last=15,
                bol_pos_last=2,
                beg_charno=0,
                end_charno=884),
            SexpInfo.Loc(
                filename=str(self.simple_file),
                lineno=15,
                bol_pos=14,
                lineno_last=44,
                bol_pos_last=0,
                beg_charno=890,
                end_charno=1546),
        ]
        self.assertEqual(loc_results_2, expected_loc_results_2)


if __name__ == "__main__":
    unittest.main()
