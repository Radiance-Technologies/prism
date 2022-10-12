"""
Test suite for Coq/SerAPI-related regular expressions.
"""

import unittest

from prism.interface.coq.re_patterns import (
    IDENT_PATTERN,
    NAMED_DEF_ASSUM_PATTERN,
    NEW_IDENT_PATTERN,
    OBLIGATION_ID_PATTERN,
    PRINT_ALL_IDENT_PATTERN,
)


class TestRegExPatterns(unittest.TestCase):
    """
    Test suite for Coq/SerAPI--related regular expressions.
    """

    def test_ident_pattern(self):
        """
        Test ident parsing for a number of diverse examples.
        """
        self.assertIsNotNone(IDENT_PATTERN.fullmatch("A"))
        self.assertIsNotNone(IDENT_PATTERN.fullmatch("a'"))
        self.assertIsNotNone(IDENT_PATTERN.fullmatch("_0"))
        self.assertIsNotNone(IDENT_PATTERN.fullmatch("a_"))
        self.assertIsNotNone(
            IDENT_PATTERN.fullmatch("test_ident'\u00A0test_ident"))
        self.assertIsNone(IDENT_PATTERN.match("'a"))
        self.assertIsNone(IDENT_PATTERN.match("0a"))
        self.assertIsNone(IDENT_PATTERN.match('\u16ee'))
        self.assertIsNotNone(IDENT_PATTERN.fullmatch('a0\u16ee'))

    def test_named_def_assum_pattern(self):
        """
        Verify that the regex matches the expected syntax.
        """
        self.assertIsNotNone(
            NAMED_DEF_ASSUM_PATTERN.fullmatch("*** [ A : Set ]"))
        self.assertIsNone(NAMED_DEF_ASSUM_PATTERN.match("A : Set"))

    def test_new_ident_pattern(self):
        """
        Verify detection of each way a new identifier may be declared.
        """
        ident = "test_ident'\u00A0test_ident"
        canaries = [
            "is defined",
            "is declared",
            "are defined",
            "is recursively defined",
            "is corecursively defined",
            "are recursively defined",
            "are corecursively defined",
            "is redefined",
            "started"
        ]
        for canary in canaries:
            match = NEW_IDENT_PATTERN.match(' '.join([ident, canary]))
            self.assertIsNotNone(match)
            self.assertEqual(ident, match.groupdict()['idents'].strip())

    def test_print_all_ident_pattern(self):
        """
        Test detection of a variety of identifiers in realistic output.
        """
        lines = [
            " >>>>>>> Library SerTop",
            "Inductive seq : forall _ : nat, Set :=",
            "    niln : seq O | consn : forall (n _ : nat) (_ : seq n), seq (S n)",
            "",
            "For seq: Argument scope is [nat_scope]",
            "For consn: Argument scopes are [nat_scope nat_scope _]",
            "seq_rect : ",
            "forall (P : forall (n : nat) (_ : seq n), Type) (_ : P O niln)",
            "  (_ : forall (n n0 : nat) (s : seq n) (_ : P n s), P (S n) (consn n n0 s))",  # noqa: B950
            "  (n : nat) (s : seq n), P n s",
            "seq_ind : ",
            "forall (P : forall (n : nat) (_ : seq n), Prop) (_ : P O niln)",
            "  (_ : forall (n n0 : nat) (s : seq n) (_ : P n s), P (S n) (consn n n0 s))",  # noqa: B950
            "  (n : nat) (s : seq n), P n s",
            "seq_rec : ",
            "forall (P : forall (n : nat) (_ : seq n), Set) (_ : P O niln)",
            "  (_ : forall (n n0 : nat) (s : seq n) (_ : P n s), P (S n) (consn n n0 s))",  # noqa: B950
            "  (n : nat) (s : seq n), P n s",
            "seq_sind : ",
            "forall (P : forall (n : nat) (_ : seq n), SProp) (_ : P O niln)",
            "  (_ : forall (n n0 : nat) (s : seq n) (_ : P n s), P (S n) (consn n n0 s))",  # noqa: B950
            "  (n : nat) (s : seq n), P n s",
            "length : forall (n : nat) (_ : seq n), nat",
            "m : Set",
            "length_corr : forall (n : nat) (s : seq n), @eq nat (length n s) n",
            "b2Prop : forall _ : bool, Prop",
            "A : "
        ]
        expected_matches = [
            'SerTop',
            'seq',
            None,
            None,
            None,
            None,
            'seq_rect',
            None,
            None,
            None,
            'seq_ind',
            None,
            None,
            None,
            'seq_rec',
            None,
            None,
            None,
            'seq_sind',
            None,
            None,
            None,
            'length',
            'm',
            'length_corr',
            'b2Prop',
            'A'
        ]
        for line, expected in zip(lines, expected_matches):
            match = PRINT_ALL_IDENT_PATTERN.match(line)
            if expected is None:
                self.assertIsNone(match)
            else:
                self.assertIsNotNone(match)
                actual = [
                    v for v in match.groupdict().values() if v is not None
                ]
                self.assertEqual(len(actual), 1)
                actual = actual.pop()
                self.assertEqual(actual, expected)

    def test_obligation_id_pattern(self):
        """
        Verify that a proof ID may be extracted from an obligation ID.
        """
        self.assertIsNone(OBLIGATION_ID_PATTERN.match("f_obligation_"))
        match = OBLIGATION_ID_PATTERN.fullmatch("f_obligation_0")
        self.assertIsNotNone(match)
        self.assertEqual(match.groupdict()['proof_id'], 'f')


if __name__ == '__main__':
    unittest.main()
