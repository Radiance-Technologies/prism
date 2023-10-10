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
Module defining classes to reflect data in Coq documents.

Adapted from `roosterize.data.CoqDocument`
at https://github.com/EngineeringSoftware/roosterize/.
"""
import copy
import os
import pathlib
from dataclasses import dataclass
from functools import cached_property
from typing import List, Optional

from prism.data.vernac_sentence import VernacularSentence
from prism.interface.coq.options import SerAPIOptions
from prism.language.gallina.util import ParserUtils
from prism.language.sexp import SexpNode
from prism.language.token import Token
from prism.util.radpytools import PathLike


@dataclass
class CoqDocument:
    """
    Class reflecting Coq document data.
    """

    name: PathLike = ""
    """
    Path to file containing document relative to the project folder.
    """
    source_code: str = ""
    """
    Contents of the file, either in string or byte-string form.
    """
    project_path: Optional[PathLike] = None
    """
    The path to the project whence comes the file or None if this
    document is not part of a project.
    """
    revision: Optional[str] = None
    """
    String identifying the commit of the project from which the file
    originates or None if this file's project is None or not a
    repository.
    """
    sentences: Optional[List[VernacularSentence]] = None
    """
    A list of sentences (which are lists of tokens) from this Coq
    document
    """
    ast_sexp_list: Optional[List[SexpNode]] = None
    """
    A list of s-expression nodes representing the ASTs of
    sentences in the order of their definition in the document.
    """
    tok_sexp_list: Optional[List[SexpNode]] = None
    """
    A list of s-expression nodes representing the sequences of
    lexical tokens in each sentence in the order of their
    definition in the document.
    """
    serapi_options: Optional[SerAPIOptions] = None
    """
    The SerAPI options for parsing this file.
    """

    def __post_init__(self) -> None:
        """
        Ensure paths are strings.
        """
        name = self.name
        if not isinstance(name, str):
            self.name = str(name)
        project_path = self.project_path
        if project_path is not None and not isinstance(project_path, str):
            self.project_path = str(project_path)

    def __repr__(self) -> str:
        """
        Construct a representation of the Coq document for debugging.

        Returns
        -------
        str
            The debug representation of the Coq document
        """
        num_sentences = len(
            self.sentences) if self.sentences is not None else 'None'
        num_tokens = len(
            [t for sent in self.sentences
             for t in sent.tokens]) if self.sentences is not None else 'None'
        s = f"File: {self.name}\n"
        s += f"Project: {self.project_name}\n"
        s += f"Revision: {self.revision}\n"
        s += f"#sentences: {num_sentences}\n"
        s += f"#tokens: {num_tokens}\n"
        s += "\n"

        if self.sentences is not None:
            for sent in self.sentences:
                for t in sent.tokens:
                    s += (
                        f"<{t.content}:{repr(t.lang_id)}"
                        f"{'ot' if t.is_one_token_gallina else ''}"
                        f":{t.kind}:{t.loffset}:{t.coffset}:{t.indentation}> ")
                s += "\n"

        return s

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
    def project_path_(self) -> PathLike:
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

    @cached_property
    def unicode_offsets(self) -> List[int]:
        """
        Get offsets of unicode characters from the start of the file.

        Returns
        -------
        List[int]
            The unicode offsets.

        See Also
        --------
        ParserUtils.get_unicode_offsets
        """
        return ParserUtils.get_unicode_offsets(self.source_code)

    def get_all_tokens(self) -> List[Token]:
        """
        Get a list of all tokens in the Coq document.

        Returns
        -------
        List[Token]
            List of tokens in the Coq document
        """
        return [t for s in self.sentences
                for t in s.tokens] if self.sentences is not None else []

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
            source_code=self.source_code,
            serapi_options=copy.deepcopy(self.serapi_options))

    def str_with_space(self) -> str:
        """
        Get a string representation of all tokens in Coq document.

        Returns
        -------
        str
            String representation of all tokens in the Coq document
        """
        return "".join(
            [s.str_with_space()
             for s in self.sentences]) if self.sentences is not None else ""
