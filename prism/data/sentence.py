"""
Defines Coq sentence abstractions and associated utilities.

Adapted from `roosterize.data.CoqDocument`
at https://github.com/EngineeringSoftware/roosterize/.
"""
import copy
from dataclasses import dataclass
from typing import List, Optional

from ..language.id import LanguageId
from ..language.token import Token


@dataclass
class VernacularSentence:
    """
    Class for representing Coq sentences.

    Attributes
    ----------
    tokens : Optional[List[Token]]
        List of tokens present in the sentence
    """

    tokens: Optional[List[Token]] = None

    def __copy__(self):
        """
        Produce a copy of this VernacularSentence object.

        Returns
        -------
        VernacularSentence
            Copy of the current object
        """
        return VernacularSentence(tokens=copy.deepcopy(self.tokens),)

    def classify_lid(self) -> LanguageId:
        """
        Discover the Language this sentence is in.

        Returns
        -------
        LanguageId
            The language the sentence is in
        """
        if all([t.lang_id == LanguageId.Comment for t in self.tokens]):
            return LanguageId.Comment
        if any([t.lang_id == LanguageId.Ltac for t in self.tokens]):
            if any([t.lang_id == LanguageId.Gallina
                    and not t.is_one_token_gallina for t in self.tokens]):
                return LanguageId.LtacMixedWithGallina
            else:
                return LanguageId.Ltac
            # end if
        elif any([t.lang_id == LanguageId.Gallina and not t.is_one_token_gallina
                  for t in self.tokens]):
            return LanguageId.VernacMixedWithGallina
        else:
            return LanguageId.Vernac
        # end if

    def str_with_space(self) -> str:
        """
        Get a string representation of the tokens in the sentence.

        Returns
        -------
        str
            String representation of tokens in sentence
        """
        return "".join([t.str_with_space() for t in self.tokens])
