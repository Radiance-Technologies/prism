"""
Test suite for prism.util.opam.
"""
import unittest

from prism.util.opam import OCamlVersion, OpamVersion, Version
from prism.util.opam.formula import (
    LogicalVF,
    LogOp,
    Not,
    ParensVF,
    RelOp,
    VersionConstraint,
    VersionFormula,
)
from prism.util.parse import ParseError


class TestVersionFormula(unittest.TestCase):
    """
    Test suite for 'VersionConstraint'.
    """

    def test_contains(self):
        """
        Verify constraint checking work via `in` operator.
        """
        self.assertIn(
            OCamlVersion(8,
                         10,
                         2),
            LogicalVF(
                VersionConstraint(RelOp.LEQ,
                                  OCamlVersion(8,
                                               10,
                                               2)),
                LogOp.AND,
                VersionConstraint(RelOp.GEQ,
                                  OCamlVersion(8,
                                               10,
                                               2))))
        self.assertNotIn(
            OCamlVersion(8,
                         10,
                         2),
            LogicalVF(
                VersionConstraint(RelOp.LEQ,
                                  OCamlVersion(8,
                                               11,
                                               2)),
                LogOp.AND,
                VersionConstraint(RelOp.GT,
                                  OCamlVersion(8,
                                               10,
                                               2))))
        # open bound on a prerelease
        self.assertIn(
            OCamlVersion(8,
                         10,
                         2),
            LogicalVF(
                VersionConstraint(RelOp.GT,
                                  OCamlVersion(8,
                                               10,
                                               2,
                                               "")),
                LogOp.AND,
                VersionConstraint(RelOp.LEQ,
                                  OCamlVersion(8,
                                               10,
                                               2))))
        self.assertIn(
            OCamlVersion(8,
                         10,
                         2),
            Not(VersionConstraint(RelOp.GT,
                                  OCamlVersion(8,
                                               10,
                                               2))))
        self.assertNotIn(
            OCamlVersion(8,
                         10,
                         2),
            Not(VersionConstraint(RelOp.GEQ,
                                  OCamlVersion(8,
                                               10,
                                               2))))
        self.assertNotIn(
            OCamlVersion(8,
                         10,
                         2),
            Not(
                ParensVF(
                    Not(VersionConstraint(RelOp.GT,
                                          OCamlVersion(8,
                                                       10,
                                                       2))))))
        complex_formula = VersionFormula.parse(
            '!= "2.0.pre" & !(<= "3") & <= 3.9.0 | =4.0+dev')
        self.assertIn(OCamlVersion(3, 2, 0), complex_formula)
        self.assertNotIn(Version.parse("2.0.pre"), complex_formula)
        self.assertNotIn(Version.parse("3"), complex_formula)
        self.assertNotIn(Version.parse("4.0+de"), complex_formula)
        self.assertIn(Version.parse("4.0+dev"), complex_formula)

    def test_filter(self):
        """
        Verify that a list of versions can be reduced to a feasible set.
        """
        lower_bound = OCamlVersion(4, 2)
        upper_bound = OCamlVersion(5, 1, 2)
        vc = LogicalVF(
            VersionConstraint(RelOp.GEQ,
                              lower_bound),
            LogOp.AND,
            VersionConstraint(RelOp.LEQ,
                              upper_bound))
        versions = [
            '0.1',
            '1.0.0',
            '2.0.0',
            '2.1.0',
            '3.0.0',
            '3.0.1',
            '4.0.0',
            '4.1.0',
            '4.2~',
            '4.2',
            '4.2.0~',
            '4.2.0',
            '4.2.1'
            '4.3.0',
            '5.0~',
            '5.0.0',
            '5.1.0',
            '5.1.1',
            '5.1.2',
            '5.2.0',
            '6',
            '7.0',
            '7.1a'
        ]
        versions = [OCamlVersion.parse(v) for v in versions]
        expected = [
            '4.2',
            '4.2.0~',
            '4.2.0',
            '4.2.1'
            '4.3.0',
            '5.0~',
            '5.0.0',
            '5.1.0',
            '5.1.1',
            '5.1.2'
        ]
        with self.subTest("lower_closed_upper_closed"):
            expected = [OCamlVersion.parse(v) for v in expected]
            self.assertEqual(vc.filter(versions), expected)
        with self.subTest("lower_open_upper_closed"):
            object.__setattr__(vc.left, 'relop', RelOp.GT)
            self.assertEqual(vc.filter(versions), expected[1 :])
        with self.subTest("lower_open_upper_open"):
            object.__setattr__(vc.right, 'relop', RelOp.LT)
            self.assertEqual(vc.filter(versions), expected[1 :-1])
        with self.subTest("lower_closed_upper_open"):
            object.__setattr__(vc.left, 'relop', RelOp.GEQ)
            self.assertEqual(vc.filter(versions), expected[:-1])
        with self.subTest("upper_open"):
            self.assertEqual(
                vc.right.filter(versions),
                versions[: versions.index(OCamlVersion(5,
                                                       1,
                                                       2))])
        with self.subTest("lower_closed"):
            self.assertEqual(
                vc.left.filter(versions),
                versions[versions.index(OCamlVersion(4,
                                                     2)):])
        with self.subTest("unsatisfiable"):
            unsatisfiable = VersionFormula.parse("< 2.0 & > 2.0")
            self.assertEqual(unsatisfiable.filter(versions), [])

    def test_parse(self):
        """
        Verify simple constraints can be parsed.
        """
        self.assertEqual(
            # TODO: Remove build; it is supposed to be a variable, not a
            # version. If we do encounter variables, other machinery
            # must be added.
            VersionFormula.parse(">= 0.7.1 & < 1.0.0"),
            LogicalVF(
                VersionConstraint(RelOp.GEQ,
                                  OCamlVersion(0,
                                               7,
                                               1)),
                LogOp.AND,
                VersionConstraint(RelOp.LT,
                                  OCamlVersion(1,
                                               0,
                                               0))))
        self.assertEqual(
            VersionFormula.parse("<= 1.0.0 | !> 0.7.1+extra"),
            LogicalVF(
                VersionConstraint(RelOp.LEQ,
                                  OCamlVersion(1,
                                               0,
                                               0)),
                LogOp.OR,
                Not(
                    VersionConstraint(
                        RelOp.GT,
                        OCamlVersion(0,
                                     7,
                                     1,
                                     extra="extra")))))
        self.assertEqual(
            VersionFormula.parse("> 0.7.1"),
            VersionConstraint(RelOp.GT,
                              OCamlVersion(0,
                                           7,
                                           1)))
        self.assertEqual(
            VersionFormula.parse("< 1.7.1~pre"),
            VersionConstraint(RelOp.LT,
                              OCamlVersion(1,
                                           7,
                                           1,
                                           "pre")))
        with self.subTest("operator_precedence"):
            self.assertEqual(
                VersionFormula.parse(
                    '!= "2.0.pre" | !(< "3") & <= 3.9.0 | =4.0+dev'),
                LogicalVF(
                    VersionConstraint(RelOp.NEQ,
                                      OpamVersion.parse("2.0.pre")),
                    LogOp.OR,
                    LogicalVF(
                        LogicalVF(
                            Not(
                                ParensVF(
                                    VersionConstraint(
                                        RelOp.LT,
                                        OpamVersion.parse("3")))),
                            LogOp.AND,
                            VersionConstraint(RelOp.LEQ,
                                              OCamlVersion(3,
                                                           9,
                                                           0))),
                        LogOp.OR,
                        VersionConstraint(
                            RelOp.EQ,
                            OpamVersion.parse("4.0+dev")))))
            self.assertEqual(
                VersionFormula.parse(
                    '(!= "2.0.pre" | !(< "3")) & <= 3.9.0 | =4.0+dev'),
                LogicalVF(
                    LogicalVF(
                        ParensVF(
                            LogicalVF(
                                VersionConstraint(
                                    RelOp.NEQ,
                                    OpamVersion.parse("2.0.pre")),
                                LogOp.OR,
                                Not(
                                    ParensVF(
                                        VersionConstraint(
                                            RelOp.LT,
                                            OpamVersion.parse("3")))))),
                        LogOp.AND,
                        VersionConstraint(RelOp.LEQ,
                                          OCamlVersion(3,
                                                       9,
                                                       0))),
                    LogOp.OR,
                    VersionConstraint(RelOp.EQ,
                                      OpamVersion.parse("4.0+dev"))))
        with self.assertRaises(ParseError):
            VersionFormula.parse(
                '!= ("2.0.pre") | !(< "3") & <= 3.9.0 | =4.0+dev')
        # assert not raises
        VersionFormula.parse('(!= "2.0.pre") | !(< "3") & <= 3.9.0 | =4.0+dev')
        with self.assertRaises(ParseError):
            VersionFormula.parse(
                '(!= "2.0.pre" | !(< "3") & <= 3.9.0 | =4.0+dev')
        with self.assertRaises(ParseError):
            VersionFormula.parse('!= "2.0.pre" | !(< 3") & <= 3.9.0 | =4.0+dev')
        with self.assertRaises(ParseError):
            VersionFormula.parse('!= "2.0.pre | !(< "3") & <= 3.9.0 | =4.0+dev')

    def test_str(self):
        """
        Verify pretty-printing matches the expected format.
        """
        formulae = [
            "(= 8.10.2)",
            '!= "2.0.pre" | !(<"3") & <= 3.9.0 | =4.0+dev',
            "> 8.10.2 & <= 8.10.2",
            "!> 8.10.2 & < 8.10.2",
            ">= 8.10.2",
            "!=8.10.2"
        ]
        expected_formulae = [
            '(= "8.10.2")',
            '!= "2.0.pre" | !(< "3") & <= "3.9.0" | = "4.0+dev"',
            '> "8.10.2" & <= "8.10.2"',
            '!> "8.10.2" & < "8.10.2"',
            '>= "8.10.2"',
            '!= "8.10.2"'
        ]
        for formula, expected in zip(formulae, expected_formulae):
            self.assertEqual(str(VersionFormula.parse(formula)), expected)


if __name__ == '__main__':
    unittest.main()
