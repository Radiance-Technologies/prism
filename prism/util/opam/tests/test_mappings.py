"""
Test suite for prism.util.opam.
"""
import unittest

from prism.util.opam.mappings import LogicalMappings as LM


class TestLogicalMappings(unittest.TestCase):
    """
    Test suite for `LogicalMappings`.
    """

    def test_concrete(self):
        """
        Test common/expected searches on LogicalMappings.
        """
        self.assertTrue(
            LM.search(prefix="mathcomp",
                      suffix="matrix") == "coq-mathcomp-algebra")
        self.assertTrue(LM.search(suffix="matrix") is None)  # ambiguous
        self.assertTrue(LM.search(suffix="stdpp.namespaces") == "coq-stdpp")


if __name__ == '__main__':
    unittest.main()
