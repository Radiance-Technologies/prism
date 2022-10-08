"""
Defines a parser of s-expressions.

Adapted from `roosterize.sexp.SexpParser`
at https://github.com/EngineeringSoftware/roosterize/.
"""
import logging
from typing import Iterable, List, Union

from prism.language.sexp.list import SexpList
from prism.language.sexp.node import SexpNode
from prism.language.sexp.string import SexpString


class SexpParser:
    """
    Namespace for methods that parse s-expressions.
    """

    logger = logging.getLogger(__name__)

    # non_par_printables = "".join(
    #     c for c in pyparsing.printables if c not in "()")

    c_quote = '"'
    c_escape = '\\'
    c_lpar = '('
    c_rpar = ')'

    @classmethod
    def from_python_ds(cls, python_ds: Union[str, Iterable]) -> SexpNode:
        """
        Convert an Python str/list s-expression to an `SexpNode`.

        Parameters
        ----------
        python_ds : Union[str, Iterable]
            A standalone term in an s-expression represented by Python
            lists and strings.

        Returns
        -------
        SexpNode
            An abstract, tree-structured representation of the given
            s-expression term.

        See Also
        --------
        SexpNode.to_python_ds : For the inverse operation.
        """
        if isinstance(python_ds, str):
            return SexpString(python_ds)
        else:
            return SexpList([cls.from_python_ds(child) for child in python_ds])
        # end if

    @classmethod
    def parse(cls, sexp_str: str) -> SexpNode:
        """
        Parse a string of s-expression to a structured s-expression.

        Parameters
        ----------
        sexp_str : str
            A string representing a standalone term in an s-expression.

        Returns
        -------
        SexpNode
            The deserialized representation of the given s-expression.

        Raises
        ------
        ValueError
            If the given s-expression string yields more than one node
            or is malformed.
        """
        sexps = cls.parse_list(sexp_str)
        if len(sexps) > 1:
            raise ValueError(
                f"Expected one s-expression node, got {len(sexps)}")
        return sexps[0]

    @classmethod
    def parse_list(cls, sexp_str: str) -> List[SexpNode]:
        """
        Parse a string of a list of s-expressions into `SexpNode`s.

        A single s-expression yields a singleton list.

        Parameters
        ----------
        sexp_list_str : str
            An s-expression representing a list of subterms.

        Returns
        -------
        list of SexpNode
            The list of deserialized subterms.

        Raises
        ------
        ValueError
            If the s-expression cannot be parsed, e.g., due to a syntax
            error.
        """
        return_stack = [[]]
        quoted = None
        escaped = False
        terminal = None

        for cur_char in sexp_str:
            if terminal is not None:
                assert quoted is None
                assert not escaped
                if (cur_char == cls.c_lpar or cur_char == cls.c_rpar
                        or cur_char == cls.c_quote or cur_char.isspace()):
                    # conclude terminal
                    return_stack[-1].append(SexpString(''.join(terminal)))
                    terminal = None
                else:
                    terminal.append(cur_char)
                    continue
            if quoted is not None:
                # extend or conclude string literal
                if escaped:
                    # escape the character
                    cur_char = ("\\"
                                + cur_char).encode().decode("unicode-escape")
                    quoted.append(cur_char)
                    escaped = False
                elif cur_char == cls.c_quote:
                    # End string literal
                    # Consume the ending quote
                    quoted.append('"')
                    return_stack[-1].append(SexpString(''.join(quoted)))
                    quoted = None
                elif cur_char == cls.c_escape:
                    # Escape the next character
                    escaped = True
                else:
                    quoted.append(cur_char)
            elif cur_char.isspace():
                # consume whitespace
                continue
            elif cur_char == cls.c_lpar:
                # consume the left paren
                # Start SexpList
                return_stack.append([])
            elif cur_char == cls.c_rpar:
                # Consume the right paren
                # End SexpList
                children = return_stack.pop()
                if not return_stack:
                    # too many close parens
                    break
                return_stack[-1].append(SexpList(children))
            elif cur_char == cls.c_quote:
                # consume the open quote
                # Start string literal
                quoted = ['"']
            else:
                # Start a normal token
                terminal = [cur_char]
            # end if
        if len(return_stack) != 1 or len(return_stack[0]) == 0:
            if len(sexp_str) > 100:
                sexp_str_err = sexp_str[: 72] + "..."
            raise ValueError(f"Malformed sexp: {sexp_str_err}")
        return return_stack[0]
