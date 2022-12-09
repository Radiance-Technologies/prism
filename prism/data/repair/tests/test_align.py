"""
Test module for repair tools.
"""
import unittest
from itertools import chain
from pathlib import Path
from typing import Dict, List

from prism.data.build_cache import ProjectCommitData, VernacSentence
from prism.data.extract_cache import VernacCommandData
from prism.data.repair import align_commits_per_file
from prism.language.heuristic.parser import HeuristicParser
from prism.project.metadata import ProjectMetadata
from prism.tests import _COQ_EXAMPLES_PATH


class TestAlign(unittest.TestCase):
    """
    Tests for repair tools.
    """

    caches: Dict[str,
                 List[VernacCommandData]] = {}

    @classmethod
    def setUpClass(cls) -> None:
        """
        Set up some real data to try to align.
        """
        cls.test_metadata = ProjectMetadata("test_align", [], [], [])
        files = ["verdi_core_net_a.v", "verdi_core_net_b.v", "Alphabet.v"]

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
                        None,
                        None))
                for x in HeuristicParser.parse_sentences_from_file(
                    Path(_COQ_EXAMPLES_PATH) / f)
                if x.text.startswith("Lemma") or x.text.startswith("Theorem")
                or x.text.startswith("Definition")
                or x.text.startswith("Inductive")
            ]
            cls.caches[f] = definitions

    def test_align_commits_per_file(self):
        """
        Check that sane alignments are produced on real data.
        """
        a = ProjectCommitData(
            self.test_metadata,
            {"core_net": TestAlign.caches["verdi_core_net_a.v"]},
            None,
            None)
        b = ProjectCommitData(
            self.test_metadata,
            {"core_net": TestAlign.caches["verdi_core_net_b.v"]},
            None,
            None)

        alignment = align_commits_per_file(a, b)

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

    def test_align_commits_per_file_multifile(self):
        """
        Check that file indices are offset correctly.
        """
        a = ProjectCommitData(
            self.test_metadata,
            {
                "Alphabet'.v": TestAlign.caches["Alphabet.v"],
                "core_net": TestAlign.caches["verdi_core_net_a.v"],
                "Alphabet.v": TestAlign.caches["Alphabet.v"]
            },
            None,
            None)
        b = ProjectCommitData(
            self.test_metadata,
            {"core_net": TestAlign.caches["verdi_core_net_b.v"]},
            None,
            None)
        alignment = align_commits_per_file(a, b)

        alines = list(
            chain.from_iterable(
                a.command_data[x] for x in a.command_data.keys()))

        # a needs special treatment because it now consists
        # of multiple files here
        for i, x in enumerate(alines):
            for j, y in enumerate(self.caches["verdi_core_net_b.v"]):
                if (x.command.text == y.command.text):
                    self.assertTrue((i, j) in alignment)


if __name__ == "__main__":
    unittest.main()
