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
Defines a parser of s-expressions.

Adapted from `roosterize.sexp.SexpParser`
at https://github.com/EngineeringSoftware/roosterize/.
"""
import logging
from typing import Iterable, List, Union

from prism.language.sexp._parse import parse_sexps
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
        r"""
        Parse a string of s-expression to a structured s-expression.

        Note that escaped characters within literals (i.e., terminal
        symbols) are encoded as their unescaped representations (e.g.,
        ``\\n`` is stored as ``\n`` in the returned `SexpNode`),
        provided that they represent valid escape sequences.
        The only exception to this is the escaped double quote within a
        string literal.
        Furthermore, octal, hex, or unicode escape patterns are not
        respected; only single-character escape codes are supported.

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
    def _py_parse_list(cls, sexp_str: str) -> List[SexpNode]:  # noqa: C901
        """
        Parse a string of a list of s-expressions into `SexpNode`s.

        Reference implementation for `parse_sexps`.
        """
        return_stack = [[]]
        quoted = None
        escaped = False
        terminal = None

        for cur_char in sexp_str:
            if terminal is not None:
                assert quoted is None
                if escaped:
                    cur_char = ("\\" + cur_char)
                    try:
                        cur_char = cur_char.encode().decode("unicode-escape")
                    except UnicodeDecodeError:
                        pass
                if (not escaped
                        and (cur_char == cls.c_lpar or cur_char == cls.c_rpar
                             or cur_char == cls.c_quote or cur_char.isspace())):
                    # conclude terminal
                    return_stack[-1].append(SexpString(''.join(terminal)))
                    terminal = None
                else:
                    escaped = False
                    terminal.append(cur_char)
                    continue
            if escaped:
                # escape the character
                cur_char = ("\\" + cur_char)
                if quoted is None or cur_char != r'\"':
                    # keep double-quotes escaped if inside of a quote
                    try:
                        cur_char = cur_char.encode().decode("unicode-escape")
                    except UnicodeDecodeError:
                        pass
            elif cur_char == cls.c_escape:
                # Escape the next character
                escaped = True
                continue
            if quoted is not None:
                # extend or conclude string literal
                if not escaped and cur_char == cls.c_quote:
                    # End string literal
                    # Consume the ending quote
                    quoted.append('"')
                    return_stack[-1].append(SexpString(''.join(quoted)))
                    quoted = None
                else:
                    escaped = False
                    quoted.append(cur_char)
            elif not escaped:
                if cur_char.isspace():
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
                    # Start string literal
                    quoted = ['"']
                else:
                    # Start a normal token
                    escaped = False
                    terminal = [cur_char]
            else:
                # Start a normal token (with an escaped first character)
                escaped = False
                terminal = [cur_char]
        if terminal is not None:
            # conclude terminal
            return_stack[-1].append(SexpString(''.join(terminal)))
        if len(return_stack) != 1 or len(return_stack[0]) == 0:
            if len(sexp_str) > 100:
                sexp_str_err = sexp_str[: 72] + "..."
            raise ValueError(f"Malformed sexp: {sexp_str_err}")
        return return_stack[0]

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
        return parse_sexps(sexp_str)
