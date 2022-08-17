"""
Tests for prism.language.gallina.analyze.SexpAnalyzer.
"""
import unittest

from prism.language.gallina.analyze import SexpAnalyzer
from prism.language.gallina.parser import CoqParser
from prism.tests import _COQ_EXAMPLES_PATH


class TestSexpAnalyzer(unittest.TestCase):
    """
    Tests for prism.language.gallina.analyze.SexpAnalyzer.
    """

    def test_is_ltac(self):
        """
        Test SexpAnalyzer.is_vernac class method.
        """
        simple_file = _COQ_EXAMPLES_PATH / "simple.v"
        doc = CoqParser.parse_document(str(simple_file))
        doc.project_path = _COQ_EXAMPLES_PATH
        proof_sentences = []
        actual_proof_sentences = [
            "intros n s.",
            "Proof.",
            "induction s...",
            "-",
            "trivial.",
            "-",
            "+",
            "{",
            "*",
            "{",
            "{",
            "simpl.",
            "rewrite IHs; reflexivity...",
            "}",
            "}",
            "}"
        ]
        for vernac_sentence, ast in zip(doc.sentences, doc.ast_sexp_list):
            if SexpAnalyzer.is_ltac(ast):
                proof_sentences.append(str(vernac_sentence))
        self.assertEqual(proof_sentences, actual_proof_sentences)


if __name__ == "__main__":
    unittest.main()
