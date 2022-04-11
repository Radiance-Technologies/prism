"""
Defines a parser of s-expressions.

Adapted from `roosterize.sexp.SexpParser`
at https://github.com/EngineeringSoftware/roosterize/.
"""
import logging
import string
from typing import Iterable, List, Tuple, Union

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
        Parse a string of s-expression to structured s-expression.

        Parameters
        ----------
        sexp_str : str
            A string representing a standalone term in an s-expression.

        Returns
        -------
        SexpNode
            The deserialized representation of the given s-expression.
        """
        sexp, end_pos = cls.parse_recur(sexp_str, 0)
        if end_pos != len(sexp_str):
            cls.logger.warning(
                "Parsing did not terminate at the last character! "
                f"({end_pos}/{len(sexp_str)})")
        # end if

        return sexp

    @classmethod
    def parse_list(cls, sexp_list_str: str) -> List[SexpNode]:
        """
        Parse a string of a list of s-expressions into `SexpNode`s.

        Parameters
        ----------
        sexp_list_str : str
            An s-expression representing a list of subterms.

        Returns
        -------
        list of SexpNode
            The list of deserialized subterms.
        """
        sexp_list: List[SexpNode] = list()
        sexp_list_str = sexp_list_str.strip()
        cur_pos = 0
        while cur_pos < len(sexp_list_str):
            sexp, cur_pos = cls.parse_recur(sexp_list_str, cur_pos)
            sexp_list.append(sexp)
        # end while

        return sexp_list

    @classmethod
    def parse_recur(cls, sexp_str: str, cur_pos: int) -> Tuple[SexpNode, int]:
        """
        Recursively parse an s-expression, maintaining current progress.

        More precisely, parses the next s-expression term in the string.

        Parameters
        ----------
        sexp_str : str
            The s-expression to parse.
        cur_pos : int
            The current position of the parser.

        Returns
        -------
        SexpNode
            The deserialized representation of the next term.
        int
            The position of the parser after parsing the next term.

        Raises
        ------
        ValueError
            If the s-expression cannot be parsed, e.g., due to a syntax
            error.
        """
        try:
            cur_char = None

            # Find the next non-whitespace char
            def parse_ws():
                nonlocal cur_char, sexp_str, cur_pos
                cur_char = sexp_str[cur_pos]
                while cur_char in string.whitespace:
                    cur_pos += 1
                    cur_char = sexp_str[cur_pos]
                # end while
                return

            # end def

            parse_ws()

            if cur_char == cls.c_lpar:
                # Start SexpList
                child_sexps: List[SexpNode] = list()
                cur_pos += 1

                while True:
                    parse_ws()
                    cur_char = sexp_str[cur_pos]
                    if cur_char == cls.c_rpar:
                        break
                    else:
                        child_sexp, cur_pos = cls.parse_recur(sexp_str, cur_pos)
                        child_sexps.append(child_sexp)
                    # end if
                # end while

                # Consume the ending par
                return SexpList(child_sexps), cur_pos + 1
            elif cur_char == cls.c_quote:
                # Start string literal
                cur_token = cur_char
                cur_pos += 1
                while True:
                    cur_char = sexp_str[cur_pos]
                    if cur_char == cls.c_quote:
                        # End string literal
                        cur_token += cur_char
                        break
                    elif cur_char == cls.c_escape:
                        # Goto and escape the next char
                        cur_pos += 1
                        cur_char = ("\\" + sexp_str[cur_pos]
                                    ).encode().decode("unicode-escape")
                    # end if
                    cur_token += cur_char
                    cur_pos += 1
                # end while

                # Consume the ending quote
                return SexpString(cur_token[1 :-1]), cur_pos + 1
            else:
                # Start a normal token
                cur_token = cur_char
                cur_pos += 1
                while True:
                    cur_char = sexp_str[cur_pos]
                    if (cur_char == cls.c_lpar or cur_char == cls.c_rpar
                            or cur_char == cls.c_quote
                            or cur_char in string.whitespace):
                        break
                    # end if
                    cur_token += cur_char
                    cur_pos += 1
                # end while

                # Does not consume the stopping char
                return SexpString(cur_token), cur_pos
            # end if
        except IndexError as e:
            raise ValueError("Malformed sexp") from e
