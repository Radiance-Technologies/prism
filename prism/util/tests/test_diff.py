"""
Test suite for `prism.util.diff`.
"""
import unittest
from textwrap import dedent

from prism.util.diff import Change, GitDiff


class TestGitDiff(unittest.TestCase):
    """
    Test suite for Git diff representations.
    """

    def test_parse_changes(self):
        """
        Verify that changes of various types can be correctly parsed.
        """
        diff = dedent(
            """
        rename from old/file.py
        rename to new/file.py
        --- /dev/null
        +++ b/new/file.py
        @@ -0,0 +0,4 @@
        +'''Module docstring'''
        +
        +def f(x : int) -> int:
        +    return x
        --- a/old/file.py
        +++ /dev/null
        @@ -0,4 +0,0 @@
        -'''Module docstring'''
        -
        -def f(x : int) -> int:
        -    return x
        --- a/changed/file.py
        +++ b/changed/file.py
        @@ -0 +0 @@
        -'''Module docstring'''
        +'''Altered module docstring'''
        @@ -2,2 +2,3 @@
        -def f(x : int) -> int:
        -    return x
        +def g(x : int) -> int:
        +    y = x
        +    return y
        """).strip()
        expected_changes = [
            Change("old/file.py",
                   "new/file.py"),
            Change(
                None,
                "new/file.py",
                range(0,
                      0),
                range(0,
                      4),
                [],
                [
                    "'''Module docstring'''",
                    "",
                    "def f(x : int) -> int:",
                    "    return x"
                ]),
            Change(
                "old/file.py",
                None,
                range(0,
                      4),
                range(0,
                      0),
                [
                    "'''Module docstring'''",
                    "",
                    "def f(x : int) -> int:",
                    "    return x"
                ],
                []),
            Change(
                "changed/file.py",
                "changed/file.py",
                range(0,
                      1),
                range(0,
                      1),
                ["'''Module docstring'''"],
                ["'''Altered module docstring'''"]),
            Change(
                "changed/file.py",
                "changed/file.py",
                range(2,
                      4),
                range(2,
                      5),
                ["def f(x : int) -> int:",
                 "    return x"],
                ["def g(x : int) -> int:",
                 "    y = x",
                 "    return y"]),
        ]
        git_diff = GitDiff(diff)
        self.assertEqual(git_diff.changes, expected_changes)
        with self.subTest("Change.__str__"):
            reconstructed_diff = [str(c) for c in expected_changes]
            # remove redundant --- +++ header
            reconstructed_diff[-1] = "\n".join(
                reconstructed_diff[-1].splitlines()[2 :])
            reconstructed_diff = "\n".join(reconstructed_diff)
            self.assertEqual(diff, reconstructed_diff)


if __name__ == '__main__':
    unittest.main()
