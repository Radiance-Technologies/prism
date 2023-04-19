"""
Test suite for `prism.data.repair.align`.
"""
import unittest
from functools import partial
from typing import Optional

import pytest

from prism.data.build_cache import ProjectCommitData, VernacCommandData
from prism.data.repair.align import default_align
from prism.data.repair.diff import compute_git_diff
from prism.data.repair.instance import (
    GitRepairInstance,
    ProjectCommitDataDiff,
    ProjectCommitDataErrorInstance,
    ProjectCommitDataRepairInstance,
    ProjectStateDiff,
)
from prism.interface.coq.goals import Goal, GoalLocation
from prism.tests import _DATA_PATH


class TestRepairInstance(unittest.TestCase):
    """
    Test suite for repair instances and related classes.
    """

    initial_state: ProjectCommitData
    repaired_state: ProjectCommitData
    compressed_repair_instance: GitRepairInstance
    diff: Optional[ProjectCommitDataDiff]

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

    @pytest.mark.dependency()
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
        self.diff = diff

    @pytest.mark.dependency(
        depends=["TestRepairInstance::test_ProjectCommitDataDiff"])
    def test_mine_repair_examples_from_successful_commits(self) -> None:
        """
        Verify that a repair example can be mined from a commit pair.
        """
        num_mined = 0

        def filter_one(command: VernacCommandData) -> bool:
            """
            Make a filter that allows us to mine one repaired proof.
            """
            nonlocal num_mined
            is_proof = command.command_type == "VernacStartTheoremProof"
            allow = num_mined < 1 and is_proof
            if allow:
                num_mined += 1
            return allow

        # mine one changeset
        mine_one = partial(
            ProjectCommitDataErrorInstance.default_changeset_miner,
            error_filter=filter_one)

        if self.diff is None:
            self.diff = ProjectCommitDataDiff.from_commit_data(
                self.initial_state,
                self.repaired_state,
                default_align)

        repairs = ProjectCommitDataRepairInstance.mine_repair_examples(
            self.initial_state,
            self.repaired_state,
            changeset_miner=mine_one)
        # only one repair should be mined
        self.assertEqual(len(repairs), 1)
        repair_instance = repairs[0]
        repair_state_diff = repair_instance.repaired_state_or_diff
        # and it should be represented as two partial diffs
        self.assertGreater(
            len(repair_instance.error.change.diff.command_changes),
            0)
        self.assertIsInstance(repair_state_diff, ProjectStateDiff)
        assert isinstance(repair_state_diff, ProjectStateDiff)
        # there should be only one change
        self.assertEqual(len(list(repair_state_diff.diff.changed_commands)), 1)
        self.assertEqual(len(list(repair_state_diff.diff.added_commands)), 0)
        self.assertEqual(len(list(repair_state_diff.diff.dropped_commands)), 0)
        # only one command should be changed in that file
        (repaired_file, _, _) = list(repair_state_diff.diff.changed_commands)[0]
        # the only changed proofs are in one file
        self.assertEqual(repaired_file, "exgcd.v")
        # and the first changed proof in the file should be repaired
        broken_command_indices = set(
            self.diff.command_changes[repaired_file].changed_commands.keys()
        ).difference(
            repair_instance.error.change.diff.command_changes[repaired_file]
            .changed_commands.keys())
        self.assertEqual(len(broken_command_indices), 1)
        broken_command_index = broken_command_indices.pop()
        broken_command = self.initial_state.command_data[repaired_file][
            broken_command_index]
        self.assertEqual(broken_command.command_type, "VernacStartTheoremProof")
        self.assertEqual(broken_command.identifier, ["gcd_partial_proof"])
        with self.subTest("compression"):
            compressed_repair_instance = repair_instance.compress()
            self.assertEqual(
                compressed_repair_instance,
                self.compressed_repair_instance)

    @classmethod
    def setUpClass(cls) -> None:
        """
        Load realistic sample cached data.
        """
        cls.initial_state = ProjectCommitData.load(
            _DATA_PATH / "initial_state.yml")
        cls.repaired_state = ProjectCommitData.load(
            _DATA_PATH / "repaired_state.yml")
        cls.compressed_repair_instance = GitRepairInstance.load(
            _DATA_PATH / "compressed_repair_instance.yml")
        cls.diff = None


if __name__ == "__main__":
    unittest.main()
