"""
Tests for prism.language.gallina.analyze.SexpAnalyzer.
"""
import unittest

from prism.language.gallina.analyze import SexpAnalyzer
from prism.language.gallina.parser import CoqParser
from prism.language.sexp import SexpParser
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
            "}",
            "Qed."
        ]
        for vernac_sentence, ast in zip(doc.sentences, doc.ast_sexp_list):
            if SexpAnalyzer.is_ltac(ast):
                proof_sentences.append(str(vernac_sentence))
        self.assertEqual(proof_sentences, actual_proof_sentences)
        example_sexp = SexpParser.parse(
            '((v(VernacExpr((local VernacFlagEmpty))'
            '(VernacExtend(Set_Solver 0)((GenArg raw(ExtraArg tactic)'
            '(TacAtom((v(TacIntroPattern false(((v(IntroForthcoming false))'
            '(loc("[LOC]"))))))(loc("[LOC]")))))))))(loc("[LOC]")))')
        self.assertFalse(SexpAnalyzer.is_ltac(example_sexp))


if __name__ == "__main__":
    unittest.main()
