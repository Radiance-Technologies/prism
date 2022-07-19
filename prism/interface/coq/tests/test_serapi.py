"""
Test suite for `prism.interface.coq.serapi`.
"""
import unittest
from typing import Dict, List

from prism.interface.coq.exception import CoqExn
from prism.interface.coq.serapi import SerAPI
from prism.interface.coq.util import normalize_spaces
from prism.language.heuristic.parser import HeuristicParser
from prism.language.sexp.parser import SexpParser
from prism.tests import _COQ_EXAMPLES_PATH


class TestSerAPI(unittest.TestCase):
    """
    Test suite for the interactive `SerAPI` interface.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Set up some example documents for realistic inputs.
        """
        cls.sentences: Dict[str, List[str]]
        cls.sentences = {}
        for filename in ['simple', 'nested', 'Alphabet']:
            cls.sentences[filename] = HeuristicParser.parse_sentences_from_file(
                _COQ_EXAMPLES_PATH / f"{filename}.v",
                glom_proofs=False)

    def test_execute(self):
        """
        Verify some simple commands can be executed.
        """
        expected_ast = SexpParser.parse(
            """
            (CoqAst
              (
                (
                  (
                    (fname ToplevelInput)
                    (line_nb 1)
                    (bol_pos 0)
                    (line_nb_last 1)
                    (bol_pos_last 0)
                    (bp 0)
                    (ep 17)))
                (VernacExpr ()
                  (VernacLocate
                    (LocateAny
                      (
                        (v
                          (ByNotation
                            (_ ∘ _ ())))
                        (loc
                          (
                            (
                              (fname ToplevelInput)
                              (line_nb 1)
                              (bol_pos 0)
                              (line_nb_last 1)
                              (bol_pos_last 0)
                              (bp 7)
                              (ep 16))))))))))
            """)
        with SerAPI() as serapi:
            responses, _ = serapi.execute("Require Import Coq.Program.Basics.")
            self.assertEqual(str(responses[0]), '(Answer 20 Ack)')
            self.assertEqual(str(responses[1]), '(Answer 20 Completed)')
            responses, _, ast = serapi.execute('Locate "_ ∘ _".', True)
            self.assertEqual(str(responses[0]), '(Answer 23 Ack)')
            self.assertEqual(str(responses[1]), '(Answer 23 Completed)')
            self.assertEqual(SexpParser.parse(ast), expected_ast)

    def test_has_open_goals(self):
        """
        Test detection of proof modes with simple examples.
        """
        simple_sentences = self.sentences['simple']
        with self.subTest("simple"):
            with SerAPI() as serapi:
                self.assertFalse(serapi.has_open_goals())
                serapi.execute(simple_sentences[0])
                self.assertFalse(serapi.has_open_goals())
                serapi.execute(simple_sentences[1])
                self.assertFalse(serapi.is_in_proof_mode)
                serapi.execute(simple_sentences[2])
                self.assertTrue(serapi.has_open_goals())
                self.assertTrue(serapi.is_in_proof_mode)
        nested_sentences = self.sentences['nested']
        with self.subTest("nested"):
            with SerAPI() as serapi:
                self.assertFalse(serapi.has_open_goals())
                serapi.execute(nested_sentences[0])
                self.assertFalse(serapi.has_open_goals())
                serapi.execute(nested_sentences[1])
                self.assertTrue(serapi.is_in_proof_mode)
                for i in range(3):
                    # this includes a mid-proof import
                    serapi.execute(nested_sentences[2 + i])
                    self.assertTrue(serapi.has_open_goals())
                serapi.execute(nested_sentences[5])
                self.assertFalse(serapi.has_open_goals())
                # set nested proofs allowed
                serapi.execute(nested_sentences[6])
                self.assertFalse(serapi.has_open_goals())
                for i in range(8):
                    serapi.execute(nested_sentences[7 + i])
                    self.assertTrue(serapi.is_in_proof_mode)
                serapi.execute(nested_sentences[15])
                self.assertFalse(serapi.is_in_proof_mode)

    def test_multiprocessing(self):
        """
        Verify that multiple SerAPI contexts can be managed at once.
        """
        pass

    def test_query_vernac(self):
        """
        Verify that queries generate feedback.
        """
        with SerAPI() as serapi:
            serapi.execute(
                "Inductive nat : Type := O : nat | S (n : nat) : nat.")
            actual = serapi.query_vernac("Print nat.")
            expected = [
                "Inductive nat : Set :=  O : nat | S : forall _ : nat, nat"
            ]
            self.assertEqual(actual, expected)

    def test_recovery(self):
        """
        Verify that control may be recovered after an exception.
        """
        with SerAPI() as serapi:
            with self.assertRaises(CoqExn):
                serapi.execute("Require Import.")
            try:
                # capture an error message
                serapi.execute("Require Import.")
            except CoqExn as e:
                self.assertEqual(
                    e.msg,
                    "Syntax error: [constr:global] expected after "
                    "[export_token] (in [vernac:gallina_ext]).")
            # verify execution of normal commands is successful
            serapi.execute("Inductive const := C | D.")
            serapi.execute(
                'Definition swap (c : const) := match c with | C => D | D => C end.'
            )
            actual = serapi.query_vernac("Print swap.")
            expected = normalize_spaces(
                """
            swap = fun c : const => match c with
                               | C => D
                                    | D => C
                                    end
                 : forall _ : const, const
            """).strip()
            self.assertEqual(normalize_spaces(actual[0]), expected)


if __name__ == '__main__':
    unittest.main()