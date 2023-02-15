"""
Test suite for `prism.data.repair.align`.
"""
import typing
import unittest

from seutil import io

from prism.data.build_cache import ProjectCommitData
from prism.data.repair.align import default_align
from prism.data.repair.diff import compute_git_diff
from prism.data.repair.instance import ProjectCommitDataDiff
from prism.interface.coq.goals import Goal, GoalLocation
from prism.tests import _DATA_PATH


class TestRepairInstance(unittest.TestCase):
    """
    Test suite for repair instances and related classes.
    """

    initial_state: ProjectCommitData
    repaired_state: ProjectCommitData

    def _assert_commit_data_equal(
            self,
            a: ProjectCommitData,
            b: ProjectCommitData) -> None:
        """
        Assert two commits have equivalent text and goals.
        """
        git_diff = compute_git_diff(a, b)
        self.assertEqual(git_diff.text, "")
        # verify goals are equal
        b_sentences = b.sorted_sentences()
        for afile, asentences in a.sorted_sentences().items():
            bsentences = b_sentences[afile]
            for asentence, bsentence in zip(asentences, bsentences):
                if asentence.goals is None:
                    self.assertIsNone(bsentence.goals)
                else:
                    assert bsentence.goals is not None
                    for ag, bg in zip(asentence.goals, bsentence.goals):
                        if isinstance(ag, (Goal, GoalLocation)):
                            # a goal or removed goal
                            self.assertEqual(str(ag), str(bg))
                        else:
                            self.assertIsInstance(bg, tuple)
                            if isinstance(ag[0], Goal):
                                # an added goal
                                self.assertEqual(str(ag[0]), str(bg[0]))
                                self.assertEqual(ag[1], bg[1])
                            else:
                                # a moved goal
                                self.assertEqual(ag, bg)

    def test_ProjectCommitDataDiff(self) -> None:
        """
        Verify that a diff captures the changes between two commits.
        """
        with self.subTest("patch_identity"):
            diff = ProjectCommitDataDiff.from_commit_data(
                self.initial_state,
                self.initial_state,
                default_align)
            self._assert_commit_data_equal(
                diff.patch(self.initial_state),
                self.initial_state)
            self.assertTrue(diff.is_empty)
        diff = ProjectCommitDataDiff.from_commit_data(
            self.initial_state,
            self.repaired_state,
            default_align)
        with self.subTest("patch"):
            patched_state = diff.patch(self.initial_state)
            patched_state.diff_goals()
            self.repaired_state.diff_goals()
            self._assert_commit_data_equal(patched_state, self.repaired_state)

    @classmethod
    def setUpClass(cls) -> None:
        """
        Load realistic sample cached data.
        """
        initial_state = io.load(
            _DATA_PATH / "initial_state.yml",
            clz=ProjectCommitData)
        cls.initial_state = typing.cast(ProjectCommitData, initial_state)
        repaired_state = io.load(
            _DATA_PATH / "repaired_state.yml",
            clz=ProjectCommitData)
        cls.repaired_state = typing.cast(ProjectCommitData, repaired_state)


if __name__ == "__main__":
    unittest.main()
