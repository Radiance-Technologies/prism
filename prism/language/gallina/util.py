"""
Defines utilities for parsing Coq/Gallina.
"""

import re
from typing import List, Optional, Tuple


class ParserUtils:
    """
    Provides a namespace for Coq parsing utilities.
    """

    # regular expression for detecting comments
    REGEX_COMMENT = re.compile(r"\s*(?P<com>\(\*[\s\S]*\*\))\s*")

    @classmethod
    def actual_charno_to_coq_charno_bp(
            cls,
            actual_charno: int,
            unicode_offsets: List[int]) -> int:
        """
        Convert a lexical character index to its first index in UTF-8.

        Parameters
        ----------
        actual_charno : int
            The raw character index of a lexical symbol or character
            irrespective of encoding in a string.
        unicode_offsets : List[int]
            The number of bytes in excess of one of each non-ASCII
            UTF-8 character in the implicit string.

        Returns
        -------
        int
            The index of the first byte of the indicated lexical
            character in a UTF-8 encoding of the implicit string.
        """
        return actual_charno + len(
            [offset for offset in unicode_offsets if offset < actual_charno])

    @classmethod
    def actual_charno_to_coq_charno_ep(
            cls,
            actual_charno: int,
            unicode_offsets: List[int]) -> int:
        """
        Convert a lexical character index to its last index in UTF-8.

        Parameters
        ----------
        actual_charno : int
            The raw character index of a lexical symbol or character
            irrespective of encoding in a string.
        unicode_offsets : List[int]
            The number of bytes in excess of one of each non-ASCII
            UTF-8 character in the implicit string.

        Returns
        -------
        int
            The index of the last byte of the indicated lexical
            character in a UTF-8 encoding of the implicit string.
        """
        return actual_charno + len(
            [offset for offset in unicode_offsets if offset <= actual_charno])

    @classmethod
    def coq_charno_to_actual_charno(
            cls,
            coq_charno: int,
            unicode_offsets: List[int]) -> int:
        """
        Convert a UTF-8 character index to a lexical character index.

        Parameters
        ----------
        coq_charno : int
            The index of a character in a UTF-8 encoded string, where
            each "character" is a byte.
        unicode_offsets : List[int]
            The number of bytes in excess of one of each non-ASCII
            UTF-8 character in the implicit string.

        Returns
        -------
        int
            The actual character index of the indicated byte
            irrespective of encoding.
        """
        # count the number of excess bytes appearing prior to the given
        # index
        excess_count = len(
            [
                cumulative_offset for cumulative_offset,
                offset in enumerate(unicode_offsets)
                if cumulative_offset + offset < coq_charno
            ])
        return coq_charno - excess_count

    @classmethod
    def find_comment(cls, s: str) -> Optional[Tuple[int, int]]:
        """
        Find the first comment block in the given string.

        Parameters
        ----------
        s : str
            A string, presumably a section of code.

        Returns
        -------
        Optional[Tuple[int, int]]
            None if there are no comment blocks, otherwise the indices
            of the beginning and end of of the detected comment.
        """
        m = cls.REGEX_COMMENT.fullmatch(s)
        if m is None:
            return None
        else:
            return m.start("com"), m.end("com")

    @classmethod
    def get_unicode_offsets(cls, code: str) -> List[int]:
        """
        Get the number of bytes each non-ASCII character needs in UTF-8.

        Parameters
        ----------
        code : str
            A section of code.

        Returns
        -------
        List[int]
            A list of indices, in ascending order, of each non-ASCII
            character in `code` repeated the number of bytes required to
            represent the character in UTF-8 in excess of one byte.
            For example, a unicode character located at index 5 that
            requires 3 bytes in UTF-8 would yield two ``5``s in a row in
            the returned list.
        """
        return [
            i for i in range(len(code))
            for _ in range(len(code[i].encode("UTF-8")) - 1)
            if not code[i].isascii()
        ]

    @classmethod
    def is_ws_or_comment(cls, s: str) -> bool:
        """
        Return whether the given string is whitespace or a comment.

        Parameters
        ----------
        s : str
            A string, presumably a section of code.

        Returns
        -------
        bool
            Whether the string is purely whitespace or a block comment
            (True) or not (False).
        """
        s_no_ws = s.strip()
        if len(s_no_ws) == 0:
            return True
        if s_no_ws[: 2] == "(*" and s_no_ws[-2 :] == "*)":
            return True

        return False
