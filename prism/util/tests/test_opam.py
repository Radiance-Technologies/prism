"""
Test suite for prism.util.opam.
"""
import re
import unittest
from typing import Dict

from seutil import bash

from prism.util.opam import (
    OpamAPI,
    Version,
    VersionConstraint,
    VersionParseError,
)


class TestVersion(unittest.TestCase):
    """
    Test suite for `Version`.
    """

    def test_compare(self):
        """
        Verify versions are ordered as expected.
        """
        # verify prerelease comes before release
        self.assertLess(Version(8, 10, 2, "pre"), Version(8, 10, 2))
        # verify patch comes after minor release
        self.assertLess(Version(8, 10, None), Version(8, 10, 1))
        self.assertGreater(Version(9, 10, 2), Version(8, 10, 2))
        self.assertLess(Version(8, 9, 2), Version(8, 10, 2))
        self.assertLess(Version(8, 10, 2), Version(8, 10, 3))
        self.assertLess(Version(8, 10, 2), Version(8, 10, 2, extra=""))
        self.assertLess(
            Version(8,
                    10,
                    2,
                    extra="a"),
            Version(8,
                    10,
                    2,
                    extra="b"))
        self.assertLess(Version(8, 10, 2, "a"), Version(8, 10, 2, "b"))

    def test_parse(self):
        """
        Verify that various version strings can be parsed.
        """
        self.assertEqual(Version.parse("8.10.2"), Version(8, 10, 2, None, None))
        self.assertEqual(Version.parse("8.10.2~"), Version(8, 10, 2, "", None))
        self.assertEqual(Version.parse("8.10.2~+"), Version(8, 10, 2, "", ""))
        self.assertEqual(Version.parse("8.10.2+"), Version(8, 10, 2, None, ""))
        self.assertEqual(Version.parse("8.10"), Version(8, 10))
        self.assertEqual(
            Version.parse("8.10+extra"),
            Version(8,
                    10,
                    extra="extra"))
        self.assertEqual(Version.parse("8.10~pre"), Version(8, 10, None, "pre"))
        self.assertEqual(
            Version.parse("8.10~pre+extra"),
            Version(8,
                    10,
                    None,
                    "pre",
                    "extra"))
        self.assertEqual(
            Version.parse("8.10+extra~pre"),
            Version(8,
                    10,
                    None,
                    None,
                    "extra~pre"))
        self.assertEqual(
            Version.parse("8.10.2~pre"),
            Version(8,
                    10,
                    2,
                    "pre",
                    None))
        self.assertEqual(
            Version.parse("8.10.2+extra"),
            Version(8,
                    10,
                    2,
                    None,
                    "extra"))
        self.assertEqual(
            Version.parse("8.10.2~pre+extra"),
            Version(8,
                    10,
                    2,
                    "pre",
                    "extra"))
        self.assertEqual(
            Version.parse("8.10.2+pre~extra"),
            Version(8,
                    10,
                    2,
                    None,
                    "pre~extra"))
        with self.assertRaises(VersionParseError):
            Version.parse(".10.2")
        with self.assertRaises(VersionParseError):
            Version.parse("10")
        with self.assertRaises(VersionParseError):
            Version.parse("8~pre+extra")

    def test_str(self):
        """
        Verify pretty-printing versions matches expectations.
        """
        self.assertEqual(str(Version(8, 10, 2)), "8.10.2")
        self.assertEqual(str(Version(8, 10, 2, "pre")), "8.10.2~pre")
        self.assertEqual(str(Version(8, 10, 2, None, "extra")), "8.10.2+extra")
        self.assertEqual(
            str(Version(8,
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
            Version(8,
                    10,
                    2),
            VersionConstraint(Version(8,
                                      10,
                                      2),
                              Version(8,
                                      10,
                                      2),
                              True,
                              True))
        self.assertNotIn(
            Version(8,
                    10,
                    2),
            VersionConstraint(
                Version(8,
                        10,
                        2),
                Version(8,
                        11,
                        2),
                False,
                True))
        # open bound on a prerelease
        self.assertIn(
            Version(8,
                    10,
                    2),
            VersionConstraint(
                Version(8,
                        10,
                        2,
                        ""),
                Version(8,
                        10,
                        2),
                False,
                True))
        # no constraint
        self.assertIn(Version(123, 123, 43), VersionConstraint())

    def test_parse(self):
        """
        Verify simple constraints can be parsed.
        """
        self.assertEqual(
            VersionConstraint.parse("{ >= 0.7.1 & build & < 1.0.0 }"),
            VersionConstraint(Version(0,
                                      7,
                                      1),
                              Version(1,
                                      0,
                                      0),
                              True,
                              False))
        self.assertEqual(
            VersionConstraint.parse("{ <= 1.0.0 | > 0.7.1+extra }"),
            VersionConstraint(
                Version(0,
                        7,
                        1,
                        extra="extra"),
                Version(1,
                        0,
                        0),
                False,
                True))
        self.assertEqual(
            VersionConstraint.parse("{ > 0.7.1 }"),
            VersionConstraint(Version(0,
                                      7,
                                      1),
                              None,
                              False,
                              False))
        self.assertEqual(
            VersionConstraint.parse("{ < 1.7.1~pre }"),
            VersionConstraint(None,
                              Version(1,
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
                    Version(8,
                            10,
                            2),
                    Version(8,
                            10,
                            2),
                    True,
                    True)),
            "= 8.10.2")
        self.assertEqual(
            str(
                VersionConstraint(
                    Version(8,
                            10,
                            2),
                    Version(8,
                            10,
                            2),
                    False,
                    True)),
            "> 8.10.2 & <= 8.10.2")
        self.assertEqual(
            str(
                VersionConstraint(
                    Version(8,
                            10,
                            2),
                    Version(8,
                            10,
                            2),
                    False,
                    False)),
            "> 8.10.2 & < 8.10.2")
        self.assertEqual(
            str(VersionConstraint(Version(8,
                                          10,
                                          2),
                                  None,
                                  True,
                                  True)),
            ">= 8.10.2")
        self.assertEqual(
            str(VersionConstraint(None,
                                  Version(8,
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
                    Version(4,
                            5,
                            0),
                    Version(4,
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
