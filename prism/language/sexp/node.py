"""
Defines an abstract representation of s-expressions as nodes in trees.

Adapted from `roosterize.sexp.SexpNode`
at https://github.com/EngineeringSoftware/roosterize/.
"""

import abc
import sys
from collections import deque
from enum import Enum
from typing import (
    Callable,
    Deque,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
)

import numpy as np

from prism.language.sexp.exception import IllegalSexpOperationException


class SexpNode(abc.ABC):
    """
    Abstract class of a node in an s-exp represented as a tree.
    """

    class RecurAction(Enum):
        """
        Records the result of a recursively applied function.
        """

        ContinueRecursion = 0
        StopRecursion = 1

    @abc.abstractmethod
    def __deepcopy__(self, memodict=None) -> 'SexpNode':  # noqa: D105
        ...

    def __getitem__(self, index: int) -> 'SexpNode':
        """
        Get the `index`-th child of this node.

        Parameters
        ----------
        index : int
            The index of the requested child.

        Returns
        -------
        SexpNode
            The requested child node.

        Raises
        ------
        IllegalSexpOperationException
            If the index is out of bounds or the node has no children.
        """
        children = self.get_children()
        if children is None:
            raise IllegalSexpOperationException(
                "Cannot get the children of an s-exp string.")
        elif isinstance(index, int):
            if index < -len(children) or index >= len(children):
                raise IllegalSexpOperationException(
                    f"Cannot get child ({index}), "
                    f"this list only has {len(children)} children.")
            # end if
        # end if

        return children[index]

    @abc.abstractmethod
    def __eq__(self, other: 'SexpNode') -> bool:  # noqa: D105
        ...

    def __len__(self) -> int:
        """
        Get the number of immediate children.

        Returns
        -------
        int
            The number of immediate children of this node.
        """
        if self.is_list():
            return len(self.get_children())
        else:
            return 0

    @abc.abstractmethod
    def __str__(self) -> str:
        """
        Get a representation of this subtree as an s-expression.
        """
        ...

    @abc.abstractmethod
    def contains_str(self, s: str) -> bool:
        """
        Return whether the given string is in in this node's subtree.

        Returns
        -------
        bool
            The number of nodes in the tree rooted at this `SexpNode`.
        """
        ...

    @property
    def content(self) -> str:
        """
        Get the content of the SexpString, or throw exception.

        Returns
        -------
        str
            The content of the node if it is a string.

        Raises
        ------
        IllegalSexpOperationException
            If the content is None, i.e. the node is not a string.
        """
        content = self.get_content()
        if content is None:
            raise IllegalSexpOperationException(
                "Cannot get the content of an s-exp list.")
        else:
            return content
        # end if

    @property
    def content_no_quote(self) -> str:
        """
        Get the content stripped of leading/trailing quotes.

        This only strips the outermost layer of quotes, preserving any
        quotes that would otherwise be interpreted as part of the
        content.

        Returns
        -------
        str
            The content stripped of at most one layer of leading or
            trailing quotes.
        """
        content = self.content
        if content.startswith('"'):
            content = content[1 :-1]
        return content

    @property
    @abc.abstractmethod
    def height(self) -> int:
        """
        Get the height of the s-expression rooted at this node.

        Returns
        -------
        int
            The height of the tree rooted at this `SexpNode`.
        """
        ...

    @property
    @abc.abstractmethod
    def num_nodes(self) -> int:
        """
        Get the number of nodes in this node's subtree.

        Returns
        -------
        int
            The number of nodes in the tree rooted at this `SexpNode`.
        """
        ...

    @property
    @abc.abstractmethod
    def num_leaves(self) -> int:
        """
        Get the number of leaves in this node's subtree.

        Returns
        -------
        int
            The number of leaves in the tree rooted at this `SexpNode`.
        """
        ...

    @abc.abstractmethod
    def apply_recur(self, func: Callable[["SexpNode"], RecurAction]) -> None:
        """
        Apply a function in depth-first-search order to this subtree.

        Parameters
        ----------
        func : func: Callable[["SexpNode"], RecurAction]
            A function that must necessarily modify its given `SexpNode`
            in-place or modifies variables in its closure.
        """
        ...

    def backward_depth_first_sequence(
        self,
        children_filtering_func: Callable[[Sequence["SexpNode"]],
                                          Iterable["SexpNode"]] = lambda x: x,
        use_parenthesis: bool = False,
    ) -> List[str]:
        """
        Filter the content of this s-expression in reverse order.

        See Also
        --------
        SexpNode.forward_depth_first_sequence
        """
        return self.forward_depth_first_sequence(
            lambda x: children_filtering_func(reversed(x)),
            use_parenthesis)

    def dot(self) -> str:
        """
        Get the source for a visualization of this node's subtree.

        A PDF can be generated with: `dot -Tpdf $file -o $pdfFile`.

        Returns
        -------
        str
            A text representation of this node's subtree in a format
            suitable for visualization with `dot`.
        """
        out = ""
        out += "digraph x {"
        toVisit: Deque[SexpNode] = deque()
        toVisit.append(self)
        while len(toVisit) > 0:
            currentSexp: SexpNode = toVisit.popleft()
            if currentSexp.is_string():
                label = currentSexp.content.replace('"', '\'')
                out += (
                    f"n{hash(currentSexp)% ((sys.maxsize + 1) * 2)} "
                    f"[label=\"{label}\" shape=none];\n")
            else:
                out += (
                    f"n{hash(currentSexp)% ((sys.maxsize + 1) * 2)} "
                    "[shape=point];\n")
                for child in currentSexp.get_children():
                    toVisit.append(child)
                    out += (
                        f"n{hash(currentSexp)% ((sys.maxsize + 1) * 2)} "
                        f"-> n{hash(child)% ((sys.maxsize + 1) * 2)};\n")
                # end for
            # end if
        # end while
        out += "}\n"

        return out

    @abc.abstractmethod
    def forward_depth_first_sequence(
        self,
        children_filtering_func: Callable[[Iterable["SexpNode"]],
                                          Iterable["SexpNode"]] = lambda x: x,
        use_parathesis: bool = False,
    ) -> List[str]:
        r"""
        Filter the content of this s-expression in order.

        Parameters
        ----------
        children_filtering_func : Callable[[Sequence["SexpNode"]], \
                                           Iterable["SexpNode"]], \
                                  optional
            A function that takes a sequence of nodes and returns an
            iterator over a derived subset of nodes, nominally a
            filtered subset.
            By default identity.
        use_parenthesis : bool, optional
            Whether to intersperse the result with parantheses at each
            level of the tree, by default False.

        Returns
        -------
        List[str]
            The (possibly `children_filtering_func`-modified) content
            of this node's filtered subtree.
        """
        ...

    def flatten(self) -> List["SexpNode"]:
        """
        Flatten the s-expression tree according to a preorder traversal.

        Returns
        -------
        list of SexpNode
            The nodes contained in this s-expression tree in preorder
            (each node appears before any children).
        """
        node_list = [self]
        if self.is_list():
            for c in self.get_children():
                node_list.extend(c.flatten())
        return node_list

    def get_children(self) -> Optional[List["SexpNode"]]:
        """
        Get the children of this (list) node.

        Returns
        -------
        list of SexpNode or None
            This node's children if this is a list node, otherwise None.
        """
        return None

    def get_content(self) -> Optional[str]:
        """
        Get the content of this (string) node.

        Returns
        -------
        str or None
            The node's content if this is a string node, otherwise None.
        """
        return None

    def head(self) -> str:
        """
        Get the first piece of content in this node's subtree.
        """
        # default implementation works for string subclass
        return self.get_content()

    def tail(self) -> Optional['SexpNode']:
        """
        Get all but the head of this node's subtree.
        """
        # default implementation works for string subclass
        return None

    def is_list(self) -> bool:
        """
        Check if this node is a list.

        Returns
        -------
        bool
            True if this node is a list, False otherwise.
        """
        return False

    def is_string(self) -> bool:
        """
        Check if this node is a string.

        Returns
        -------
        bool
            True if this node is a string, False otherwise.
        """
        return False

    @abc.abstractmethod
    def modify_recur(
        self,
        pre_children_modify: Callable[["SexpNode"],
                                      Tuple[Optional["SexpNode"],
                                            RecurAction]] = lambda x:
        (x,
         SexpNode.RecurAction.ContinueRecursion),
        post_children_modify: Callable[["SexpNode"],
                                       Optional["SexpNode"]] = lambda x: x,
    ) -> Optional["SexpNode"]:
        r"""
        Perform an out-of-place modification of this node's subtree.

        Recursively visits (in depth-first-search order) each node in
        the s-expression and modifies the s-expression.
        Two functions are composed and applied to this node and each of
        its children.

        Parameters
        ----------
        pre_children_modify : Callable[[SexpNode], \
                                       Tuple[Optional[SexpNode], \
                                             RecurAction]]
            The function that should be applied prior to applying the
            modification on children.
        post_children_modify : Callable[[SexpNode], Optional[SexpNode]]
            The function that should be applied after applying the
            modification on children.

        Returns
        -------
        Optional[SexpNode]
            The modified s-expression to replace this s-expression node,
            or None if deleting this node from parent list.
        """
        ...

    @abc.abstractmethod
    def pretty_format(self, max_depth: int = np.PINF) -> str:
        """
        Format this s-expression into a human-readable string.

        Returns
        -------
        str
            A pretty human-readable string for this s-expression.
        """
        ...

    def serialize(self) -> str:
        """
        Convert this node's subtree to an s-expression.

        Returns
        -------
        str
            An s-expression corresponding to this node's subtree.
        """
        return self.__str__()

    @abc.abstractmethod
    def to_python_ds(self) -> Union[str, list]:
        """
        Convert this s-expression to Python lists and strings.
        """
        ...

    @classmethod
    def deserialize(cls, data: str) -> 'SexpNode':
        """
        Parse the given s-expression into an `SexpNode`.

        Parameters
        ----------
        data : str
            A serialized s-expression.

        Returns
        -------
        SexpNode
            The parsed, deserialized s-expression.
        """
        # TODO: Refactor to remove circular reference.
        from prism.language.sexp.parser import SexpParser
        return SexpParser.parse(data)
