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
Defines Coq sentence abstractions and associated utilities.

Adapted from `roosterize.data.CoqDocument`
at https://github.com/EngineeringSoftware/roosterize/.
"""
import copy
import re
from dataclasses import dataclass
from typing import List

from prism.util.radpytools.dataclasses import default_field

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

    tokens: List[Token] = default_field(list())

    def __copy__(self):
        """
        Produce a copy of this VernacularSentence object.

        Returns
        -------
        VernacularSentence
            Copy of the current object
        """
        return VernacularSentence(
            tokens=copy.deepcopy(self.tokens),
        )

    def __str__(self) -> str:
        """
        Return the minimal `str` representation of the sentence.

        Returns
        -------
        str
            String repr of the sentence
        """
        return self.str_minimal_whitespace()

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

    def concat(self, *others: 'VernacularSentence') -> 'VernacularSentence':
        """
        Concatenate this sentence with another.

        Returns
        -------
        VernacularSentence
            A sentence comprising the tokens of this sentence followed
            by the tokens of the provided sentences in order of their
            appearance.
        """
        tokens = list(self.tokens)
        for other in others:
            tokens.extend(other.tokens)
        return VernacularSentence(tokens)

    def str_with_space(self) -> str:
        """
        Get a string representation of the tokens in the sentence.

        Returns
        -------
        str
            String representation of tokens in sentence
        """
        return "".join([t.str_with_space() for t in self.tokens]).strip()

    def str_minimal_whitespace(self) -> str:
        """
        Get a string repr of the sentence with minimal whitespace.

        Returns
        -------
        str
            String representation of tokens in sentence
        """
        return re.sub(r"(\s)+", " ", self.str_with_space()).strip()
