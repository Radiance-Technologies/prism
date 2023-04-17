"""
Test string escaping and other capabilities of the string module.
"""
import unittest

from prism.util.string import escape


class TestString(unittest.TestCase):
    """
    Tests for prism.util.string functions.
    """

    def test_escape(self):
        """
        Verify that escape function escapes whitespace correctly.
        """
        string_with_weird_whitespace = "a\nb\tasda\\sda\"\'"
        self.assertEqual(
            escape(string_with_weird_whitespace),
            r"""a\nb\tasda\\sda\"\'""")


if __name__ == "__main__":
    unittest.main()
