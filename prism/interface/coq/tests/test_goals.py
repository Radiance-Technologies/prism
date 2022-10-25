"""
Test suite for `prism.interface.coq.goals`.
"""

import unittest

from prism.interface.coq.goals import (
    Goal,
    Goals,
    GoalsDiff,
    GoalType,
    Hypothesis,
)


class TestGoalsDiff(unittest.TestCase):
    """
    Test suite for `GoalsDiff`.
    """

    @classmethod
    def setUpClass(cls):
        """
        Set up common before and after changed goals.
        """
        cls.before = Goals(
            foreground_goals=[
                Goal(
                    11,
                    '@eq nat (Nat.add n (Nat.add m p)) (Nat.add (Nat.add n m) p)',
                    '(App (Ind (((MutInd (MPfile (DirPath ((Id Logic) (Id Init) '
                    '(Id Coq)))) (Id eq)) 0) (Instance ()))) '
                    '((Ind (((MutInd (MPfile (DirPath ((Id Datatypes) (Id Init) '
                    '(Id Coq)))) (Id nat)) 0) (Instance ()))) '
                    '(App (Const ((Constant (MPfile (DirPath ((Id Nat) (Id Init) '
                    '(Id Coq)))) (Id add)) (Instance ()))) ((Var (Id n)) '
                    '(App (Const ((Constant (MPfile (DirPath ((Id Nat) (Id Init) '
                    '(Id Coq)))) (Id add)) (Instance ()))) ((Var (Id m)) '
                    '(Var (Id p)))))) '
                    '(App (Const ((Constant (MPfile (DirPath ((Id Nat) (Id Init) '
                    '(Id Coq)))) (Id add)) (Instance ()))) '
                    '((App (Const ((Constant (MPfile (DirPath ((Id Nat) (Id Init) '
                    '(Id Coq)))) (Id add)) (Instance ()))) ((Var (Id n)) '
                    '(Var (Id m)))) (Var (Id p))))))',
                    [
                        Hypothesis(
                            ['p',
                             'm',
                             'n'],
                            None,
                            'nat',
                            '(Ind (((MutInd (MPfile (DirPath ((Id Datatypes) (Id Init) '
                            '(Id Coq)))) (Id nat)) 0) (Instance ())))')
                    ])
            ],
            background_goals=[
                (
                    [
                        Goal(
                            10,
                            '@eq nat (Nat.add O O) O',
                            '(App (Ind (((MutInd (MPfile (DirPath ((Id Logic) '
                            '(Id Init) (Id Coq)))) (Id eq)) 0) (Instance ()))) '
                            '((Ind (((MutInd (MPfile (DirPath ((Id Datatypes) '
                            '(Id Init) (Id Coq)))) (Id nat)) 0) (Instance ()))) '
                            '(App (Const ((Constant (MPfile (DirPath ((Id Nat) '
                            '(Id Init) (Id Coq)))) (Id add)) (Instance ()))) '
                            '((Construct ((((MutInd (MPfile (DirPath ((Id Datatypes) '
                            '(Id Init) (Id Coq)))) (Id nat)) 0) 1) (Instance ()))) '
                            '(Construct ((((MutInd (MPfile (DirPath ((Id Datatypes) '
                            '(Id Init) (Id Coq)))) (Id nat)) 0) 1) (Instance ()))))) '
                            '(Construct ((((MutInd (MPfile (DirPath ((Id Datatypes) '
                            '(Id Init) (Id Coq)))) (Id nat)) 0) 1) (Instance ())))))',
                            [])
                    ],
                    [])
            ],
            shelved_goals=[
                Goal(
                    13,
                    '@eq nat (Nat.add (S a) O) (S a)',
                    '(App (Ind (((MutInd (MPfile (DirPath ((Id Logic) (Id Init) '
                    '(Id Coq)))) (Id eq)) 0) (Instance ()))) '
                    '((Ind (((MutInd (MPfile (DirPath ((Id Datatypes) (Id Init) '
                    '(Id Coq)))) (Id nat)) 0) (Instance ()))) '
                    '(App (Const ((Constant (MPfile (DirPath ((Id Nat) (Id Init) '
                    '(Id Coq)))) (Id add)) (Instance ()))) '
                    '((App (Construct ((((MutInd (MPfile (DirPath ((Id Datatypes) '
                    '(Id Init) (Id Coq)))) (Id nat)) 0) 2) (Instance ()))) '
                    '((Var (Id a)))) '
                    '(Construct ((((MutInd (MPfile (DirPath ((Id Datatypes) '
                    '(Id Init) (Id Coq)))) (Id nat)) 0) 1) (Instance ()))))) '
                    '(App (Construct ((((MutInd (MPfile (DirPath ((Id Datatypes) '
                    '(Id Init) (Id Coq)))) (Id nat)) 0) 2) (Instance ()))) '
                    '((Var (Id a))))))',
                    [
                        Hypothesis(
                            ['a'],
                            None,
                            'nat',
                            '(Ind (((MutInd (MPfile (DirPath ((Id Datatypes) (Id Init) '
                            '(Id Coq)))) (Id nat)) 0) (Instance ())))'),
                        Hypothesis(
                            ['IH'],
                            None,
                            '@eq nat (Nat.add a O) a',
                            '(App (Ind (((MutInd (MPfile (DirPath ((Id Logic) '
                            '(Id Init) (Id Coq)))) (Id eq)) 0) (Instance ()))) '
                            '((Ind (((MutInd (MPfile (DirPath ((Id Datatypes) '
                            '(Id Init) (Id Coq)))) (Id nat)) 0) (Instance ()))) '
                            '(App (Const ((Constant (MPfile (DirPath ((Id Nat) '
                            '(Id Init) (Id Coq)))) (Id add)) (Instance ()))) '
                            '((Var (Id a)) '
                            '(Construct ((((MutInd (MPfile (DirPath ((Id Datatypes) '
                            '(Id Init) (Id Coq)))) (Id nat)) 0) 1) (Instance ()))))) '
                            '(Var (Id a))))')
                    ]),
                Goal(
                    9,
                    '@eq nat (Nat.add n m) (Nat.add m n)',
                    '(App (Ind (((MutInd (MPfile (DirPath ((Id Logic) (Id Init) '
                    '(Id Coq)))) (Id eq)) 0) (Instance ()))) '
                    '((Ind (((MutInd (MPfile (DirPath ((Id Datatypes) (Id Init) '
                    '(Id Coq)))) (Id nat)) 0) (Instance ()))) '
                    '(App (Const ((Constant (MPfile (DirPath ((Id Nat) (Id Init) '
                    '(Id Coq)))) (Id add)) (Instance ()))) ((Var (Id n)) '
                    '(App (Const ((Constant (MPfile (DirPath ((Id Nat) (Id Init) '
                    '(Id Coq)))) (Id add)) (Instance ()))) ((Var (Id m)) '
                    '(Var (Id p)))))) '
                    '(App (Const ((Constant (MPfile (DirPath ((Id Nat) (Id Init) '
                    '(Id Coq)))) (Id add)) (Instance ()))) '
                    '((App (Const ((Constant (MPfile (DirPath ((Id Nat) (Id Init) '
                    '(Id Coq)))) (Id add)) (Instance ()))) ((Var (Id n)) '
                    '(Var (Id m)))) (Var (Id p))))))',
                    [
                        Hypothesis(
                            ['m',
                             'n'],
                            None,
                            'nat',
                            '(Ind (((MutInd (MPfile (DirPath ((Id Datatypes) (Id Init) '
                            '(Id Coq)))) (Id nat)) 0) (Instance ())))')
                    ])
            ],
            abandoned_goals=[
                Goal(
                    11,
                    '@eq nat (Nat.add n (Nat.add m p)) (Nat.add (Nat.add n m) p)',
                    '(App (Ind (((MutInd (MPfile (DirPath ((Id Logic) (Id Init) '
                    '(Id Coq)))) (Id eq)) 0) (Instance ()))) '
                    '((Ind (((MutInd (MPfile (DirPath ((Id Datatypes) (Id Init) '
                    '(Id Coq)))) (Id nat)) 0) (Instance ()))) '
                    '(App (Const ((Constant (MPfile (DirPath ((Id Nat) (Id Init) '
                    '(Id Coq)))) (Id add)) (Instance ()))) ((Var (Id n)) '
                    '(App (Const ((Constant (MPfile (DirPath ((Id Nat) (Id Init) '
                    '(Id Coq)))) (Id add)) (Instance ()))) ((Var (Id m)) '
                    '(Var (Id p)))))) '
                    '(App (Const ((Constant (MPfile (DirPath ((Id Nat) (Id Init) '
                    '(Id Coq)))) (Id add)) (Instance ()))) '
                    '((App (Const ((Constant (MPfile (DirPath ((Id Nat) (Id Init) '
                    '(Id Coq)))) (Id add)) (Instance ()))) ((Var (Id n)) '
                    '(Var (Id m)))) (Var (Id p))))))',
                    [
                        Hypothesis(
                            ['p',
                             'm',
                             'n'],
                            None,
                            'nat',
                            '(Ind (((MutInd (MPfile (DirPath ((Id Datatypes) (Id Init) '
                            '(Id Coq)))) (Id nat)) 0) (Instance ())))')
                    ])
            ])
        cls.after = cls.before.shallow_copy()
        # move a goal from the shelf to the background
        goal = cls.after.pop(GoalType.SHELVED, (0, 0, True))
        cls.after.insert(goal, GoalType.BACKGROUND, (0, 0, False))
        # replace the foreground goal with the other shelved goal
        cls.after.pop(GoalType.FOREGROUND, (0, 0, True))
        goal = cls.after.pop(GoalType.SHELVED, (0, 0, True))
        cls.after.insert(goal, GoalType.FOREGROUND, (0, 0, True))
        # increase depth of background stack
        goal = cls.after.pop(GoalType.BACKGROUND, (0, 0, True))
        cls.after.insert(goal, GoalType.BACKGROUND, (1, 0, True))
        # duplicate abandoned goal
        goal = cls.after.get(GoalType.ABANDONED, *(0, 0, True))
        cls.after.insert(goal, GoalType.ABANDONED, (0, 1, True))

    def test_compute_diff_and_patch(self):
        """
        Compute a diff and verify that it can replay a change.
        """
        diff = GoalsDiff.compute_diff(self.before, self.after)
        replayed_after = diff.patch(self.before)
        self.assertEqual(replayed_after, self.after)
        diff = GoalsDiff.compute_diff(self.after, self.before)
        replayed_before = diff.patch(self.after)
        self.assertEqual(replayed_before, self.before)


if __name__ == '__main__':
    unittest.main()
