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
Provides an enumeration of recognized languages.

Adapted from `roosterize.data.LanguageID`
at https://github.com/EngineeringSoftware/roosterize/.
"""

from enum import Enum


class LanguageId(Enum):
    """
    Enumerates "languages" that occur in Coq source code.
    """

    Unknown = -1
    Vernac = 1
    Gallina = 2
    Ltac = 3
    Comment = 4

    # code-mixed lids are only assigned on sentences but not tokens
    LtacMixedWithGallina = 11
    VernacMixedWithGallina = 12

    def __repr__(self):  # noqa : D105
        return {
            LanguageId.Unknown: "UNK",
            LanguageId.Vernac: "V",
            LanguageId.Gallina: "G",
            LanguageId.Ltac: "L",
            LanguageId.Comment: "C",
            LanguageId.LtacMixedWithGallina: "LG",
            LanguageId.VernacMixedWithGallina: "VG",
        }[self]

    def __str__(self):  # noqa : D105
        return self.__repr__()

    @property
    def base_lid(self) -> "LanguageId":
        """
        Get the base language ID.

        Returns
        -------
        LanguageID
            The base lid of a code-mixed lid.
            If self is not a code-mixed lid, returns self.
        """
        if self == LanguageId.LtacMixedWithGallina:
            return LanguageId.Ltac
        elif self == LanguageId.VernacMixedWithGallina:
            return LanguageId.Vernac
        else:
            return self
