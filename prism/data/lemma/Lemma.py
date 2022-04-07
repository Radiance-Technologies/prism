"""
Defines abstractions for Coq lemmas and theorems.
"""

from dataclasses import dataclass
from typing import List

from prism.language.sexp import SexpNode
from prism.language.token import Token


@dataclass
class Lemma:
    """
    A Coq definition corresponding to a lemma or theorem statement.
    """

    data_index: str = ""

    vernac_command: List[Token] = None
    name: str = ""
    qname: str = ""

    statement: List[Token] = None
    ast_sexp: SexpNode = None
    backend_sexp: SexpNode = None

    uid: int = -1  # Used only for indexing in this dataset

    def __repr__(self):  # noqa : D105
        return self.__str__()

    def __str__(self):  # noqa: D105
        s = ""
        s += f"data_index: {self.data_index}\n"
        s += f"name: {self.name}\n"
        s += f"qname: {self.qname}\n"
        s += f"vernac_command: {self.vernac_command_with_space()}\n"
        s += f"statement: {self.statement_with_space()}\n"
        return s

    def statement_with_space(self) -> str:
        """
        Get the lemma statement as a string.
        """
        return ''.join([t.str_with_space() for t in self.statement])

    def vernac_command_with_space(self) -> str:
        """
        Get the full command associated with the lemma as a string.
        """
        return ''.join([t.str_with_space() for t in self.vernac_command])
