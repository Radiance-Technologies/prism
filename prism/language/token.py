"""
Abstractions for Coq lexical tokens.

Adapted from `roosterize.data.Token` at
https://github.com/EngineeringSoftware/roosterize/.
"""
from dataclasses import dataclass
from typing import Dict

from prism.language.id import LanguageId
from prism.util.radpytools.dataclasses import immutable_dataclass


class TokenConsts:
    """
    Collects constants related to lexical tokenization.
    """

    CONTENT_UNK = "<UNK>"

    KIND_PAD = "<PAD>"
    KIND_UNK = "<UNK>"
    KIND_ID = "ID"
    KIND_KEYWORD = "KW"
    KIND_SYMBOL = "SYM"
    KIND_NUMBER = "NUM"
    KIND_STR = "STR"
    KIND_COMMENT = "COM"
    KIND_STR_IN_COMMENT = "STR_in_COM"
    KIND_BOS = "<BOS>"
    KIND_EOS = "<EOS>"

    OFFSET_UNSET = -2
    OFFSET_INVALID = -1
    OFFSET_BOS = -3
    OFFSET_EOS = -4

    LOC_UNSET = -2
    LOC_INVALID = -1

    KINDS_EMBEDDINGS: Dict[str, int]
    KINDS_EMBEDDINGS = {
        KIND_PAD: 0,
        KIND_UNK: 1,
        KIND_ID: 2,
        KIND_KEYWORD: 3,
        KIND_SYMBOL: 4,
        KIND_NUMBER: 5,
        KIND_STR: 6,
        KIND_COMMENT: 7,
        KIND_BOS: 8,
        KIND_EOS: 9,
    }


@immutable_dataclass
class Spacing:
    """
    An abstraction of whitespace associated with a token.
    """

    loffset: int = TokenConsts.OFFSET_UNSET
    coffset: int = TokenConsts.OFFSET_UNSET
    indentation: int = TokenConsts.OFFSET_UNSET

    def __str__(self):
        """
        Get a condensed representation of the whitespace.
        """
        if self.coffset >= 0:
            return f"{self.coffset}s"
        else:
            return f"{self.loffset}l{self.indentation}s"

    def describe(self) -> str:
        """
        Get a human-readable description of the whitespace.

        Returns
        -------
        str
            A human-readable description of this `Spacing` object's
            associated whitespace.
        """
        if self.coffset >= 0:
            return f"{self.coffset} space(s)"
        else:
            return f"{self.loffset} newline(s) and {self.indentation} space(s)"


@dataclass
class Token:
    """
    A lexical token tagged with location and additional metadata.
    """

    content: str = TokenConsts.CONTENT_UNK
    kind: str = TokenConsts.CONTENT_UNK
    loffset: int = TokenConsts.OFFSET_UNSET
    coffset: int = TokenConsts.OFFSET_UNSET
    indentation: int = TokenConsts.OFFSET_UNSET

    lang_id: LanguageId = LanguageId.Unknown

    beg_charno: int = TokenConsts.LOC_UNSET
    end_charno: int = TokenConsts.LOC_UNSET
    lineno: int = TokenConsts.LOC_UNSET

    is_one_token_gallina: bool = False

    def apply_spacing(self, spacing: Spacing) -> None:
        """
        Set the spacing associated with this token to the given value.

        Parameters
        ----------
        spacing : Spacing
            The new spacing information for this token.
        """
        self.loffset = spacing.loffset
        self.coffset = spacing.coffset
        self.indentation = spacing.indentation

    def clear_naming(self) -> None:
        """
        Clear the contents of the token by setting it to be unknown.
        """
        self.content = TokenConsts.CONTENT_UNK

    def clear_spacing(self) -> None:
        """
        Unset the spacing information of the token.
        """
        self.loffset = TokenConsts.OFFSET_UNSET
        self.coffset = TokenConsts.OFFSET_UNSET
        self.indentation = TokenConsts.OFFSET_UNSET

    def get_space(self) -> str:
        """
        Get the whitespace associated with this token.

        Returns
        -------
        str
            The whitespace that precedes the token in the original text.
        """
        if self.coffset >= 0:
            return " " * self.coffset
        elif self.indentation >= 0:
            return "\n" * self.loffset + " " * self.indentation
        else:
            # Default spacing
            return " "
        # end if

    def get_spacing(self) -> Spacing:
        """
        Get the whitespace information associated with this token.

        Returns
        -------
        Spacing
            The whitespace for this token wrapped in a `Spacing` object.
        """
        return Spacing(self.loffset, self.coffset, self.indentation)

    def is_ignored(self) -> bool:
        """
        Return whether this kind of token should be ignored.

        Returns
        -------
        bool
            Whether this kind of token is considered to be an ignorable
            type (True) or not (False).
        """
        return self.kind not in [
            TokenConsts.KIND_ID,
            TokenConsts.KIND_NUMBER,
            TokenConsts.KIND_STR,
            TokenConsts.KIND_KEYWORD,
            TokenConsts.KIND_SYMBOL
        ]

    def str_with_space(self) -> str:
        """
        Get the token with appropriate preceding whitespace.

        Returns
        -------
        str
            This `Token`'s content prepended with ``self.get_space()``.
        """
        return self.get_space() + self.content
