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
