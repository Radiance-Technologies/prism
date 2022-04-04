"""
Provides an enumeration of recognized languages.
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

    def debug_repr(self) -> str:
        """
        Get a representation of the language ID for debug messages.
        """
        return self.__repr__()
