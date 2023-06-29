"""
Test suite for `prism.data.cache.types`.
"""
import typing
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import List, Optional, Tuple, Union

import seutil.io as io

from prism.data.cache.types.command import VernacSentence
from prism.interface.coq.goals import Goals, GoalsDiff
from prism.interface.coq.ident import Identifier, IdentType, get_all_idents
from prism.interface.coq.serapi import SerAPI
from prism.language.gallina.analyze import SexpInfo
from prism.language.sexp.node import SexpNode
from prism.util.io import Fmt

TEST_DIR = Path(__file__).parent


class TestVernacSentence(unittest.TestCase):
    """
    Test suite for `VernacSentence`.
    """

    def test_serialization(self) -> None:
        """
        Verify that `VernacSentence` can be serialize/deserialized.
        """
        goals: List[Optional[Union[Goals, GoalsDiff]]] = []
        asts = []
        commands = [
            "Lemma foobar : unit.",
            "shelve.",
            "Unshelve.",
            "exact tt.",
            "Qed."
        ]
        with SerAPI() as serapi:
            goals.append(serapi.query_goals())
            for c in commands:
                (_,
                 _,
                 ast) = typing.cast(
                     Tuple[List[SexpNode],
                           List[str],
                           SexpNode],
                     serapi.execute(c,
                                    return_ast=True))
                goals.append(serapi.query_goals())
                asts.append(ast)
        # force multiple added goals
        assert isinstance(goals[1], Goals)
        assert isinstance(goals[2], Goals)
        goals[2].foreground_goals = [
            deepcopy(g) for g in goals[1].foreground_goals * 3
        ]
        goals[2].foreground_goals[0].id += 1
        goals[2].foreground_goals[1].id += 2
        goals[2].shelved_goals.append(goals[2].foreground_goals[0])
        goals = goals[0 : 1] + [
            GoalsDiff.compute_diff(g1,
                                   g2)
            if isinstance(g1,
                          Goals) and isinstance(g2,
                                                Goals) else g2 for g1,
            g2 in zip(goals,
                      goals[1 :])
        ]
        sentences = [
            VernacSentence(
                c,
                a,
                [
                    Identifier(IdentType.lident,
                               "lemma"),
                    Identifier(IdentType.CRef,
                               "unit")
                ],
                SexpInfo.Loc("test_build_cache.py",
                             0,
                             0,
                             0,
                             0,
                             0,
                             0),
                "CommandType",
                g,
                get_identifiers=lambda ast: typing.cast(
                    list,
                    get_all_idents(ast,
                                   True))) for c,
            a,
            g in zip(commands,
                     asts,
                     goals)
        ]
        with NamedTemporaryFile("w") as f:
            with self.subTest("serialize"):
                io.dump(f.name, sentences, fmt=Fmt.yaml)
            with self.subTest("deserialize"):
                loaded = io.load(f.name, Fmt.yaml, clz=List[VernacSentence])
                self.assertEqual(loaded, sentences)
