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
