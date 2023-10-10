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
Defines leaf s-expression nodes with string content.

Adapted from `roosterize.sexp.SexpString`
at https://github.com/EngineeringSoftware/roosterize/.
"""
from typing import Callable, Iterator, List, Optional, Tuple

from prism.language.sexp.exception import IllegalSexpOperationException
from prism.language.sexp.node import SexpNode
from prism.util.string import escape_backslash


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

    def __iter__(self) -> Iterator['SexpNode']:  # noqa: D105
        raise IllegalSexpOperationException(
            "Cannot iterate over children of an s-exp string")

    def __str__(self) -> str:  # noqa: D105
        content = self.content
        if (not (content.startswith('"') and content.endswith('"'))
                and " " in content):
            content = '"' + escape_backslash(content) + '"'
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

    def modify_recur(  # noqa: D102
        self,
        pre_children_modify: Callable[["SexpNode"],
                                      Tuple[Optional["SexpNode"],
                                            SexpNode.RecurAction]] = lambda x:
        (x,
         SexpNode.RecurAction.ContinueRecursion),
        post_children_modify: Callable[["SexpNode"],
                                       Optional["SexpNode"]] = lambda x: x,
    ) -> Optional["SexpNode"]:
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
