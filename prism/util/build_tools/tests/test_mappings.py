"""
Test suite for prism.util.opam.
"""
import unittest

from prism.util.build_tools.mappings import LogicalMappings as LM


class TestLogicalMappings(unittest.TestCase):
    """
    Test suite for `LogicalMappings`.
    """

    def test_concrete(self):
        """
        Test common/expected searches on LogicalMappings.
        """
        self.assertEqual(
            LM.opam.search(prefix="mathcomp",
                           suffix="matrix"),
            {"coq-mathcomp-algebra"})
        self.assertGreater(len(LM.opam.search(suffix="matrix")), 1)  # ambiguous
        self.assertEqual(
            LM.opam.search(suffix="stdpp.namespaces"),
            {"coq-stdpp"})


if __name__ == '__main__':
    unittest.main()
