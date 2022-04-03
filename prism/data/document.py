"""
Module defining classes to reflect data in Coq documents.
"""
import copy
import os
import pathlib
from dataclasses import dataclass
from typing import List, Optional

from prism.data.Token import Token
from prism.parser.sexp import SexpNode

from .sentence import VernacularSentence


@dataclass
class CoqDocument:
    """
    Class reflecting Coq document data.

    Attributes
    ----------
    name : str
        Path to file containing document relative to the project folder.
    project_path : str or None
        The path to the project whence comes the file or None if this
        document is not part of a project.
    revision : str or None
        String identifying the commit of the project from which the file
        originates or None if this file's project is None or not a
        repository.
    source_code : str or bytes
        Contents of the file, either in string or byte-string form.
    sentences : Optional[List[VernacularSentence]]
        A list of sentences (which are lists of tokens) from this Coq
        document
    ast_sexp_lists : List[SexpNode]
        A list of s-expression nodes representing the ASTs of
        sentences in the order of their definition in the document.
    tok_sexp_lists : List[SexpNode]
        A list of s-expression nodes representing the sequences of
        lexical tokens in each sentence in the order of their
        definition in the document.
    """

    name: str = ""
    source_code: str = ""
    project_path: Optional[str] = None
    revision: Optional[str] = None
    sentences: Optional[List[VernacularSentence]] = None
    ast_sexp_lists: Optional[List[SexpNode]] = None
    tok_sexp_lists: Optional[List[SexpNode]] = None

    @property
    def abspath(self) -> str:
        """
        Get the absolute path of the document.
        """
        return os.path.abspath(os.path.join(self.project_path_, self.name))

    @property
    def index(self) -> str:
        """
        Get an index that uniquely identifies the document.

        The index combines the project name, revision, and file name.

        Returns
        -------
        str
            The index of the file.
        """
        return f"{self.project_name}@{self.revision}/{self.name}"

    @property
    def project_path_(self) -> str:
        """
        Get the path to the project or the empty string if None.
        """
        return self.project_path if self.project_path is not None else ""

    @property
    def project_name(self) -> str:
        """
        Get the name of the project or the empty string if None.
        """
        return pathlib.Path(self.project_path_).stem

    def get_all_tokens(self) -> List[Token]:
        """
        Get a list of all tokens in the Coq document.

        Returns
        -------
        List[Token]
            List of tokens in the Coq document
        """
        return [t for s in self.sentences for t in s.tokens]

    def __copy__(self):
        """
        Produce a copy of this CoqDocument object.

        Returns
        -------
        CoqDocument
            Copy of the current object
        """
        return CoqDocument(
            sentences=copy.deepcopy(self.sentences),
            name=self.name,
            project_path=self.project_path,
            revision=self.revision,
            source_code=self.source_code)

    def debug_repr(self) -> str:
        """
        Construct a representation of the Coq document for debugging.

        Returns
        -------
        str
            The debug representation of the Coq document
        """
        s = f"File: {self.name}\n"
        s += f"Project: {self.project_name}\n"
        s += f"Revision: {self.revision}\n"
        s += f"#sentences: {len(self.sentences)}\n"
        s += f"#tokens: {len([t for sent in self.sentences for t in sent.tokens])}\n"
        s += "\n"

        for sent in self.sentences:
            for t in sent.tokens:
                s += (
                    f"<{t.content}:{t.lang_id.debug_repr()}"
                    f"{'ot' if t.is_one_token_gallina else ''}"
                    f":{t.kind}:{t.loffset}:{t.coffset}:{t.indentation}> ")
            # end for
            s += "\n"
        # end for

        return s

    def str_with_space(self) -> str:
        """
        Get a string representation of all tokens in Coq document.

        Returns
        -------
        str
            String representation of all tokens in the Coq document
        """
        return "".join([s.str_with_space() for s in self.sentences])
