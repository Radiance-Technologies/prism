#
# Copyright (c) 2023 Radiance Technologies, Inc.
#
# This file is part of PRISM
# (see https://github.com/orgs/Radiance-Technologies/prism).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program. If not, see
# <http://www.gnu.org/licenses/>.
#
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
                            '(Id Coq)))) (Id nat)) 0) (Instance ())))',
                            None,
                            '(VernacExpr () (VernacCheckMayEval () () '
                            '((v (CRef ((v (Ser_Qualid (DirPath ()) (Id nat))) '
                            '(loc (((fname ToplevelInput) (line_nb 1) (bol_pos 0) '
                            '(line_nb_last 1) (bol_pos_last 0) (bp 6) (ep 9))))) ())) '
                            '(loc (((fname ToplevelInput) (line_nb 1) (bol_pos 0) '
                            '(line_nb_last 1) (bol_pos_last 0) (bp 6) (ep 9)))))))'
                        )
                    ])
            ],
            background_goals=[
                ([],
                 []),
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
                    []),
                ([],
                 []),
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
                            '(Id Coq)))) (Id nat)) 0) (Instance ())))',
                            None,
                            '(VernacExpr () (VernacCheckMayEval () () '
                            '((v (CRef ((v (Ser_Qualid (DirPath ()) (Id nat))) '
                            '(loc (((fname ToplevelInput) (line_nb 1) (bol_pos 0) '
                            '(line_nb_last 1) (bol_pos_last 0) (bp 6) (ep 9))))) ())) '
                            '(loc (((fname ToplevelInput) (line_nb 1) (bol_pos 0) '
                            '(line_nb_last 1) (bol_pos_last 0) (bp 6) (ep 9)))))))'
                        ),
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
                            '(Var (Id a))))',
                            None,
                            '(VernacExpr () (VernacCheckMayEval () () '
                            '((v (CAppExpl (() ((v (Ser_Qualid (DirPath ()) (Id eq))) '
                            '(loc (((fname ToplevelInput) (line_nb 1) (bol_pos 0) '
                            '(line_nb_last 1) (bol_pos_last 0) (bp 7) (ep 9))))) ()) '
                            '(((v (CRef ((v (Ser_Qualid (DirPath ()) (Id nat))) '
                            '(loc (((fname ToplevelInput) (line_nb 1) (bol_pos 0) '
                            '(line_nb_last 1) (bol_pos_last 0) (bp 10) (ep 13))))) '
                            '())) (loc (((fname ToplevelInput) (line_nb 1) (bol_pos 0) '
                            '(line_nb_last 1) (bol_pos_last 0) (bp 10) (ep 13))))) '
                            '((v (CApp (() ((v (CRef ((v (Ser_Qualid (DirPath '
                            '((Id Nat))) (Id add))) (loc (((fname ToplevelInput) '
                            '(line_nb 1) (bol_pos 0) (line_nb_last 1) (bol_pos_last 0) '
                            '(bp 15) (ep 22))))) ())) (loc (((fname ToplevelInput) '
                            '(line_nb 1) (bol_pos 0) (line_nb_last 1) (bol_pos_last 0) '
                            '(bp 15) (ep 22)))))) ((((v (CRef ((v (Ser_Qualid '
                            '(DirPath ()) (Id a))) (loc (((fname ToplevelInput) '
                            '(line_nb 1) (bol_pos 0) (line_nb_last 1) (bol_pos_last 0) '
                            '(bp 23) (ep 24))))) ())) (loc (((fname ToplevelInput) '
                            '(line_nb 1) (bol_pos 0) (line_nb_last 1) (bol_pos_last 0) '
                            '(bp 23) (ep 24))))) ()) (((v (CRef ((v (Ser_Qualid '
                            '(DirPath ()) (Id O))) (loc (((fname ToplevelInput) '
                            '(line_nb 1) (bol_pos 0) (line_nb_last 1) (bol_pos_last 0) '
                            '(bp 25) (ep 26))))) ())) (loc (((fname ToplevelInput) '
                            '(line_nb 1) (bol_pos 0) (line_nb_last 1) (bol_pos_last 0) '
                            '(bp 25) (ep 26))))) ())))) (loc (((fname ToplevelInput) '
                            '(line_nb 1) (bol_pos 0) (line_nb_last 1) (bol_pos_last 0) '
                            '(bp 15) (ep 26))))) ((v (CRef ((v (Ser_Qualid '
                            '(DirPath ()) (Id a))) (loc (((fname ToplevelInput) '
                            '(line_nb 1) (bol_pos 0) (line_nb_last 1) (bol_pos_last 0) '
                            '(bp 28) (ep 29))))) ())) (loc (((fname ToplevelInput) '
                            '(line_nb 1) (bol_pos 0) (line_nb_last 1) (bol_pos_last 0) '
                            '(bp 28) (ep 29)))))))) (loc (((fname ToplevelInput) '
                            '(line_nb 1) (bol_pos 0) (line_nb_last 1) (bol_pos_last 0) '
                            '(bp 6) (ep 29)))))))')
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
                            '(Id Coq)))) (Id nat)) 0) (Instance ())))',
                            None,
                            '(VernacExpr () (VernacCheckMayEval () () '
                            '((v (CRef ((v (Ser_Qualid (DirPath ()) (Id nat))) '
                            '(loc (((fname ToplevelInput) (line_nb 1) (bol_pos 0) '
                            '(line_nb_last 1) (bol_pos_last 0) (bp 6) (ep 9))))) ())) '
                            '(loc (((fname ToplevelInput) (line_nb 1) (bol_pos 0) '
                            '(line_nb_last 1) (bol_pos_last 0) (bp 6) (ep 9)))))))'
                        )
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
                            '(Id Coq)))) (Id nat)) 0) (Instance ())))',
                            None,
                            '(VernacExpr () (VernacCheckMayEval () () '
                            '((v (CRef ((v (Ser_Qualid (DirPath ()) (Id nat))) '
                            '(loc (((fname ToplevelInput) (line_nb 1) (bol_pos 0) '
                            '(line_nb_last 1) (bol_pos_last 0) (bp 6) (ep 9))))) ())) '
                            '(loc (((fname ToplevelInput) (line_nb 1) (bol_pos 0) '
                            '(line_nb_last 1) (bol_pos_last 0) (bp 6) (ep 9)))))))'
                        )
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
        goal = cls.after.pop(GoalType.BACKGROUND, (1, 0, True))
        cls.after.insert(goal, GoalType.BACKGROUND, (3, 0, True))
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
        with self.subTest("unchanged"):
            for goals in [self.before, self.after]:
                expected_diff = GoalsDiff()
                actual_diff = GoalsDiff.compute_diff(goals, goals)
                self.assertEqual(expected_diff.patch(goals), goals)
                self.assertEqual(actual_diff.patch(goals), goals)
                self.assertEqual(expected_diff, actual_diff)


if __name__ == '__main__':
    unittest.main()
