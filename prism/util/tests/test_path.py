"""
Test suite for `prism.util.path`.
"""

import os
import unittest
from pathlib import Path

from prism.util.path import (
    append_suffix,
    pop_suffix,
    with_suffixes,
    without_suffixes,
)


class TestPath(unittest.TestCase):
    """
    Test various path manipulation functions.
    """

    def setUp(self) -> None:
        """
        Define simple paths shared between multiple tests.
        """
        self.path = "test.1.2.3.4.5.6.7.a.b.c"
        self.dir_path = os.path.join("test", "test.1.2.3.4.5.6.7.a.b.c")

    def test_append_suffix(self) -> None:  # noqa: D102
        for p in [self.path, self.dir_path]:
            self.assertEqual(append_suffix(p, ".d"), Path(p + ".d"))

    def test_without_suffixes(self) -> None:  # noqa: D102
        self.assertEqual(without_suffixes(self.path), Path("test"))
        self.assertEqual(without_suffixes(self.dir_path), Path("test") / "test")
        self.assertEqual(without_suffixes("test"), Path("test"))

    def test_with_suffixes(self) -> None:  # noqa: D102
        self.assertEqual(
            with_suffixes(self.path,
                          [".d",
                           ".e",
                           ".f"]),
            Path("test.d.e.f"))
        self.assertEqual(
            with_suffixes(self.dir_path,
                          [".h",
                           ".i",
                           ".j"]),
            Path("test") / "test.h.i.j")

    def test_pop_suffix(self) -> None:  # noqa: D102
        self.assertEqual(
            pop_suffix(pop_suffix(self.path)),
            Path("test.1.2.3.4.5.6.7.a"))
        self.assertEqual(
            pop_suffix(pop_suffix(self.dir_path)),
            Path("test") / "test.1.2.3.4.5.6.7.a")


if __name__ == '__main__':
    unittest.main()
