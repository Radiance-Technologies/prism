"""
Test suite for prism.util.opam.
"""
import re
import unittest
from typing import Dict

from seutil import bash

from prism.util.opam import (
    OCamlVersion,
    OpamAPI,
    OpamVersion,
    Version,
    VersionConstraint,
    VersionParseError,
)


class TestVersion(unittest.TestCase):
    """
    Test suite for `OCamlVersion`.
    """

    def test_compare(self):
        """
        Verify versions are ordered as expected.
        """
        # verify prerelease comes before release
        self.assertLess(OCamlVersion(8, 10, 2, "pre"), OCamlVersion(8, 10, 2))
        # verify patch comes after minor release
        self.assertLess(OCamlVersion(8, 10, None), OCamlVersion(8, 10, 1))
        self.assertGreater(OCamlVersion(9, 10, 2), OCamlVersion(8, 10, 2))
        self.assertLess(OCamlVersion(8, 9, 2), OCamlVersion(8, 10, 2))
        self.assertLess(OCamlVersion(8, 10, 2), OCamlVersion(8, 10, 3))
        self.assertLess(
            OCamlVersion(8,
                         10,
                         2),
            OCamlVersion(8,
                         10,
                         2,
                         extra=""))
        self.assertLess(
            OCamlVersion(8,
                         10,
                         2,
                         extra="a"),
            OCamlVersion(8,
                         10,
                         2,
                         extra="b"))
        self.assertLess(
            OCamlVersion(8,
                         10,
                         2,
                         "a"),
            OCamlVersion(8,
                         10,
                         2,
                         "b"))
        self.assertEqual(OpamVersion(['', 8, '.', 10]), OCamlVersion(8, 10))
        self.assertLess(
            OpamVersion(['',
                         8,
                         '.',
                         10,
                         '~pl',
                         1]),
            OCamlVersion(8,
                         10))
        # assert same order as the example at
        # https://opam.ocaml.org/doc/Manual.html#version-ordering.
        versions = [
            '~~',
            '~',
            '~beta2',
            '~beta10',
            '0.1',
            '1.0~beta',
            '1.0',
            '1.0-test',
            '1.0.1',
            '1.0.10',
            'dev',
            'trunk'
        ]
        versions = [OCamlVersion.parse(v) for v in versions]
        for i, v in enumerate(versions):
            self.assertEqual(v, v)
            for j in range(i + 1, len(versions)):
                self.assertLess(v, versions[j])

    def test_init(self):
        """
        Test error checking on direct initialization (i.e., not parsed).
        """
        self.assertEqual(OpamVersion(['', '3']), OpamVersion.parse('3'))
        with self.assertRaises(TypeError):
            OpamVersion([8])
        with self.assertRaises(TypeError):
            OpamVersion(['3'])
        with self.assertRaises(TypeError):
            OpamVersion(['', '3', 'g5'])
        with self.assertRaises(TypeError):
            OpamVersion(['', 8, '.', 10, '~pl1']),

    def test_parse(self):
        """
        Verify that various version strings can be parsed.
        """
        self.assertEqual(
            OCamlVersion.parse("8.10.2"),
            OCamlVersion(8,
                         10,
                         2,
                         None,
                         None))
        self.assertEqual(
            OCamlVersion.parse("8.10.2~"),
            OCamlVersion(8,
                         10,
                         2,
                         "",
                         None))
        self.assertEqual(
            OCamlVersion.parse("8.10.2~+"),
            OCamlVersion(8,
                         10,
                         2,
                         "",
                         ""))
        self.assertEqual(
            OCamlVersion.parse("8.10.2+"),
            OCamlVersion(8,
                         10,
                         2,
                         None,
                         ""))
        self.assertEqual(OCamlVersion.parse("8.10"), OCamlVersion(8, 10))
        self.assertEqual(
            OCamlVersion.parse("8.10+extra"),
            OCamlVersion(8,
                         10,
                         extra="extra"))
        self.assertEqual(
            OCamlVersion.parse("8.10~pre"),
            OCamlVersion(8,
                         10,
                         None,
                         "pre"))
        self.assertEqual(
            OCamlVersion.parse("8.10~pre+extra"),
            OCamlVersion(8,
                         10,
                         None,
                         "pre",
                         "extra"))
        self.assertEqual(
            OCamlVersion.parse("8.10+extra~pre"),
            OCamlVersion(8,
                         10,
                         None,
                         None,
                         "extra~pre"))
        self.assertEqual(
            OCamlVersion.parse("8.10.2~pre"),
            OCamlVersion(8,
                         10,
                         2,
                         "pre",
                         None))
        self.assertEqual(
            OCamlVersion.parse("8.10.2+extra"),
            OCamlVersion(8,
                         10,
                         2,
                         None,
                         "extra"))
        self.assertEqual(
            OCamlVersion.parse("8.10.2~pre+extra"),
            OCamlVersion(8,
                         10,
                         2,
                         "pre",
                         "extra"))
        self.assertEqual(
            OCamlVersion.parse("8.10.2+pre~extra"),
            OCamlVersion(8,
                         10,
                         2,
                         None,
                         "pre~extra"))
        # test fallback to OpamVersion parsing
        self.assertEqual(
            OCamlVersion.parse(".10.2"),
            OpamVersion(['.',
                         10,
                         '.',
                         2]))
        self.assertEqual(OCamlVersion.parse("10"), OpamVersion(['', 10]))
        self.assertEqual(
            OCamlVersion.parse("8~pre+extra"),
            OpamVersion(['',
                         8,
                         '~pre+extra']))
        self.assertEqual(
            OCamlVersion.parse("8.4pl1"),
            OpamVersion(['',
                         8,
                         '.',
                         4,
                         'pl',
                         1]))
        with self.assertRaises(VersionParseError):
            OCamlVersion.parse("dev^9")
        with self.assertRaises(VersionParseError):
            OpamVersion.parse("#build")

    def test_str(self):
        """
        Verify pretty-printing versions matches expectations.
        """
        self.assertEqual(str(OCamlVersion(8, 10, 2)), "8.10.2")
        self.assertEqual(str(OCamlVersion(8, 10, 2, "pre")), "8.10.2~pre")
        self.assertEqual(
            str(OCamlVersion(8,
                             10,
                             2,
                             None,
                             "extra")),
            "8.10.2+extra")
        self.assertEqual(
            str(OCamlVersion(8,
                             10,
                             2,
                             "pre",
                             "extra")),
            "8.10.2~pre+extra")


class TestVersionConstraint(unittest.TestCase):
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
            VersionConstraint(
                OCamlVersion(8,
                             10,
                             2),
                OCamlVersion(8,
                             10,
                             2),
                True,
                True))
        self.assertNotIn(
            OCamlVersion(8,
                         10,
                         2),
            VersionConstraint(
                OCamlVersion(8,
                             10,
                             2),
                OCamlVersion(8,
                             11,
                             2),
                False,
                True))
        # open bound on a prerelease
        self.assertIn(
            OCamlVersion(8,
                         10,
                         2),
            VersionConstraint(
                OCamlVersion(8,
                             10,
                             2,
                             ""),
                OCamlVersion(8,
                             10,
                             2),
                False,
                True))
        # no constraint
        self.assertIn(OCamlVersion(123, 123, 43), VersionConstraint())

    def test_parse(self):
        """
        Verify simple constraints can be parsed.
        """
        self.assertEqual(
            VersionConstraint.parse("{ >= 0.7.1 & build & < 1.0.0 }"),
            VersionConstraint(
                OCamlVersion(0,
                             7,
                             1),
                OCamlVersion(1,
                             0,
                             0),
                True,
                False))
        self.assertEqual(
            VersionConstraint.parse("{ <= 1.0.0 | > 0.7.1+extra }"),
            VersionConstraint(
                OCamlVersion(0,
                             7,
                             1,
                             extra="extra"),
                OCamlVersion(1,
                             0,
                             0),
                False,
                True))
        self.assertEqual(
            VersionConstraint.parse("{ > 0.7.1 }"),
            VersionConstraint(OCamlVersion(0,
                                           7,
                                           1),
                              None,
                              False,
                              False))
        self.assertEqual(
            VersionConstraint.parse("{ < 1.7.1~pre }"),
            VersionConstraint(None,
                              OCamlVersion(1,
                                           7,
                                           1,
                                           "pre"),
                              False,
                              False))

    def test_str(self):
        """
        Verify pretty-printing matches the expected format.
        """
        self.assertEqual(str(VersionConstraint()), "")
        self.assertEqual(
            str(
                VersionConstraint(
                    OCamlVersion(8,
                                 10,
                                 2),
                    OCamlVersion(8,
                                 10,
                                 2),
                    True,
                    True)),
            "= 8.10.2")
        self.assertEqual(
            str(
                VersionConstraint(
                    OCamlVersion(8,
                                 10,
                                 2),
                    OCamlVersion(8,
                                 10,
                                 2),
                    False,
                    True)),
            "> 8.10.2 & <= 8.10.2")
        self.assertEqual(
            str(
                VersionConstraint(
                    OCamlVersion(8,
                                 10,
                                 2),
                    OCamlVersion(8,
                                 10,
                                 2),
                    False,
                    False)),
            "> 8.10.2 & < 8.10.2")
        self.assertEqual(
            str(VersionConstraint(OCamlVersion(8,
                                               10,
                                               2),
                                  None,
                                  True,
                                  True)),
            ">= 8.10.2")
        self.assertEqual(
            str(VersionConstraint(None,
                                  OCamlVersion(8,
                                               10,
                                               2),
                                  True,
                                  False)),
            "< 8.10.2")


class TestOpamAPI(unittest.TestCase):
    """
    Test suite for `OpamAPI`.
    """

    def test_get_available_versions(self):
        """
        Test retrieval of available versions for a single package.

        Indirectly test by comparing a pretty-printed version of the
        retrieved versions with the command-line output.
        """
        pkg = 'ocaml'
        r = bash.run(f"opam show -f all-versions {pkg}")
        r.check_returncode()
        expected = re.sub(r"\s+", " ", r.stdout).strip()
        actual = OpamAPI.get_available_versions(pkg)
        self.assertIsInstance(actual[0], Version)
        self.assertEqual(" ".join(str(v) for v in actual), expected)

    def test_get_dependencies(self):
        """
        Test retrieval of dependencies for a single package.
        """
        actual = OpamAPI.get_dependencies("coq", "8.10.2")
        expected: Dict[str, VersionConstraint]
        expected = {
            "ocaml":
                VersionConstraint(
                    OCamlVersion(4,
                                 '05',
                                 0),
                    OCamlVersion(4,
                                 10),
                    True,
                    False),
            "ocamlfind":
                VersionConstraint(),
            "num":
                VersionConstraint(),
            "conf-findutils":
                VersionConstraint()
        }
        self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()
