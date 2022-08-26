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
        cls.located_str = ParserUtils.StrWithLocation.create_from_file_contents(
            cls.simple_doc.source_code)

    def test_init(self):
        """
        Test object init.
        """
        self.assertEqual(
            len(self.located_str),
            len(self.simple_doc.source_code))
        print(self.located_str.string)
        print(self.located_str.indices)

    def test_re_split(self):
        """
        Test re_split class method.
        """
        split_result = ParserUtils.StrWithLocation.re_split(
            "Print",
            self.located_str)
        for res in split_result:
            print(res)

    def test_re_sub(self):
        """
        Test re_sub class method.
        """
        ...


if __name__ == "__main__":
    unittest.main()
