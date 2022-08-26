"""
Tests for the StrWithLocation class.
"""
import unittest
from pathlib import Path

from prism.data.document import CoqDocument
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
        # print(self.located_str_simple.string)
        # print(self.located_str_simple.indices)

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
            r"\b[a-z]{3}\b",
            self.example,
            maxsplit=1,
            return_split=True)
        expected_result_2_str = [
            "",
            "The quick ",
            "red",
            "\nfox jumps\n\nover the\tlazy dog."
        ]
        expected_result_2_ind = [
            [],
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
        ...


if __name__ == "__main__":
    unittest.main()
