"""
Defines internal, non-leaf s-expression nodes with branching subtrees.
"""

import copy
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from prism.language.sexp.node import SexpNode


class SexpList(SexpNode):
    """
    An internal node of an s-expression tree with multiple branches.
    """

    pprint_newline = "\n"
    pprint_tab = "  "

    def __init__(self, children: List[SexpNode] = None) -> None:
        self.children = children if children is not None else list()

    def __deepcopy__(self, memodict=None) -> 'SexpList':  # noqa: D105
        return SexpList([copy.deepcopy(c) for c in self.children])

    def __str__(self) -> str:  # noqa: D105
        s = "("
        last_is_str = False
        for c in self.children:
            # Put space only between SexpString
            if c.is_string():
                if last_is_str:
                    s += " "
                # end if
                last_is_str = True
            # end if

            s += c.__str__()
        # end for
        s += ")"
        return s

    @property
    def height(self) -> int:  # noqa: D102
        return max([c.height for c in self.children] + [0]) + 1

    @property
    def num_nodes(self) -> int:  # noqa: D102
        return sum([c.num_nodes for c in self.children]) + 1

    @property
    def num_leaves(self) -> int:  # noqa: D102
        return sum([c.num_leaves for c in self.children])

    def apply_recur(  # noqa: D102
            self,
            func: Callable[["SexpNode"],
                           SexpNode.RecurAction]) -> None:
        recur_action = func(self)

        if recur_action == SexpNode.RecurAction.ContinueRecursion:
            for child in self.children:
                child.apply_recur(func)
            # end for
        # end if

    def contains_str(self, s: str) -> bool:  # noqa: D102
        for c in self.children:
            if c.contains_str(s):
                return True
            # end if
        # end for
        return False

    def forward_depth_first_sequence(
        self,
        children_filtering_func: Callable[[Sequence["SexpNode"]],
                                          Iterable["SexpNode"]] = lambda x: x,
        use_parenthesis: bool = False,
    ) -> List[str]:  # noqa: D102
        core = [
            t for c in children_filtering_func(self.children)
            for t in c.forward_depth_first_sequence(
                children_filtering_func,
                use_parenthesis)
        ]
        if use_parenthesis:
            return ["("] + core + [")"]
        else:
            return core
        # end if

    def get_children(self):  # noqa: D102
        return self.children

    def is_list(self):  # noqa: D102
        return True

    def modify_recur(
        self,
        pre_children_modify: Callable[["SexpNode"],
                                      Tuple[Optional["SexpNode"],
                                            SexpNode.RecurAction]] = lambda x:
        (x,
         SexpNode.RecurAction.ContinueRecursion),
        post_children_modify: Callable[["SexpNode"],
                                       Optional["SexpNode"]] = lambda x: x,
    ) -> Optional["SexpNode"]:  # noqa: D102
        sexp, recur_action = pre_children_modify(self)

        if sexp is None:
            return None

        if sexp.is_list(
        ) and recur_action == SexpNode.RecurAction.ContinueRecursion:
            child_i = 0
            while child_i < len(sexp.get_children()):
                new_child = sexp.get_children()[child_i].modify_recur(
                    pre_children_modify,
                    post_children_modify)
                if new_child is None:
                    del sexp.get_children()[child_i]
                else:
                    sexp.get_children()[child_i] = new_child
                    child_i += 1
                # end if
            # end for
        # end if

        sexp = post_children_modify(sexp)
        return sexp

    def pretty_format(self, max_depth: int = np.PINF) -> str:  # noqa: D102
        return self.pretty_format_recur(self, max_depth, 0).strip()

    def to_python_ds(self) -> list:  # noqa: D102
        return [child.to_python_ds() for child in self.children]

    @classmethod
    def pretty_format_recur(
            cls,
            sexp: SexpNode,
            max_depth: int,
            depth: int) -> str:
        """
        Recursively pretty-print the given node's subtree.

        Parameters
        ----------
        sexp : SexpNode
            A node.
        max_depth : int
            The maximum depth at which content should be printed.
            An ellipsis will be printed if the maximum depth when the
            maximum depth is met.
        depth : int
            The depth of the given node `sexp`.

        Returns
        -------
        str
            The pretty-printed format of the s-expression.
        """
        if sexp.is_string():
            return sexp.pretty_format()
        # end if

        sexp: SexpList
        if len(sexp.children) == 0:
            return "()"
        else:
            if max_depth == 0:
                return " ... "
            else:
                return (
                    cls.pprint_newline + depth * cls.pprint_tab + "("
                    + " ".join(
                        [
                            cls.pretty_format_recur(
                                c,
                                max_depth - 1,
                                depth + 1) for c in sexp.children
                        ]) + ")")
            # end if
        # end if
