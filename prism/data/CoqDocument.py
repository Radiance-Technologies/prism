"""
Module defining classes to reflect data in Coq documents.
"""
import copy
from dataclasses import dataclass
from typing import List, Optional

from prism.data.LanguageId import LanguageId
from prism.data.Token import Token


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


@dataclass
class CoqDocument:
    """
    Class reflecting Coq document data.

    Attributes
    ----------
    sentences : Optional[List[VernacularSentence]]
        A list of sentences (which are lists of tokens) from this Coq
        document
    file_name : str
        Path to file containing document relative to the project folder
    project_name : str
        The name of the project whence comes the file
    revision : str
        String identifying a commit
    abspath : str
        Absolute path to the file
    file_contents : str or bytes
        Contents of the file, either in string or byte-string form
    """

    sentences: Optional[List[VernacularSentence]] = None
    file_name: str = ""
    project_name: str = ""
    revision: str = ""
    abspath: str = ""
    source_code: str = ""

    def get_all_tokens(self) -> List[Token]:
        """
        Get a list of all tokens in the Coq document.

        Returns
        -------
        List[Token]
            List of tokens in the Coq document
        """
        return [t for s in self.sentences for t in s.tokens]

    def get_data_index(self) -> str:
        """
        Combine the project name and file name.

        Returns
        -------
        str
            Relative path to Coq file prepended by project name
        """
        return f"{self.project_name}/{self.file_name}"

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
            file_name=self.file_name,
            project_name=self.project_name,
            revision=self.revision,
            abspath=self.abspath,
            source_code=self.source_code)

    def debug_repr(self) -> str:
        """
        Construct a representation of the Coq document for debugging.

        Returns
        -------
        str
            The debug representation of the Coq document
        """
        s = f"File: {self.file_name}\n"
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
