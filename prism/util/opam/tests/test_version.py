"""
Test suite for prism.util.opam.
"""
import unittest

from prism.util.opam import OCamlVersion, OpamVersion, ParseError, Version


class TestVersion(unittest.TestCase):
    """
    Test suite for `Version`.
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

    def test_filter_versions(self):
        """
        Verify that a list may be filtered by a version.
        """
        versions = [
            '0.1.2',
            '0.1.1',
            '1.0',
            '1.0~pre',
            '1.0.0',
            '1.0',
            '2',
            '0.99',
            '1'
        ]
        versions = [Version.parse(v) for v in versions]
        self.assertEqual(
            Version.parse('1.0').filter_versions(versions),
            [versions[2],
             versions[5]])
        self.assertEqual(
            Version.parse('1.0~pre').filter_versions(versions),
            [versions[3]])
        self.assertEqual(Version.parse('3').filter_versions(versions), [])

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
        with self.assertRaises(ParseError):
            OCamlVersion.parse("dev^9")
        with self.assertRaises(ParseError):
            OpamVersion.parse("#build")
        self.assertEqual(OCamlVersion.parse("3"), OpamVersion(['', '3']))
        self.assertEqual(
            OCamlVersion.parse("20181113"),
            OpamVersion(['',
                         '20181113']))

    def test_serialization(self):
        """
        Verify that versions can be serialized and deserialized.
        """
        version = OCamlVersion.parse("8.4pl1")
        serialized = version.serialize()
        self.assertEqual(
            serialized,
            f"{OpamVersion.__module__},OpamVersion,8.4pl1")
        deserialized = Version.deserialize(serialized)
        self.assertEqual(version, deserialized)

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


if __name__ == '__main__':
    unittest.main()
