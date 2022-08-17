"""
Tests for prism.language.gallina.analyze.SexpAnalyzer.
"""
import unittest

from prism.interface.coq.serapi import SerAPI
from prism.language.gallina.analyze import SexpAnalyzer
from prism.language.gallina.parser import CoqParser
from prism.project.base import Project
from prism.tests import _COQ_EXAMPLES_PATH


class TestSexpAnalyzer(unittest.TestCase):
    """
    Tests for prism.language.gallina.analyze.SexpAnalyzer.
    """

    def test_is_vernac(self):
        """
        Test SexpAnalyzer.is_vernac class method.
        """
        simple_file = _COQ_EXAMPLES_PATH / "simple.v"
        doc = CoqParser.parse_document(str(simple_file))
        doc.project_path = _COQ_EXAMPLES_PATH
        sentences = Project.extract_sentences(doc, glom_proofs=False)
        # sexps = CoqParser.parse_asts(str(simple_file))
        with SerAPI() as serapi:
            for sentence in sentences:
                sexp = serapi.query_ast(sentence)
                if SexpAnalyzer.is_ltac(sexp):
                    print(sentence)


if __name__ == "__main__":
    unittest.main()
