"""
Tests for the utils module.
"""
import unittest

from coqgym_interface.unknowns import (
    TokenizerConfiguration,
    find_and_replace_unrecognized_sequences,
)


class TestUtils(unittest.TestCase):
    """
    Class for testing the utils module.
    """

    def test_replace_unrecognized_sequences_bart(self):
        """
        Ensure this function properly converts unknowns.
        """
        test_in = "foo <unk> bar <unk>"
        test_out = find_and_replace_unrecognized_sequences(test_in)
        self.assertEqual(test_out, test_in)

    def test_replace_unrecognized_sequences_bert(self):
        """
        Ensure the function works with the Bert tokenizer.
        """
        test_in = "foo bar ∀A baz"
        tokenizer_config = TokenizerConfiguration.from_name("bert_base_uncased")
        test_out = find_and_replace_unrecognized_sequences(
            test_in,
            tokenizer_config)
        self.assertEqual(test_out, "foo bar \\ensuremath{\\forall}A baz")
        test_in_2 = "foo bar ∀ A baz"
        test_out_2 = find_and_replace_unrecognized_sequences(
            test_in_2,
            tokenizer_config)
        self.assertEqual(test_out_2, "foo bar \\ensuremath{\\forall} A baz")

    def test_rus_bert_with_unlatexable_character(self):
        """
        Make sure the function works to convert unlatexable unknowns.
        """
        test_in = "foo bar 𐡀baz"
        tokenizer_config = TokenizerConfiguration.from_name("bert_base_uncased")
        test_out = find_and_replace_unrecognized_sequences(
            test_in,
            tokenizer_config)
        self.assertEqual(
            test_out,
            r"foo bar b'\xff\xfe\x02\xd8@\xdcb\x00a\x00z\x00'")


if __name__ == "__main__":
    unittest.main()
