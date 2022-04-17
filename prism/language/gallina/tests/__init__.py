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
