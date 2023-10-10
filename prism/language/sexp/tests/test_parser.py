#
# Copyright (c) 2023 Radiance Technologies, Inc.
#
# This file is part of PRISM
# (see https://github.com/orgs/Radiance-Technologies/prism).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program. If not, see
# <http://www.gnu.org/licenses/>.
#
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
