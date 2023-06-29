"""
Test module for repair tools.
"""
import typing
import unittest
from pathlib import Path
from typing import Dict, List

import numpy as np

from prism.data.cache.command_types import (
    VernacCommandData,
    VernacCommandDataList,
    VernacSentence,
)
from prism.data.cache.project_types.project import ProjectCommitData
from prism.data.repair import align_commits, align_commits_per_file
from prism.data.repair.diff import compute_git_diff
from prism.language.gallina.analyze import SexpInfo
from prism.language.heuristic.parser import CoqSentence, HeuristicParser
from prism.project.metadata import ProjectMetadata
from prism.tests import _COQ_EXAMPLES_PATH
from prism.util.diff import GitDiff


class TestAlign(unittest.TestCase):
    """
    Tests for repair tools.
    """

    caches: Dict[str,
                 VernacCommandDataList] = {}
    test_metadata: ProjectMetadata

    @classmethod
    def setUpClass(cls) -> None:
        """
        Set up some real data to try to align.
        """
        cls.test_metadata = ProjectMetadata("test_align", [], [], [])
        files = [
            "verdi_core_net_a.v",
            "verdi_core_net_b.v",
            "Alphabet.v",
            "simple.v"
        ]

        for f in files:
            # grab a small representative set of lines
            definitions = [
                VernacCommandData(
                    [],
                    None,
                    VernacSentence(
                        x.text,
                        # AST is not used, don't worry about Nones
                        str(x.ast),
                        [],
                        typing.cast(SexpInfo.Loc,
                                    x.location).rename("core_net")
                        if f.startswith("verdi") else typing.cast(
                            SexpInfo.Loc,
                            x.location),
                        # heuristic command type; won't work with
                        # attributes
                        x.text.split()[0]))
                for x in typing.cast(
                    List[CoqSentence],
                    HeuristicParser.parse_sentences_from_file(
                        Path(_COQ_EXAMPLES_PATH) / f,
                        return_locations=True,
                        glom_proofs=False,
                        project_path=Path(_COQ_EXAMPLES_PATH)))
                if x.text.startswith("Lemma") or x.text.startswith("Theorem")
                or x.text.startswith("Definition")
                or x.text.startswith("Inductive")
            ]
            cls.caches[f] = VernacCommandDataList(definitions)

    def assertEqualIdentifiersInAlignment(
            self,
            a: ProjectCommitData,
            b: ProjectCommitData,
            alignment: np.ndarray) -> None:
        """
        Assert that equivalently identified commands are aligned.
        """
        for i, (_, x) in enumerate(a.commands):
            for j, (_, y) in enumerate(b.commands):
                x_identifier = x.command.text.split(":=")[0]
                y_identifier = y.command.text.split(":=")[0]
                if x_identifier == y_identifier:
                    self.assertTrue((i, j) in alignment)

    def test_align_commits_per_file(self):
        """
        Check that sane alignments are produced on real data.
        """
        a = ProjectCommitData(
            self.test_metadata,
            {"core_net": TestAlign.caches["verdi_core_net_a.v"]},
            None,
            None,
            None,
            None)
        b = ProjectCommitData(
            self.test_metadata,
            {"core_net": TestAlign.caches["verdi_core_net_b.v"]},
            None,
            None,
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
            None,
            None,
            None)
        b = ProjectCommitData(
            self.test_metadata,
            {"core_net": TestAlign.caches["verdi_core_net_b.v"]},
            None,
            None,
            None,
            None)
        alignment = align_commits_per_file(a, b)
        self.assertEqualIdentifiersInAlignment(a, b, alignment)

    def test_align_commits(self):
        """
        Verify that alignments can be constrained to diffs.
        """
        a = ProjectCommitData(
            self.test_metadata,
            {
                "simple.v": TestAlign.caches["simple.v"],
                "core_net": TestAlign.caches["verdi_core_net_a.v"],
                "Alphabet.v": TestAlign.caches["Alphabet.v"]
            },
            None,
            None,
            None,
            None)
        b = ProjectCommitData(
            self.test_metadata,
            {"core_net": TestAlign.caches["verdi_core_net_b.v"]},
            None,
            None,
            None,
            None)
        diff = GitDiff("")
        with self.assertRaises(ValueError):
            align_commits(a, b, diff, align_commits_per_file)
        diff = compute_git_diff(a, b)
        alignment = align_commits(a, b, diff, align_commits_per_file)
        self.assertEqualIdentifiersInAlignment(a, b, alignment)


if __name__ == "__main__":
    unittest.main()
