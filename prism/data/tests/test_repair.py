"""
Test module for repair tools.
"""
import unittest
from pathlib import Path

from prism.data.build_cache import ProjectCommitData, VernacSentence
from prism.data.extract_cache import VernacCommandData
from prism.data.repair.align import align_commits
from prism.language.heuristic.parser import HeuristicParser
from prism.tests import _COQ_EXAMPLES_PATH


class TestRepair(unittest.TestCase):
    """
    Tests for repair tools.
    """

    caches = {}

    @classmethod
    def setUpClass(cls) -> None:
        """
        Set up some real data to try to align.
        """
        files = ["verdi_core_net_a.v", "verdi_core_net_b.v"]
        print(_COQ_EXAMPLES_PATH)

        for f in files:
            # grab a small representative set of lines
            definitions = [
                VernacCommandData(
                    None,
                    None,
                    VernacSentence(
                        x.text.split(":=")[0]
                        if x.text.startswith("Definition")
                        or x.text.startswith("Inductive") else x.text,
                        None,
                        None,
                        None))
                for x in HeuristicParser.parse_sentences_from_file(
                    Path(_COQ_EXAMPLES_PATH) / f)
                if x.text.startswith("Lemma") or x.text.startswith("Theorem")
                or x.text.startswith("Definition")
                or x.text.startswith("Inductive")
            ]
            cls.caches[f] = definitions

    def test_align(self):
        """
        Check that align_commits produces sane alignments on real data.
        """
        a = ProjectCommitData(
            None,
            {"core_net": TestRepair.caches["verdi_core_net_a.v"]},
            None,
            None)
        b = ProjectCommitData(
            None,
            {"core_net": TestRepair.caches["verdi_core_net_b.v"]},
            None,
            None)

        alignment = align_commits(a, b)

        # alignments are heuristic.
        # there's only a couple formal metrics we can test.
        # if you want to look evaluate the alignment, as a human,
        # try the following code.
        """
        for x,y in alignment:
            print("*** matched these theorems *** ",x,y)
            print("" if x is None else
                a.command_data["core_net"][x].command.text)
            print("" if y is None else
                b.command_data["core_net"][y].command.text)
        """

        # probably all exactly matching strings are
        # exactly matched in the alignment
        # unless there are Very Extenuating Circumstances
        for i, x in enumerate(self.caches["verdi_core_net_a.v"]):
            for j, y in enumerate(self.caches["verdi_core_net_b.v"]):
                if (x.command.text == y.command.text):
                    self.assertTrue((i, j) in alignment)


if __name__ == "__main__":
    unittest.main()
