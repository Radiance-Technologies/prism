"""
Tests for prism.language.gallina.analyze.SexpAnalyzer.
"""
import unittest

from prism.language.gallina.analyze import ControlFlag, SexpAnalyzer, SexpInfo
from prism.language.gallina.exception import SexpAnalyzingException
from prism.language.gallina.parser import CoqParser
from prism.language.sexp import SexpList, SexpParser, SexpString
from prism.tests import _COQ_EXAMPLES_PATH


class TestSexpAnalyzer(unittest.TestCase):
    """
    Tests for prism.language.gallina.analyze.SexpAnalyzer.
    """

    def test_analyze_vernac(self):
        """
        Verify that control flags and attributes can be extracted.
        """
        with self.subTest("pre-8.11"):
            example_sexp = SexpParser.parse(
                '((v(VernacTime((v(VernacFail((v(VernacExpr((local VernacFlagEmpty))'
                '(VernacExtend(Set_Solver 0)((GenArg raw(ExtraArg tactic)'
                '(TacAtom((v(TacIntroPattern false(((v(IntroForthcoming false))'
                '(loc("[LOC]"))))))(loc("[LOC]")))))))))(loc("[LOC]")))))'
                '(loc("[LOC]")))))(loc("[LOC]")))')
            with self.assertRaises(SexpAnalyzingException):
                # missing bool attribute for VernacTime
                vernac = SexpAnalyzer.analyze_vernac(example_sexp)
            # add the missing bool attribute
            vernac_time: SexpList = example_sexp[0][1]
            vernac_time.children.insert(1, SexpString("false"))
            vernac = SexpAnalyzer.analyze_vernac(example_sexp)
            expected_vernac = SexpInfo.Vernac(
                "VernacExtend",
                "Set_Solver",
                [ControlFlag.Time,
                 ControlFlag.Fail],
                ["local"],
                example_sexp[0][1])
            self.assertEqual(vernac, expected_vernac)
        with self.subTest("post-8.11"):
            example_sexp = SexpParser.parse(
                '((v('
                '(control (ControlTime ControlFail))'
                '(attrs ((local VernacFlagEmpty)))'
                '(expr '
                '(VernacExtend(Set_Solver 0)((GenArg raw(ExtraArg tactic)'
                '(TacAtom((v(TacIntroPattern false(((v(IntroForthcoming false))'
                '(loc("[LOC]"))))))(loc("[LOC]"))))))))))'
                '(loc("[LOC]")))')
            with self.assertRaises(SexpAnalyzingException):
                # missing bool attribute for VernacTime
                vernac = SexpAnalyzer.analyze_vernac(example_sexp)
            # add the missing bool attribute
            control: SexpList = example_sexp[0][1][0][1]
            control.children[0] = SexpList([control[0], SexpString("false")])
            vernac = SexpAnalyzer.analyze_vernac(example_sexp)
            expected_vernac = SexpInfo.Vernac(
                "VernacExtend",
                "Set_Solver",
                [ControlFlag.Time,
                 ControlFlag.Fail],
                ["local"],
                example_sexp[0][1])
            self.assertEqual(vernac, expected_vernac)

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
