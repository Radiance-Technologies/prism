"""
Tests for the utils module.
"""
import unittest

from coqgym_interface.unknowns import find_and_replace_unrecognized_sequences


class TestUtils(unittest.TestCase):
    """
    Class for testing the utils module.
    """

    def test_replace_unrecognized_sequences(self):
        """
        Ensure this method properly converts unknowns.
        """
        test_in = "foo <unk> bar <unk>"
        test_out = find_and_replace_unrecognized_sequences(test_in)
        self.assertEqual(
            test_out,
            "foo b'\\xff\\xfe<\\x00u\\x00n\\x00k\\x00>\\x00' bar "
            "b'\\xff\\xfe<\\x00u\\x00n\\x00k\\x00>\\x00'")


if __name__ == "__main__":
    unittest.main()
