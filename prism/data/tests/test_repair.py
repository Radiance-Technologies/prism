"""
Test module for repair tools.
"""
import time
import unittest
from copy import copy, deepcopy
from typing import List, Optional

from prism.data.commit_map import (
    Except,
    ProjectCommitMapper,
    ProjectCommitUpdateMapper,
)
from prism.project.repo import ProjectRepo
from prism.tests.factories import DatasetFactory
from prism.util.identity import Identity
from prism.data.repair.align import align_commits, file_alignment, normalized_string_alignment
from prism.language.heuristic.parser import HeuristicParser
from prism.tests import _COQ_EXAMPLES_PATH, _PROJECT_EXAMPLES_PATH
from prism.data.build_cache import VernacSentence, ProjectCommitData
from prism.data.extract_cache import VernacCommandData
from pathlib import Path


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
        files = ["verdi_core_net_a.v","verdi_core_net_b.v"]
        print(_COQ_EXAMPLES_PATH)
    
        for f in files:
            # grab a small representative set of lines
            # include some definitions because those actually changed btween commits
            definitions = [
                VernacSentence(x.text.split(":=")[0] if x.text.startswith("Definition") or x.text.startswith("Inductive") else x.text,None,None,None)
                for x in HeuristicParser.parse_sentences_from_file(Path(_COQ_EXAMPLES_PATH)/f)
                if x.text.startswith("Lemma") or x.text.startswith("Theorem")
                or x.text.startswith("Definition") or x.text.startswith("Inductive")
            ]
            # not actually a file scrape, but good enough for our purposes
            fake_cache = [VernacCommandData(None,None,x) for x in definitions]
            cls.caches[f] = fake_cache

    def test_align(self):
        """
        Check that align_commits produces sane alignments on real data.
        """
        a = ProjectCommitData(None,{"core_net":TestRepair.caches["verdi_core_net_a.v"]},None,None)
        b = ProjectCommitData(None,{"core_net":TestRepair.caches["verdi_core_net_b.v"]} ,None,None)

        alignment = align_commits(a,b)
       
        # alignments are heuristic.
        # there's only a couple formal metrics we can test.
        # if you want to look at the alignment, as a human,
        # try the following code.
        """ 
        for x,y in alignment:
            print("*** matched these theorems *** ",x,y,
                normalized_string_alignment(a.command_data["core_net"][x].command.text,b.command_data["core_net"][y].command.text)
                if x and y else "")
            print("" if x is None else a.command_data["core_net"][x].command.text)
            print("" if y is None else b.command_data["core_net"][y].command.text)
        """

        # probably all exactly matching strings are exactly matched in the alignment
        # unless there are Very Extenuating Circumstances
        for i,x in enumerate(self.caches["verdi_core_net_a.v"]):
            for j,y in enumerate(self.caches["verdi_core_net_b.v"]):
                if (x.command.text == y.command.text):
                    self.assertTrue((i,j) in alignment)

        
    
if __name__ == "__main__":
    unittest.main()
