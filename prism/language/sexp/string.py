"""
Defines leaf s-expression nodes with string content.

Adapted from `roosterize.sexp.SexpString`
at https://github.com/EngineeringSoftware/roosterize/.
"""
from typing import Callable, List, Optional, Tuple

from prism.language.sexp.node import SexpNode


class SexpString(SexpNode):
    """
    An atomic node containing a single string of content.
    """

    def __init__(self, content: str = None) -> None:
        self._content = content if content is not None else ""

    def __deepcopy__(self, memodict=None) -> 'SexpString':  # noqa: D105
        return SexpString(self.content)

    def __eq__(self, other: SexpNode) -> bool:  # noqa: D105
        if not isinstance(other, SexpNode):
            return NotImplemented
        else:
            return other.is_string() and other._content == self._content

    def __str__(self) -> str:  # noqa: D105
        content = self.content
        if (not (content.startswith('"') and content.endswith('"'))
                and " " in content):
            content = '"' + content + '"'
        return content

    @property
    def height(self) -> int:  # noqa: D102
        return 0

    @property
    def num_nodes(self) -> int:  # noqa: D102
        return 1

    @property
    def num_leaves(self) -> int:  # noqa: D102
        return 1

    def apply_recur(  # noqa: D102
        self,
        func: Callable[["SexpNode"],
                       SexpNode.RecurAction]) -> None:
        func(self)

    def contains_str(self, s: str) -> bool:
        """
        Return whether `s` is equal to this node's content.
        """
        return self._content == s

    def forward_depth_first_sequence(self, *args, **kwargs) -> List[str]:
        """
        Return the content of this node wrapped in a list.
        """
        return [self.content]

    def get_content(self) -> str:  # noqa: D102
        return self._content

    def is_string(self) -> bool:  # noqa: D102
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
        sexp, _recur_action = pre_children_modify(self)
        if sexp is None:
            return None
        sexp = post_children_modify(sexp)
        return sexp

    def pretty_format(self, *args, **kwargs) -> str:
        """
        Return the string content of this node.
        """
        return self._content

    def to_python_ds(self) -> str:
        """
        Return the string content of this node.
        """
        return self._content
