"""
Test suite for s-expression parsing.
"""

import unittest

from prism.language.sexp.parser import SexpParser


class TestSexpParser(unittest.TestCase):
    """
    Test suite for `SexpParser`.
    """

    def test_parse(self):
        """
        Verify basic parsing functionality.
        """
        parse = SexpParser.parse
        with self.assertRaises(ValueError):
            parse("")
        with self.assertRaises(ValueError):
            parse("() ()")
        with self.assertRaises(ValueError):
            parse("(")
        with self.assertRaises(ValueError):
            parse("())")
        with self.assertRaises(ValueError):
            parse('("asdfasdf)"')
        self.assertEqual(str(parse('"())"')), '"())"')
        self.assertEqual(str(parse("()")), "()")
        self.assertEqual(
            str(parse('(expr \n  (v "literal")\n  (loc ([LOC])))')),
            '(expr (v "literal") (loc ([LOC])))')
        # NOTE: The following implies lack of invertibility without an
        # alternative printing option to `str`.
        self.assertEqual(str(SexpParser.parse("(\\n)")), "(\n)")
        self.assertEqual(str(SexpParser.parse("(\\))")), "(\\))")
        self.assertEqual(str(SexpParser.parse("日本語能力!!ソﾊﾝｶｸ")), "日本語能力!!ソﾊﾝｶｸ")
        self.assertEqual(
            str(SexpParser.parse('("dfsdf\\xbf\\" ")')),
            '("dfsdf\\xbf\\" ")')


if __name__ == '__main__':
    unittest.main()
