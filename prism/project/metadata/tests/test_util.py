"""
Test suite for `prism.project.util`.
"""
import unittest

from prism.project.util import extract_name


class TestUtil(unittest.TestCase):
    """
    Test suite for common project utility functions.
    """

    def test_extract_name(self):
        """
        Verify project name extraction works for URLs and paths.
        """
        self.assertEqual(
            "CompCert",
            extract_name("https://github.com/AbsInt/CompCert"))
        # with extension
        self.assertEqual(
            "CompCert",
            extract_name("https://github.com/AbsInt/CompCert.git"))
        self.assertEqual("CompCert", extract_name("path/to/AbsInt/CompCert"))


if __name__ == '__main__':
    unittest.main()
