"""
Test suite for prism.util.opam.
"""
import unittest

from prism.util.opam import OCamlVersion, VersionConstraint


class TestVersionConstraint(unittest.TestCase):
    """
    Test suite for 'VersionConstraint'.
    """

    def test_apply(self):
        """
        Verify that a list of versions can be reduced to a feasible set.
        """
        lower_bound = OCamlVersion(4, 2)
        upper_bound = OCamlVersion(5, 1, 2)
        vc = VersionConstraint(lower_bound, upper_bound, True, True)
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
        expected = [OCamlVersion.parse(v) for v in expected]
        self.assertEqual(vc.apply(versions), expected)
        object.__setattr__(vc, 'lower_closed', False)
        self.assertEqual(vc.apply(versions), expected[1 :])
        object.__setattr__(vc, 'upper_closed', False)
        self.assertEqual(vc.apply(versions), expected[1 :-1])
        object.__setattr__(vc, 'lower_closed', True)
        self.assertEqual(vc.apply(versions), expected[:-1])
        object.__setattr__(vc, 'lower_bound', None)
        self.assertEqual(
            vc.apply(versions),
            versions[: versions.index(OCamlVersion(5,
                                                   1,
                                                   2))])
        object.__setattr__(vc, 'upper_bound', None)
        self.assertEqual(vc.apply(versions), versions)
        object.__setattr__(vc, 'lower_bound', lower_bound)
        self.assertEqual(
            vc.apply(versions),
            versions[versions.index(OCamlVersion(4,
                                                 2)):])
        with self.subTest("unsorted"):
            versions = set(versions[7 :] + versions[: 7])
            vc = VersionConstraint(lower_bound, upper_bound, True, True)
            self.assertEqual(vc.apply(versions, True), expected)

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


if __name__ == '__main__':
    unittest.main()
