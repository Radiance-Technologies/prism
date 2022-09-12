"""
Test suite for `prism.util.opam.formula`.
"""
import unittest

from prism.util.opam import OCamlVersion, OpamVersion, Version
from prism.util.opam.formula import (
    LogicalPF,
    LogicalVF,
    LogOp,
    NotVF,
    PackageFormula,
    ParensVF,
    RelOp,
    VersionConstraint,
    VersionFormula,
)
from prism.util.parse import ParseError


def normalize_spaces(string: str) -> str:  # noqa: D103
    return ' '.join(string.split())


class TestLogical(unittest.TestCase):
    """
    Test suite for `Logical`.
    """

    def test_to_list(self):
        """
        Verify chained logical formulas can be decomposed into lists.
        """
        with self.subTest("conjunction"):
            conjunction: LogicalPF = PackageFormula.parse(
                """
                ("ocaml" {>= "4.08" & < "5.0"} |
                 ("ocaml" {< "4.08~~"} & "ocamlfind-secondary")) &
                "base-unix" &
                "base-threads"
                """)
            self.assertEqual(
                # exercise `Logical` iterator
                [str(d) for d in conjunction],
                [
                    '("ocaml" { >= "4.08" & < "5.0" } |'
                    ' ("ocaml" { < "4.08~~" } & "ocamlfind-secondary"))',
                    '"base-unix"',
                    '"base-threads"'
                ])
        with self.subTest("disjunction"):
            disjunction: LogicalVF = VersionFormula.parse(
                '!= "2.0.pre" | !(< "3") & <= "3.9.0" | ="4.0+dev"')
            self.assertEqual(
                [str(c) for c in disjunction.to_disjunctive_list()],
                ['!= "2.0.pre"',
                 '!(< "3") & <= "3.9.0"',
                 '= "4.0+dev"'])


class TestVersionFormula(unittest.TestCase):
    """
    Test suite for 'VersionFormula'.
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
            NotVF(VersionConstraint(RelOp.GT,
                                    OCamlVersion(8,
                                                 10,
                                                 2))))
        self.assertNotIn(
            OCamlVersion(8,
                         10,
                         2),
            NotVF(VersionConstraint(RelOp.GEQ,
                                    OCamlVersion(8,
                                                 10,
                                                 2))))
        self.assertNotIn(
            OCamlVersion(8,
                         10,
                         2),
            NotVF(
                ParensVF(
                    NotVF(VersionConstraint(RelOp.GT,
                                            OCamlVersion(8,
                                                         10,
                                                         2))))))
        complex_formula = VersionFormula.parse(
            '!= "2.0.pre" & !(<= "3") & <= "3.9.0" | ="4.0+dev"')
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
            unsatisfiable = VersionFormula.parse('< "2.0" & > "2.0"')
            self.assertEqual(unsatisfiable.filter(versions), [])

    def test_parse(self):
        """
        Verify simple constraints can be parsed.
        """
        self.assertEqual(
            # TODO: Remove build; it is supposed to be a variable, not a
            # version. If we do encounter variables, other machinery
            # must be added.
            VersionFormula.parse('>= "0.7.1" & < "1.0.0"'),
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
            VersionFormula.parse('<= "1.0.0" | !> "0.7.1+extra"'),
            LogicalVF(
                VersionConstraint(RelOp.LEQ,
                                  OCamlVersion(1,
                                               0,
                                               0)),
                LogOp.OR,
                NotVF(
                    VersionConstraint(
                        RelOp.GT,
                        OCamlVersion(0,
                                     7,
                                     1,
                                     extra="extra")))))
        self.assertEqual(
            VersionFormula.parse('> "0.7.1"'),
            VersionConstraint(RelOp.GT,
                              OCamlVersion(0,
                                           7,
                                           1)))
        self.assertEqual(
            VersionFormula.parse('< "1.7.1~pre"'),
            VersionConstraint(RelOp.LT,
                              OCamlVersion(1,
                                           7,
                                           1,
                                           "pre")))
        with self.subTest("operator_precedence"):
            self.assertEqual(
                VersionFormula.parse(
                    '!= "2.0.pre" | !(< "3") & <= "3.9.0" | ="4.0+dev"'),
                LogicalVF(
                    VersionConstraint(RelOp.NEQ,
                                      OpamVersion.parse("2.0.pre")),
                    LogOp.OR,
                    LogicalVF(
                        LogicalVF(
                            NotVF(
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
                    '(!= "2.0.pre" | !(< "3")) & <= "3.9.0" | ="4.0+dev"'),
                LogicalVF(
                    LogicalVF(
                        ParensVF(
                            LogicalVF(
                                VersionConstraint(
                                    RelOp.NEQ,
                                    OpamVersion.parse("2.0.pre")),
                                LogOp.OR,
                                NotVF(
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
                '!= ("2.0.pre") | !(< "3") & <= "3.9.0" | ="4.0+dev"')
        # assert not raises
        VersionFormula.parse(
            '(!= "2.0.pre") | !(< "3") & <= "3.9.0" | ="4.0+dev"')
        with self.assertRaises(ParseError):
            VersionFormula.parse(
                '(!= "2.0.pre" | !(< "3") & <= "3.9.0" | ="4.0+dev"')
        with self.assertRaises(ParseError):
            VersionFormula.parse(
                '!= "2.0.pre" | !(< 3") & <= "3.9.0" | ="4.0+dev"')
        with self.assertRaises(ParseError):
            VersionFormula.parse(
                '!= "2.0.pre | !(< "3") & <= "3.9.0" | ="4.0+dev"')

    def test_str(self):
        """
        Verify pretty-printing matches the expected format.
        """
        formulae = [
            '(= "8.10.2")',
            '!= "2.0.pre" \n| !(<"3") & <= "3.9.0" \n  | ="4.0+dev"',
            '> "8.10.2" & <= "8.10.2"',
            '!> "8.10.2" & < "8.10.2"',
            '>=    \n"8.10.2"',
            '!="8.10.2"'
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


class TestPackageFormula(unittest.TestCase):
    """
    Test suite for `PackageFormula`.
    """

    def setUp(self) -> None:
        """
        Prepare some real example formulae taken from OPAM.
        """
        self.formulae = [
            """
            "ocaml" {>= "4.05.0" & < "4.10"} &
            "ocamlfind" {build} &
            "num" &
            "conf-findutils" {build}
            """,
            """
            "ocaml-config" &
            "ocaml-base-compiler" {= "4.08.1"} |
            "ocaml-variants" {>= "4.08.1" & < "4.08.2~"} |
            "ocaml-system" {>= "4.08.1" & < "4.08.2~"}
            """,
            """
            "ocaml" {>= "4.05.0"} &
            "dune" {>= "1.4"} &
            "menhir" {>= "20181113"} &
            "ANSITerminal" &
            "fmt" &
            "logs" &
            "mtime" {>= "1.0.0"} &
            "cmdliner" {>= "1.0.0" & < "1.1.0"} &
            "conf-freetype" &
            "conf-pkg-config" &
            "conf-cairo" &
            "cairo2" &
            "yojson" {>= "1.6.0"} &
            "easy-format"
            """,
            """
            ("ocaml" {>= "4.08" & < "5.0"} |
             ("ocaml" {< "4.08~~"} & "ocamlfind-secondary")) &
            "base-unix" &
            "base-threads"
            """,
            """
            "odoc-parser" {>= "0.9.0" & < "2.0.0"} &
            "astring" &
            "cmdliner" {>= "1.0.0"} &
            "cppo" {build & >= "1.1.0"} &
            "dune" {>= "2.9.1"} &
            "fpath" &
            "ocaml" {>= "4.02.0"} &
            "result" &
            "tyxml" {>= "4.3.0"} &
            "fmt" &
            "ocamlfind" {with-test} &
            "yojson" {< "2.0.0" & with-test} &
            ("ocaml" {< "4.04.1" & with-test} | "sexplib0" {with-test}) &
            "conf-jq" {with-test} &
            "ppx_expect" {with-test} &
            "bos" {with-test} &
            "bisect_ppx" {dev & > "2.5.0"} &
            ("ocaml" {< "4.03.0" & dev} | "mdx" {dev})
            """,
            # TODO: Fully support filters and uncomment these formulas
            # """
            # "ocaml" {= "5.0.0" & post} &
            # "base-unix" {post} &
            # "base-bigarray" {post} &
            # "base-threads" {post} &
            # "base-domains" {post} &
            # "base-nnp" {post} &
            # "ocaml-options-vanilla" {post} &
            # "ocaml-beta" {opam-version < "2.1.0"}
            # """,
            # """
            # "ocaml" {>= "4.03.0"} &
            # "dune" {>= "2.8.0"} &
            # "menhirLib" {= version} &
            # "menhirSdk" {= version}
            # """
        ]
        self.packages = {
            'astring': "1.0",
            'ocaml': "4.07.1",
            'fmt': '1.0',
            'mtime': '2.0',
            'cmdliner': '1.0.1',
            'ocamlfind': '1.93.0',
            'ocaml-config': '2.0',
            'bisect_ppx': '2.6.0',
            'yojson': '1.8.0',
            'result': '1.0',
            'tyxml': '4.3.0',
            'astring': '1.0',
            'num': '1.0',
            'base-threads': '1.0',
            'conf-findutils': '1.0'
        }
        self.packages = {k: Version.parse(v) for k,
                         v in self.packages.items()}
        self.variables = {
            'build': True,
            'with-test': True
        }

    def test_is_satisfied(self):
        """
        Verify satisfaction (or lack thereof) with a number of examples.
        """
        self.packages['dune'] = Version.parse('2.9.1')
        self.packages['menhirLib'] = Version.parse('20181113')
        self.packages['base-unix'] = Version.parse('1')
        self.packages['ocamlfind-secondary'] = Version.parse('1')
        self.packages['ocaml-system'] = Version.parse('4.07.1')
        self.packages['ocaml-variants'] = Version.parse('4.08.1')
        self.variables['dev'] = False
        self.variables['version'] = 20181113
        expected_satisfactions = [
            True,
            True,
            False,
            True,
            False,
            # TODO:
            # False,
            # True
        ]
        for formula, expected in zip(self.formulae, expected_satisfactions):
            actual = PackageFormula.parse(formula)
            actual = actual.is_satisfied(self.packages, self.variables)
            self.assertEqual(actual, expected)

    def test_simplify(self):
        """
        Verify with examples that formulas can be simplified.

        Examples demonstrate simplification to Booleans, removal of
        logical operations, short-circuiting, and variable substitution.
        """
        expected_simplifications = [
            'True',
            normalize_spaces(
                """
            "ocaml-base-compiler" { = "4.08.1" } |
            "ocaml-variants" { >= "4.08.1" & < "4.08.2~" } |
            "ocaml-system" { >= "4.08.1" & < "4.08.2~" }
            """),
            normalize_spaces(
                """
            "dune" { >= "1.4" } &
            "menhir" { >= "20181113" } &
            "ANSITerminal" &
            "logs" &
            "conf-freetype" &
            "conf-pkg-config" &
            "conf-cairo" &
            "cairo2" &
            "easy-format"
            """),
            normalize_spaces(
                """
            (("ocamlfind-secondary")) &
            "base-unix"
            """),
            normalize_spaces(
                """
            "odoc-parser" { >= "0.9.0" & < "2.0.0" } &
            "cppo" { >= "1.1.0" } &
            "dune" { >= "2.9.1" } &
            "fpath" &
            ("sexplib0") &
            "conf-jq" &
            "ppx_expect" &
            "bos" &
            "bisect_ppx" { dev } &
            ("mdx" { dev })
            """),
            # TODO: Fully support filters and uncomment these formulas
            # 'False',
            # """
            # "dune" { >= "2.8.0" } &
            # "menhirLib" { = version } &
            # "menhirSdk" { = version }
            # """
        ]
        for formula, expected in zip(self.formulae, expected_simplifications):
            actual = PackageFormula.parse(formula)
            actual = actual.simplify(self.packages, self.variables)
            self.assertEqual(str(actual), expected)

    def test_size(self):
        """
        Verify calculation of the size property is correct.
        """
        expected_sizes = [
            4,
            1,
            14,
            3,
            18,
            # TODO: Fully support filters and uncomment these sizes
            # 7,
            # 4
        ]
        for formula, size in zip(self.formulae, expected_sizes):
            self.assertEqual(PackageFormula.parse(formula).size, size)

    def test_str(self):
        """
        Verify pretty-printing matches the expected format.
        """
        expected_formulae = [
            normalize_spaces(
                """
            "ocaml" { >= "4.05.0" & < "4.10" } &
            "ocamlfind" { build } &
            "num" &
            "conf-findutils" { build }
            """),
            normalize_spaces(
                """
            "ocaml-config" &
            "ocaml-base-compiler" { = "4.08.1" } |
            "ocaml-variants" { >= "4.08.1" & < "4.08.2~" } |
            "ocaml-system" { >= "4.08.1" & < "4.08.2~" }
            """),
            normalize_spaces(
                """
            "ocaml" { >= "4.05.0" } &
            "dune" { >= "1.4" } &
            "menhir" { >= "20181113" } &
            "ANSITerminal" &
            "fmt" &
            "logs" &
            "mtime" { >= "1.0.0" } &
            "cmdliner" { >= "1.0.0" & < "1.1.0" } &
            "conf-freetype" &
            "conf-pkg-config" &
            "conf-cairo" &
            "cairo2" &
            "yojson" { >= "1.6.0" } &
            "easy-format"
            """),
            normalize_spaces(
                """
            ("ocaml" { >= "4.08" & < "5.0" } |
             ("ocaml" { < "4.08~~" } & "ocamlfind-secondary")) &
            "base-unix" &
            "base-threads"
            """),
            normalize_spaces(
                """
            "odoc-parser" { >= "0.9.0" & < "2.0.0" } &
            "astring" &
            "cmdliner" { >= "1.0.0" } &
            "cppo" { build & >= "1.1.0" } &
            "dune" { >= "2.9.1" } &
            "fpath" &
            "ocaml" { >= "4.02.0" } &
            "result" &
            "tyxml" { >= "4.3.0" } &
            "fmt" &
            "ocamlfind" { with-test } &
            "yojson" { < "2.0.0" & with-test } &
            ("ocaml" { < "4.04.1" & with-test } | "sexplib0" { with-test }) &
            "conf-jq" { with-test } &
            "ppx_expect" { with-test } &
            "bos" { with-test } &
            "bisect_ppx" { dev & > "2.5.0" } &
            ("ocaml" { < "4.03.0" & dev } | "mdx" { dev })
            """),
            # TODO: Fully support filters and uncomment these formulas
            # normalize_spaces("""
            # "ocaml" { = "5.0.0" & post } &
            # "base-unix" { post } &
            # "base-bigarray" { post } &
            # "base-threads" { post } &
            # "base-domains" { post } &
            # "base-nnp" { post } &
            # "ocaml-options-vanilla" { post } &
            # "ocaml-beta" { opam-version < "2.1.0" }
            # """),
            # normalize_spaces("""
            # "ocaml" { >= "4.03.0" } &
            # "dune" { >= "2.8.0" } &
            # "menhirLib" { = version } &
            # "menhirSdk" { = version }
            # """)
        ]
        for formula, expected in zip(self.formulae, expected_formulae):
            self.assertEqual(str(PackageFormula.parse(formula)), expected)


if __name__ == '__main__':
    unittest.main()
