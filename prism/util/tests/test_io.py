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
Tests for the util.io module.
"""

import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from prism.util.io import atomic_write
from prism.util.path import append_suffix
from prism.util.serialize import Serializable


@dataclass
class ExampleSerializable(Serializable):
    """
    Really simple serializable subclass for testing atomic_write.
    """

    attr_a: int
    attr_b: str


class TestAtomicWrite(unittest.TestCase):
    """
    Tests for the atomic_write function.
    """

    def test_atomic_write_str(self):
        """
        Verify uncompressed strings get written correctly.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            test_string = "abc\ndef"
            test_filename = Path(tmpdir) / "test.txt"
            atomic_write(test_filename, test_string)
            with open(test_filename, "rt") as f:
                actual_file_contents = f.read()
                self.assertEqual(test_string, actual_file_contents)

    def test_atomic_write_serializable(self):
        """
        Verify uncompressed serializables get written correctly.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            test_object = ExampleSerializable(123, "abc")
            test_filename = Path(tmpdir) / "test.yml"
            atomic_write(test_filename, test_object)
            actual_file_contents = ExampleSerializable.load(test_filename)
            self.assertEqual(test_object, actual_file_contents)
            self.assertFalse(append_suffix(test_filename, '.gz').exists())
            self.assertTrue(test_filename.exists())

    def test_atomic_write_serializable_compressed(self):
        """
        Verify compressed serializables get written correctly.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            test_object = ExampleSerializable(123, "abc")
            test_filename = Path(tmpdir) / "test.yml"
            atomic_write(
                test_filename,
                test_object,
                use_gzip_compression_for_serializable=True)
            actual_file_contents = ExampleSerializable.load(test_filename)
            self.assertEqual(test_object, actual_file_contents)
            self.assertTrue(append_suffix(test_filename, '.gz').exists())
            self.assertFalse(test_filename.exists())


if __name__ == "__main__":
    unittest.main()
