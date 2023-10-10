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
Test suite for s-expression analysis as part of Coq parsing.
"""
import unittest

from prism.language.gallina.analyze import SexpAnalyzer, SexpInfo
from prism.language.sexp.parser import SexpParser


class TestSexpInfoLoc(unittest.TestCase):
    """
    Test suite for `SexpInfo.Loc`.
    """

    # example loc s-expression
    loc_sexp = SexpParser.parse(
        """
        ( loc
            ( ( (fname(InFile gallina.v))
                (line_nb 1)
                (bol_pos 0)
                (line_nb_last 1)
                (bol_pos_last 0)
                (bp 23)
                (ep 26)
                )
            )
        )""")

    def test_to_sexp(self) -> None:
        """
        Verify invertibility of location analysis.
        """
        loc: SexpInfo.Loc = SexpAnalyzer.analyze_loc(self.loc_sexp)
        self.assertEqual(
            loc.to_sexp().pretty_format(),
            self.loc_sexp.pretty_format())


if __name__ == '__main__':
    unittest.main()
