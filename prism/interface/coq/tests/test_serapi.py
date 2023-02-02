"""
Test suite for `prism.interface.coq.serapi`.
"""
import multiprocessing
import os
import re
import unittest
from dataclasses import asdict
from typing import Dict, List, Optional

from prism.interface.coq.exception import CoqExn
from prism.interface.coq.serapi import Goal, Goals, Hypothesis, SerAPI
from prism.language.gallina.parser import CoqParser
from prism.language.heuristic.parser import HeuristicParser
from prism.language.sexp.list import SexpList
from prism.language.sexp.node import SexpNode
from prism.language.sexp.parser import SexpParser
from prism.language.sexp.string import SexpString
from prism.tests import _COQ_EXAMPLES_PATH
from prism.util.opam import OpamSwitch, OpamVersion
from prism.util.string import normalize_spaces


def omit_locs(sexp: SexpNode) -> SexpNode:
    """
    Replace location terms in the AST with ``[LOC]``.

    The result should match that expected from SerAPI commands when
    ``--omit-loc`` is provided.

    Parameters
    ----------
    sexp : SexpNode
        A serialized AST.

    Returns
    -------
    SexpNode
        The given AST albeit with all location subtrees replaced with a
        ``[LOC]`` atom.
    """
    if sexp.is_list():
        if sexp.head() == "fname" and sexp.num_nodes == 25:
            return SexpList([SexpString('"[LOC]"')])
        else:
            return SexpList([omit_locs(c) for c in sexp.get_children()])
    else:
        return SexpString(sexp.get_content())


def execute_sentences(
        sentences: List[str],
        test_switch: Optional[OpamSwitch]) -> None:
    """
    Execute the given sentences in an interactive session.
    """
    with SerAPI(opam_switch=test_switch) as serapi:
        for sentence in sentences:
            serapi.execute(sentence)


def update_vernac_control(sexp: str, do_update: bool) -> str:
    """
    Transform a `vernac_control` structure to post-8.10.2 format.
    """
    if do_update:
        sexp = normalize_spaces(sexp)
        match = re.match(r"\(VernacExpr \(\) \((?P<vernac_sexp>.*)\)\)", sexp)
        if match is not None:
            sexp = f"((control ()) (attrs ()) (expr ({match['vernac_sexp']})))"
    return sexp


def update_GType(sexp: str, do_update: bool) -> str:
    """
    Transform an anonymous GType to post-8.10.2 format.
    """
    if do_update:
        sexp = normalize_spaces(sexp)
        sexp = re.sub(r"GType \(\)", "UAnonymous (rigid true)", sexp)
    return sexp


def update_kername(sexp: str, do_update: bool) -> str:
    """
    Transform KerNames to pre-8.10 format.
    """

    def _update_kername(s: SexpNode) -> SexpNode:
        if s.is_list():
            children = s.get_children()
            assert children is not None
            if (children and children[0].is_string()
                    and children[0].get_content() in {"MutInd",
                                                      "Constant"}):
                children = list(children)
                # NOTE: SerAPI's capitalization for its internal version
                # of MutInd changed between versions 8.9 and 8.10
                if children[0].get_content() == "MutInd":
                    children[0] = SexpString("Mutind")
                children.insert(
                    2,
                    SexpList([SexpString("DirPath"),
                              SexpList()]))
            else:
                children = [_update_kername(c) for c in children]
            return SexpList(children)
        else:
            content = s.get_content()
            assert content is not None
            return SexpString(content)

    if do_update:
        updated_sexp = SexpParser.parse(sexp)
        updated_sexp = _update_kername(updated_sexp)
        sexp = str(updated_sexp)
    return sexp


def update_binders_and_levels(sexp: str, do_update: bool) -> str:
    """
    Update binder and `Level` structures to pre-8.10 format.
    """

    def _update_binders(s: SexpNode) -> SexpNode:
        if s.is_list():
            children = s.get_children()
            assert children is not None
            if children and children[0].is_string():
                if children[0].get_content() == "Prod":
                    children = [
                        children[0],
                        children[1][0][1],
                        _update_binders(children[2]),
                        _update_binders(children[3])
                    ]
                elif children[0].get_content() == "Level":
                    children = [children[0], children[1][1], children[1][0]]
                else:
                    children = [_update_binders(c) for c in children]
            else:
                children = [_update_binders(c) for c in children]
            return SexpList(children)
        else:
            content = s.get_content()
            assert content is not None
            return SexpString(content)

    if do_update:
        updated_sexp = SexpParser.parse(sexp)
        updated_sexp = _update_binders(updated_sexp)
        sexp = str(updated_sexp)
    return sexp


class TestSerAPI(unittest.TestCase):
    """
    Test suite for the interactive `SerAPI` interface.
    """

    test_switch: OpamSwitch = OpamSwitch()
    sentences: Dict[str, List[str]]
    serapi_version: str
    update_8_9: bool
    update_8_11: bool
    update_8_12: bool

    @classmethod
    def setUpClass(cls) -> None:
        """
        Set up some example documents for realistic inputs.
        """
        cls.serapi_version = cls.test_switch.get_installed_version("coq-serapi")
        assert cls.serapi_version is not None
        cls.update_8_9 = OpamVersion.less_than(cls.serapi_version, "8.10")
        cls.update_8_11 = OpamVersion.less_than("8.10.2", cls.serapi_version)
        cls.update_8_12 = OpamVersion.less_than("8.11.2", cls.serapi_version)
        cls.update_8_13 = OpamVersion.less_than("8.12.2", cls.serapi_version)
        cls.sentences = {}
        for filename in ['simple', 'nested', 'Alphabet']:
            sentences = HeuristicParser.parse_sentences_from_file(
                _COQ_EXAMPLES_PATH / f"{filename}.v",
                glom_proofs=False)
            cls.sentences[filename] = [str(s) for s in sentences]

    def test_execute(self):
        """
        Verify some simple commands can be executed.
        """
        expected_ast = """
            (VernacExpr ()
                  (VernacLocate
                    (LocateAny
                      (
                        (v
                          (ByNotation
                            ("_ ∘ _" ())))
                        (loc
                          (
                            (
                              (fname ToplevelInput)
                              (line_nb 1)
                              (bol_pos 0)
                              (line_nb_last 1)
                              (bol_pos_last 0)
                              (bp 7)
                              (ep 16))))))))
            """
        expected_ast = update_vernac_control(expected_ast, self.update_8_11)
        expected_ast = SexpParser.parse(expected_ast)
        expected_state_id = 20 if self.update_8_9 else 22
        with SerAPI(opam_switch=self.test_switch) as serapi:
            responses, _ = serapi.execute("Require Import Coq.Program.Basics.")
            self.assertEqual(
                str(responses[0]),
                f'(Answer {expected_state_id} Ack)')
            self.assertEqual(
                str(responses[1]),
                f'(Answer {expected_state_id} Completed)')
            responses, _, ast = serapi.execute('Locate "_ ∘ _".', True)
            self.assertEqual(
                str(responses[0]),
                f'(Answer {expected_state_id+3} Ack)')
            self.assertEqual(
                str(responses[1]),
                f'(Answer {expected_state_id+3} Completed)')
            self.assertEqual(ast, expected_ast)

    def test_get_local_ids(self):
        """
        Verify that locally defined identifiers can be obtained.
        """
        with SerAPI(opam_switch=self.test_switch) as serapi:
            for sentence in self.sentences['simple']:
                serapi.execute(sentence)
            serapi.execute("Parameter (A : Set).")
            actual_idents = serapi.get_local_ids()
        expected_idents = [
            'SerTop',
            'seq',
            'seq_rect',
            'seq_ind',
            'seq_rec',
        ] + ([
            'seq_sind',
        ] if not self.update_8_9 else [])
        expected_idents += ['length', 'm', 'length_corr', 'b2Prop', 'A']
        self.assertEqual(actual_idents, expected_idents)

    def test_get_conjecture_id(self):
        """
        Verify that conjecture names can be obtained.
        """
        with SerAPI(opam_switch=self.test_switch) as serapi:
            actual_ids = [serapi.get_conjecture_id()]
            for sentence in self.sentences['nested']:
                serapi.execute(sentence)
                actual_ids.append(serapi.get_conjecture_id())
        expected_ids = [
            None,
            None,
            'foobar',
            'foobar',
            'foobar',
            'foobar',
            None,
            None,
            "foobar'",
            "aux",
            "aux",
            "aux",
            "aux",
            "aux",
            "foobar'",
            "foobar'",
            None,
            None
        ]
        self.assertEqual(actual_ids, expected_ids)

    def test_has_open_goals(self):
        """
        Test detection of proof modes with simple examples.
        """
        simple_sentences = self.sentences['simple']
        with self.subTest("simple"):
            with SerAPI(opam_switch=self.test_switch) as serapi:
                self.assertFalse(serapi.has_open_goals())
                serapi.execute(simple_sentences[0])
                self.assertFalse(serapi.has_open_goals())
                serapi.execute(simple_sentences[1])
                self.assertFalse(serapi.is_in_proof_mode)
                serapi.execute(simple_sentences[2])
                self.assertTrue(serapi.has_open_goals())
                self.assertTrue(serapi.is_in_proof_mode)
        nested_sentences = self.sentences['nested']
        with self.subTest("nested"):
            with SerAPI(opam_switch=self.test_switch) as serapi:
                self.assertFalse(serapi.has_open_goals())
                serapi.execute(nested_sentences[0])
                self.assertFalse(serapi.has_open_goals())
                serapi.execute(nested_sentences[1])
                self.assertTrue(serapi.is_in_proof_mode)
                for i in range(3):
                    # this includes a mid-proof import
                    serapi.execute(nested_sentences[2 + i])
                    self.assertTrue(serapi.has_open_goals())
                serapi.execute(nested_sentences[5])
                self.assertFalse(serapi.has_open_goals())
                # set nested proofs allowed
                serapi.execute(nested_sentences[6])
                self.assertFalse(serapi.has_open_goals())
                for i in range(8):
                    serapi.execute(nested_sentences[7 + i])
                    self.assertTrue(serapi.is_in_proof_mode)
                serapi.execute(nested_sentences[15])
                self.assertFalse(serapi.is_in_proof_mode)

    def test_multiprocessing(self):
        """
        Verify that multiple SerAPI contexts can be managed at once.
        """
        with multiprocessing.Pool(3) as p:
            p.starmap(
                execute_sentences,
                [(s,
                  self.test_switch) for s in self.sentences.values()])

    def test_query_ast(self):
        """
        Verify that queried ASTs match those obtained from `sercomp`.
        """
        expected_asts = CoqParser.parse_asts(
            _COQ_EXAMPLES_PATH / "simple.v",
            opam_switch=self.test_switch)
        actual_asts = []
        with SerAPI(omit_loc=True, opam_switch=self.test_switch) as serapi:
            for sentence in self.sentences["simple"]:
                # actually execute to ensure notations/imports exist
                serapi.execute(sentence)
                actual_asts.append(serapi.query_ast(sentence))
        for actual, expected in zip(actual_asts, expected_asts):
            # do not compare based on locations since those will
            # definitely differ
            actual = omit_locs(actual)
            expected = omit_locs(expected)
            # Also strip top-level location from expected since it is
            # pre-stripped from queried AST
            expected = expected[0][1]
            self.assertEqual(actual, expected)

    def test_query_env(self):
        """
        Verify that a global environment can be retrieved.

        Also verify that the environment can be extended with local
        definitions.
        """
        mut_ind_example = """
        Inductive tree : Set := node : A -> forest -> tree

        with forest : Set :=
        | leaf : B -> forest
        | cons : tree -> forest -> forest.
        """
        expected_keys = {
            'nat',
            'SerTop.nat',
            'Datatypes.nat',
            'Init.Datatypes.nat',
            'Coq.Init.Datatypes.nat',
            'tree',
            'SerTop.tree',
            'foo',
            'SerTop.foo',
            'A',
            'B',
            'SerTop.A',
            'SerTop.B'
        }
        expected_tree_ind = {
            'physical_path': '<interactive>:tree',
            'short_id': 'tree',
            'full_id': 'SerTop.tree',
            'blocks':
                [
                    {
                        'short_id':
                            'tree',
                        'full_id':
                            'SerTop.tree',
                        'constructors':
                            [('node',
                              'forall (_ : A) (_ : forest), tree')]
                    },
                    {
                        'short_id':
                            'forest',
                        'full_id':
                            'SerTop.forest',
                        'constructors':
                            [
                                ('leaf',
                                 'forall _ : B, forest'),
                                (
                                    'cons',
                                    'forall (_ : tree) (_ : forest), forest')
                            ]
                    }
                ],
            'is_record': False
        }
        expected_A_const = {
            'physical_path': '<interactive>:A',
            'short_id': 'A',
            'full_id': 'SerTop.A',
            'term': None,
            'type': 'Set',
            'sort': 'Type',
            'opaque': None
        }
        expected_nat_ind = {
            'physical_path':
                '<interactive>:nat',
            'short_id':
                'nat',
            'full_id':
                'SerTop.nat',
            'blocks':
                [
                    {
                        'short_id':
                            'nat',
                        'full_id':
                            'SerTop.nat',
                        'constructors':
                            [('O',
                              'nat'),
                             ('S',
                              'forall _ : nat, nat')]
                    }
                ],
        }
        with SerAPI(max_wait_time=120, opam_switch=self.test_switch) as serapi:
            serapi.execute(
                "Inductive nat : Type := O : nat | S (n : nat) : nat.")
            serapi.execute("Lemma foo : unit.")
            serapi.execute("Admitted.")
            serapi.execute("Parameters A B : Set.")
            serapi.execute(normalize_spaces(mut_ind_example))
            env = serapi.query_env().asdict()
            for qualid in expected_keys:
                self.assertIn(qualid, env)
            actual_tree_ind = asdict(env['tree'])
            self.assertDictEqual(
                actual_tree_ind,
                {
                    **actual_tree_ind,
                    **expected_tree_ind
                })
            actual_A_const = asdict(env['A'])
            self.assertDictEqual(
                actual_A_const,
                {
                    **actual_A_const,
                    **expected_A_const
                })
            actual_nat_ind = asdict(env['nat'])
            self.assertDictEqual(
                actual_nat_ind,
                {
                    **actual_nat_ind,
                    **expected_nat_ind
                })
            expected_coq_nat_ind = {
                'physical_path':
                    str(
                        os.path.relpath(
                            serapi.switch.path.joinpath(
                                "lib",
                                "coq",
                                "theories",
                                "Init",
                                "Datatypes.vo"))) + ':nat',
                'short_id':
                    'Datatypes.nat',
                'full_id':
                    'Coq.Init.Datatypes.nat',
                'blocks':
                    [
                        {
                            'short_id':
                                'Datatypes.nat',
                            'full_id':
                                'Coq.Init.Datatypes.nat',
                            'constructors':
                                [
                                    ('O',
                                     'Datatypes.nat'),
                                    (
                                        'S',
                                        'forall _ : Datatypes.nat, Datatypes.nat'
                                    )
                                ]
                        }
                    ],
            }
            actual_coq_nat_ind = asdict(env['Datatypes.nat'])
            self.assertDictEqual(
                actual_coq_nat_ind,
                {
                    **actual_coq_nat_ind,
                    **expected_coq_nat_ind
                })

    def test_query_full_qualid(self):
        """
        Verify that fully qualified identifiers can be retrieved.
        """
        with SerAPI(opam_switch=self.test_switch) as serapi:
            self.assertEqual(
                serapi.query_full_qualids("nat"),
                ["Coq.Init.Datatypes.nat"])
            serapi.execute(
                "Inductive nat : Type := O : nat | S (n : nat) : nat.")
            serapi.execute("Module test.")
            serapi.execute("Lemma nat : unit.")
            serapi.execute("Admitted.")
            actual = serapi.query_full_qualids("nat")
            expected = [
                "SerTop.test.nat",
                "Coq.Init.Datatypes.nat",
                "SerTop.nat"
            ]
            self.assertEqual(actual, expected)
            serapi.execute("End test.")
            actual = serapi.query_full_qualids("nat")
            expected = [
                "SerTop.nat",
                "Coq.Init.Datatypes.nat",
                "SerTop.test.nat"
            ]
            self.assertEqual(actual, expected)
            self.assertEqual(
                serapi.query_full_qualid("Datatypes.nat"),
                "Coq.Init.Datatypes.nat")
            self.assertEqual(serapi.query_full_qualid("nat"), "SerTop.nat")
            with self.subTest("idempotent"):
                qualid = serapi.query_full_qualid("Logic.or")
                assert qualid is not None
                self.assertEqual(qualid, "Coq.Init.Logic.or")
                qualid = serapi.query_full_qualid(qualid)
                self.assertEqual(qualid, "Coq.Init.Logic.or")

    def test_query_goals(self):
        """
        Verify that goals can be obtained when in proof mode.

        Likewise, verify that no goals are obtained when not in the
        middle of a proof.
        """
        unit_kernel = update_kername(
            '(Ind (((MutInd (MPfile (DirPath ((Id Datatypes) (Id Init) (Id Coq)))) '
            '(Id unit)) 0) (Instance ())))',
            self.update_8_9)

        def expected_unit_goals(
                evar: int,
                hypotheses: Optional[List[Hypothesis]] = None) -> Goals:
            if hypotheses is None:
                hypotheses = []
            return Goals(
                [Goal(evar,
                      'unit',
                      unit_kernel,
                      hypotheses)],
                [],
                [],
                [])

        def drop_goal_asts(goal: Goal) -> Goal:
            """
            Drop optional AST fields.
            """
            return Goal(
                goal.id,
                goal.type,
                goal.type_sexp,
                [h for h in goal.hypotheses])

        def drop_asts(goals: Goals) -> Goals:
            """
            Drop optional AST fields recursively.
            """
            return Goals(
                [drop_goal_asts(g) for g in goals.foreground_goals],
                [
                    (
                        [drop_goal_asts(g) for g in lgs],
                        [drop_goal_asts(g) for g in rgs]) for lgs,
                    rgs in goals.background_goals
                ],
                [drop_goal_asts(g) for g in goals.shelved_goals],
                [drop_goal_asts(g) for g in goals.abandoned_goals])

        nested_kernel = update_binders_and_levels(
            update_kername(
                '(Prod ((binder_name (Name (Id A))) (binder_relevance Relevant)) '
                '(Sort (Type ((((hash 14398528522911) '
                '(data (Level ((DirPath ((Id SerTop))) 1)))) 0)))) '
                '(Prod ((binder_name Anonymous) (binder_relevance Relevant)) '
                '(Rel 1) (Ind (((MutInd (MPfile (DirPath ((Id Datatypes) '
                '(Id Init) (Id Coq)))) (Id unit)) 0) (Instance ())))))',
                self.update_8_9),
            self.update_8_9)
        expected_nested_goals = Goals(
            [Goal(3,
                  'forall (A : Type) (_ : A), unit',
                  nested_kernel,
                  [])],
            [],
            [],
            [])
        expected_hypotheses = [
            Hypothesis(
                ['A'],
                None,
                'Type',
                update_binders_and_levels(
                    '(Sort (Type ((((hash 14398528522911) '
                    '(data (Level ((DirPath ((Id SerTop))) 1)))) 0))))',
                    self.update_8_9),
                None,
                update_GType(
                    update_vernac_control(
                        '(VernacExpr () (VernacCheckMayEval () () '
                        '((v (CSort (GType ()))) '
                        '(loc (((fname ToplevelInput) (line_nb 1) (bol_pos 0) '
                        '(line_nb_last 1) (bol_pos_last 0) (bp 6) (ep 10)))))))',
                        self.update_8_11),
                    self.update_8_11)),
            Hypothesis(
                ['X'],
                None,
                'A',
                '(Var (Id A))',
                None,
                update_vernac_control(
                    '(VernacExpr () (VernacCheckMayEval () () '
                    '((v (CRef ((v (Ser_Qualid (DirPath ()) (Id A))) '
                    '(loc (((fname ToplevelInput) (line_nb 1) (bol_pos 0) '
                    '(line_nb_last 1) (bol_pos_last 0) (bp 6) (ep 7))))) ())) '
                    '(loc (((fname ToplevelInput) (line_nb 1) (bol_pos 0) '
                    '(line_nb_last 1) (bol_pos_last 0) (bp 6) (ep 7)))))))',
                    self.update_8_11))
        ]
        posed_hypothesis = Hypothesis(
            ['foo'],
            'idw A',
            'Type',
            update_binders_and_levels(
                '(Sort (Type ((((hash 14398528588510) '
                '(data (Level ((DirPath ((Id SerTop))) 2)))) 0))))',
                self.update_8_9),
            update_vernac_control(
                '(VernacExpr () (VernacCheckMayEval () () '
                '((v (CApp (() ((v (CRef ((v (Ser_Qualid (DirPath ()) (Id idw))) '
                '(loc (((fname ToplevelInput) (line_nb 1) (bol_pos 0) (line_nb_last 1) '
                '(bol_pos_last 0) (bp 6) (ep 9))))) ())) '
                '(loc (((fname ToplevelInput) (line_nb 1) (bol_pos 0) (line_nb_last 1) '
                '(bol_pos_last 0) (bp 6) (ep 9)))))) '
                '((((v (CRef ((v (Ser_Qualid (DirPath ()) (Id A))) '
                '(loc (((fname ToplevelInput) (line_nb 1) (bol_pos 0) (line_nb_last 1) '
                '(bol_pos_last 0) (bp 10) (ep 11))))) ())) '
                '(loc (((fname ToplevelInput) (line_nb 1) (bol_pos 0) (line_nb_last 1) '
                '(bol_pos_last 0) (bp 10) (ep 11))))) ())))) (loc '
                '(((fname ToplevelInput) '
                '(line_nb 1) (bol_pos 0) (line_nb_last 1) (bol_pos_last 0) (bp 6) '
                '(ep 11)))))))',
                self.update_8_11),
            update_GType(
                update_vernac_control(
                    '(VernacExpr () (VernacCheckMayEval () () ((v (CSort (GType ()))) '
                    '(loc (((fname ToplevelInput) (line_nb 1) (bol_pos 0) '
                    '(line_nb_last 1) '
                    '(bol_pos_last 0) (bp 6) (ep 10)))))))',
                    self.update_8_11),
                self.update_8_11))
        no_goals = None
        focused_no_goals = Goals([], [([], [])], [], [])
        expected_add0_base_goal = Goal(
            9 if self.update_8_12 else 10,
            '@eq nat (Nat.add O O) O',
            update_kername(
                '(App (Ind (((MutInd (MPfile (DirPath ((Id Logic) (Id Init) '
                '(Id Coq)))) (Id eq)) 0) (Instance ()))) '
                '((Ind (((MutInd (MPfile (DirPath ((Id Datatypes) (Id Init) '
                '(Id Coq)))) (Id nat)) 0) (Instance ()))) '
                '(App (Const ((Constant (MPfile (DirPath ((Id Nat) (Id Init) '
                '(Id Coq)))) (Id add)) (Instance ()))) '
                '((Construct ((((MutInd (MPfile (DirPath ((Id Datatypes) (Id Init) '
                '(Id Coq)))) (Id nat)) 0) 1) (Instance ()))) '
                '(Construct ((((MutInd (MPfile (DirPath ((Id Datatypes) (Id Init) '
                '(Id Coq)))) (Id nat)) 0) 1) (Instance ()))))) '
                '(Construct ((((MutInd (MPfile (DirPath ((Id Datatypes) (Id Init) '
                '(Id Coq)))) (Id nat)) 0) 1) (Instance ())))))',
                self.update_8_9),
            [])
        expected_add0_ind_goal = Goal(
            12 if self.update_8_12 else 13,
            '@eq nat (Nat.add (S a) O) (S a)',
            update_kername(
                '(App (Ind (((MutInd (MPfile (DirPath ((Id Logic) (Id Init) '
                '(Id Coq)))) (Id eq)) 0) (Instance ()))) '
                '((Ind (((MutInd (MPfile (DirPath ((Id Datatypes) (Id Init) '
                '(Id Coq)))) (Id nat)) 0) (Instance ()))) '
                '(App (Const ((Constant (MPfile (DirPath ((Id Nat) (Id Init) '
                '(Id Coq)))) (Id add)) (Instance ()))) '
                '((App (Construct ((((MutInd (MPfile (DirPath ((Id Datatypes) '
                '(Id Init) (Id Coq)))) (Id nat)) 0) 2) (Instance ()))) ((Var (Id a)))) '
                '(Construct ((((MutInd (MPfile (DirPath ((Id Datatypes) (Id Init) '
                '(Id Coq)))) (Id nat)) 0) 1) (Instance ()))))) '
                '(App (Construct ((((MutInd (MPfile (DirPath ((Id Datatypes) (Id Init) '
                '(Id Coq)))) (Id nat)) 0) 2) (Instance ()))) ((Var (Id a))))))',
                self.update_8_9),
            [
                Hypothesis(
                    ['a'],
                    None,
                    'nat',
                    update_kername(
                        '(Ind (((MutInd (MPfile (DirPath ((Id Datatypes) (Id Init) '
                        '(Id Coq)))) (Id nat)) 0) (Instance ())))',
                        self.update_8_9),
                    None,
                    update_vernac_control(
                        '(VernacExpr () (VernacCheckMayEval () () '
                        '((v (CRef ((v (Ser_Qualid (DirPath ()) (Id nat))) '
                        '(loc (((fname ToplevelInput) (line_nb 1) (bol_pos 0) '
                        '(line_nb_last 1) (bol_pos_last 0) (bp 6) (ep 9))))) ())) '
                        '(loc (((fname ToplevelInput) (line_nb 1) (bol_pos 0) '
                        '(line_nb_last 1) (bol_pos_last 0) (bp 6) (ep 9)))))))',
                        self.update_8_11)),
                Hypothesis(
                    ['IH'],
                    None,
                    '@eq nat (Nat.add a O) a',
                    update_kername(
                        '(App (Ind (((MutInd (MPfile (DirPath ((Id Logic) (Id Init) '
                        '(Id Coq)))) (Id eq)) 0) (Instance ()))) '
                        '((Ind (((MutInd (MPfile (DirPath ((Id Datatypes) (Id Init) '
                        '(Id Coq)))) (Id nat)) 0) (Instance ()))) '
                        '(App (Const ((Constant (MPfile (DirPath ((Id Nat) (Id Init) '
                        '(Id Coq)))) (Id add)) (Instance ()))) ((Var (Id a)) '
                        '(Construct ((((MutInd (MPfile (DirPath ((Id Datatypes) '
                        '(Id Init) '
                        '(Id Coq)))) (Id nat)) 0) 1) (Instance ()))))) (Var (Id a))))',
                        self.update_8_9),
                    None,
                    update_vernac_control(
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
                        '(bp 6) (ep 29)))))))',
                        self.update_8_11))
            ])
        expected_add_assoc_goals = Goals(
            [
                Goal(
                    9 if self.update_8_12 else 11,
                    '@eq nat (Nat.add n (Nat.add m p)) (Nat.add (Nat.add n m) p)',
                    update_kername(
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
                        self.update_8_9),
                    [
                        Hypothesis(
                            ['p',
                             'm',
                             'n'],
                            None,
                            'nat',
                            update_kername(
                                '(Ind (((MutInd (MPfile (DirPath ((Id Datatypes) '
                                '(Id Init) '
                                '(Id Coq)))) (Id nat)) 0) (Instance ())))',
                                self.update_8_9),
                            None,
                            update_vernac_control(
                                '(VernacExpr () (VernacCheckMayEval () () '
                                '((v (CRef ((v (Ser_Qualid (DirPath ()) (Id nat))) '
                                '(loc (((fname ToplevelInput) (line_nb 1) (bol_pos 0) '
                                '(line_nb_last 1) (bol_pos_last 0) (bp 6) (ep 9))))) '
                                '())) '
                                '(loc (((fname ToplevelInput) (line_nb 1) (bol_pos 0) '
                                '(line_nb_last 1) (bol_pos_last 0) (bp 6) (ep 9)))))))',
                                self.update_8_11))
                    ])
            ],
            [],
            [],
            [])

        def assertEqualGoals(actual: Optional[Goals], expected: Goals) -> None:
            """
            Assert equality irrespective of AST fields.
            """
            return self.assertEqual(
                drop_asts(actual) if actual is not None else actual,
                expected)

        with SerAPI(opam_switch=self.test_switch) as serapi:
            with self.subTest("simple"):
                serapi.execute("Lemma foobar : unit.")
                goals = serapi.query_goals()
                assertEqualGoals(goals, expected_unit_goals(1))
                serapi.execute("Require Import Program.")
                goals = serapi.query_goals()
                assertEqualGoals(goals, expected_unit_goals(1))
                serapi.execute("apply (const tt tt).")
                goals = serapi.query_goals()
                self.assertEqual(goals, no_goals)
                serapi.execute("Qed.")
                goals = serapi.query_goals()
                self.assertEqual(goals, no_goals)
            with self.subTest("nested"):
                serapi.execute("Set Nested Proofs Allowed.")
                serapi.execute("Lemma foobar' : unit.")
                goals = serapi.query_goals()
                assertEqualGoals(goals, expected_unit_goals(2))
                serapi.execute("Lemma aux : forall A : Type, A -> unit.")
                goals = serapi.query_goals()
                assertEqualGoals(goals, expected_nested_goals)
                serapi.execute("intros.")
                goals = serapi.query_goals()
                assertEqualGoals(
                    goals,
                    expected_unit_goals(5,
                                        expected_hypotheses))
                serapi.execute("Definition idw (A : Type) := A.")
                goals = serapi.query_goals()
                assertEqualGoals(
                    goals,
                    expected_unit_goals(5,
                                        expected_hypotheses))
                serapi.execute("pose (foo := idw A).")
                goals = serapi.query_goals()
                assertEqualGoals(
                    goals,
                    expected_unit_goals(
                        7 if self.update_8_9 else 6,
                        expected_hypotheses + [posed_hypothesis]))
                serapi.execute("exact tt.")
                goals = serapi.query_goals()
                self.assertEqual(goals, no_goals)
                serapi.execute("Qed.")
                goals = serapi.query_goals()
                assertEqualGoals(goals, expected_unit_goals(2))
                serapi.execute("apply (@aux unit tt).")
                goals = serapi.query_goals()
                self.assertEqual(goals, no_goals)
                serapi.execute("Qed.")
                goals = serapi.query_goals()
                self.assertEqual(goals, no_goals)
            with self.subTest("multiple_goals"):
                serapi.execute("Lemma add_0_r: forall (a : nat), a + 0 = a.")
                serapi.execute("intros.")
                goals = serapi.query_goals()
                serapi.execute("induction a as [| a IH].")
                goals = serapi.query_goals()
                assertEqualGoals(
                    goals,
                    Goals(
                        [expected_add0_base_goal,
                         expected_add0_ind_goal],
                        [],
                        [],
                        []))
                serapi.execute("-")
                goals = serapi.query_goals()
                assertEqualGoals(
                    goals,
                    Goals(
                        [expected_add0_base_goal],
                        [([],
                          [expected_add0_ind_goal])],
                        [],
                        []))
                serapi.execute("reflexivity.")
                goals = serapi.query_goals()
                assertEqualGoals(
                    goals,
                    Goals([],
                          [([],
                            [expected_add0_ind_goal])],
                          [],
                          []))
                serapi.execute("-")
                goals = serapi.query_goals()
                assertEqualGoals(
                    goals,
                    Goals([expected_add0_ind_goal],
                          [([],
                            [])],
                          [],
                          []))
                serapi.execute("simpl. rewrite -> IH. reflexivity.")
                goals = serapi.query_goals()
                self.assertEqual(goals, focused_no_goals)
                serapi.execute("Qed.")
            with self.subTest("multiple_idents"):
                serapi.execute(
                    "Theorem add_assoc : forall n m p : nat, "
                    "n + (m + p) = (n + m) + p.")
                serapi.execute("intros.")
                goals = serapi.query_goals()
                assertEqualGoals(goals, expected_add_assoc_goals)

    def test_query_library(self):
        """
        Verify that libraries' physical paths can be queried.
        """
        with SerAPI(opam_switch=self.test_switch) as serapi:
            actual = serapi.query_library("Datatypes")
            expected = serapi.switch.path.joinpath(
                "lib",
                "coq",
                "theories",
                "Init",
                "Datatypes.vo")
            self.assertEqual(actual, expected)
            with self.assertRaises(CoqExn):
                serapi.query_library("nonexistent_library")

    def test_query_qualid(self):
        """
        Verify that minimally qualified identifiers can be retrieved.
        """
        with SerAPI(opam_switch=self.test_switch) as serapi:
            self.assertEqual(serapi.query_qualids("nat"), ["nat"])
            serapi.execute(
                "Inductive nat : Type := O : nat | S (n : nat) : nat.")
            serapi.execute("Module test.")
            serapi.execute("Lemma nat : unit.")
            serapi.execute("Admitted.")
            actual = serapi.query_qualids("nat")
            expected = ["nat", "Datatypes.nat", "SerTop.nat"]
            self.assertEqual(actual, expected)
            serapi.execute("End test.")
            actual = serapi.query_full_qualids("nat")
            expected = ["nat", "Datatypes.nat", "test.nat."]
            self.assertEqual(
                serapi.query_qualid("Coq.Init.Datatypes.nat"),
                "Datatypes.nat")
            with self.subTest("idempotent"):
                qualid = serapi.query_qualid("Init.Logic.or")
                self.assertEqual(qualid, "or")
                qualid = serapi.query_qualid(qualid)
                self.assertEqual(qualid, "or")

    def test_query_type(self):
        """
        Verify that types of expressions and identifiers can be queried.
        """
        with SerAPI(opam_switch=self.test_switch) as serapi:
            expected_type = 'forall (A : Type) (x : A), @eq A x x'
            self.assertEqual(serapi.query_type("eq_refl"), expected_type)
            self.assertEqual(serapi.query_type(expected_type), "Prop")

    def test_query_vernac(self):
        """
        Verify that queries generate feedback.
        """
        with SerAPI(opam_switch=self.test_switch) as serapi:
            serapi.execute(
                "Inductive nat : Type := O : nat | S (n : nat) : nat.")
            actual = serapi.query_vernac("Print nat.")
            expected = [
                "Inductive nat : Set :=  O : nat | S : forall _ : nat, nat"
            ]
            self.assertEqual(actual, expected)

    def test_recovery(self):
        """
        Verify that control may be recovered after an exception.
        """
        with SerAPI(opam_switch=self.test_switch) as serapi:
            with self.assertRaises(CoqExn):
                serapi.execute("Require Import.")
            try:
                # capture an error message
                serapi.execute("Require Import.")
            except CoqExn as e:
                if self.update_8_13:
                    expected_exception = (
                        "Syntax error: [global] expected after "
                        "[export_token] (in [gallina_ext]).")
                else:
                    expected_exception = (
                        "[constr:global] expected after "
                        "[export_token] (in [vernac:gallina_ext])")
                    if not self.update_8_9:
                        expected_exception = f"Syntax error: {expected_exception}."
                self.assertEqual(e.msg, expected_exception)
            # verify execution of normal commands is successful
            serapi.execute("Inductive const := C | D.")
            serapi.execute(
                'Definition swap (c : const) := match c with | C => D | D => C end.'
            )
            actual = serapi.query_vernac("Print swap.")
            expected = normalize_spaces(
                """
            swap = fun c : const => match c with
                               | C => D
                                    | D => C
                                    end
                 : forall _ : const, const
            """)
            self.assertEqual(normalize_spaces(actual[0]), expected)

    def test_parse_new_identifiers(self):
        """
        Verify that new identifiers can be parsed from feedback.
        """
        with SerAPI(opam_switch=self.test_switch) as serapi:
            _, feedback = serapi.execute(
                "Inductive nat : Type := O : nat | S (n : nat) : nat.")
            actual_idents = serapi.parse_new_identifiers(feedback)
            expected_idents = [
                "nat",
                "nat_rect",
                "nat_ind",
                "nat_rec",
            ]
            if not self.update_8_9:
                expected_idents.append("nat_sind")
            self.assertEqual(actual_idents, expected_idents)
            _, feedback = serapi.execute("Module foo.")
            actual_idents = serapi.parse_new_identifiers(feedback)
            self.assertEqual(actual_idents, ['foo'])
            _, feedback = serapi.execute("End foo.")
            actual_idents = serapi.parse_new_identifiers(feedback)
            self.assertEqual(actual_idents, ['foo'])
            _, feedback = serapi.execute("Lemma foobar : unit.")
            actual_idents = serapi.parse_new_identifiers(feedback)
            self.assertEqual(actual_idents, [])
            _, feedback = serapi.execute("intros.")
            actual_idents = serapi.parse_new_identifiers(feedback)
            self.assertEqual(actual_idents, [])
            _, feedback = serapi.execute("Admitted.")
            actual_idents = serapi.parse_new_identifiers(feedback)
            self.assertEqual(actual_idents, ['foobar'])


if __name__ == '__main__':
    unittest.main()
