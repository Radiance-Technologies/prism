"""
Provides quick parsing utilities relying on heuristics.
"""
import pathlib
import re
from typing import List, Union

from radpytools.os import pushd
from seutil import io

from prism.data.document import CoqDocument
from prism.data.sentence import VernacularSentence
from prism.language.gallina.parser import CoqParser

from .assertion import Assertion
from .util import ParserUtils, ParserUtilsSerAPI


class HeuristicParser:
    """
    A faster, less accurate parser that bypasses SerAPI.

    The main utility of this parser is to determine sentence and proof
    boundaries.
    This parser is not capable of extracting abstract syntax trees, nor
    is it guaranteed to yield correct results, especially in the
    presence of arbitrary grammar extensions.
    However, the parser will work on standalone Coq source files without
    requiring any compilation.

    Detection of tactics and proof starters is the main heuristic
    employed along with splitting utilities around sentence elements.
    Note that in the presence of nested proofs, the order of sentences
    is not preserved.
    The sentences corresponding to inner proof (and its theorem) nested
    within another are guaranteed to appear before the outer proof's
    sentences.
    """

    @classmethod
    def parse_proofs(
            cls,
            file_path: str,
            encoding: str = 'utf-8',
            glom_proofs: bool = True) -> List[Assertion]:
        """
        Extract proofs from the given file.

        Parameters
        ----------
        file_path : str
            The path to a Coq source file.
        encoding : str, optional
            The encoding to use for decoding if a bytestring is
            provided, by default 'utf-8'
        glom_proofs : bool, optional
            A flag indicating whether or not proofs should be re-glommed
            after sentences are split, by default `True`

        Returns
        -------
        List[Assertion]
            A list of proofs paired with their corresponding assertion
            statements.
        """
        raise NotImplementedError(
            "Heuristic proof extraction not yet implemented")

    @classmethod
    def parse_sentences(
            cls,
            file_path: str,
            encoding: str = 'utf-8',
            glom_proofs: bool = True) -> List[str]:
        """
        Split the Coq file text by sentences.

        An alternative interface for `HeuristicParser.parse_sentences`.

        Parameters
        ----------
        file_path : str
            The path to a Coq source file.
        encoding : str, optional
            The encoding to use for decoding if a bytestring is
            provided, by default 'utf-8'
        glom_proofs : bool, optional
            A flag indicating whether or not proofs should be re-glommed
            after sentences are split, by default `True`

        Returns
        -------
        List[str]
            A list of strings corresponding to Coq source file
            sentences, with proofs glommed (or not) depending on input
            flag.
        """
        return cls.parse_sentences_from_source(
            file_path,
            CoqParser.parse_source(file_path),
            encoding,
            glom_proofs)

    @classmethod
    def parse_sentences_from_source(
            cls,
            document_index: str,
            file_contents: Union[str,
                                 bytes],
            encoding: str = 'utf-8',
            glom_proofs: bool = True) -> List[str]:
        """
        Split the Coq file text by sentences.

        By default, proofs are then re-glommed into their own entries.
        This behavior can be switched off.

        Parameters
        ----------
        document_index : str
            A unique identifier for the document.
        file_contents : Union[str, bytes]
            Complete contents of the Coq source file, either in
            bytestring or string form.
        encoding : str, optional
            The encoding to use for decoding if a bytestring is
            provided, by default 'utf-8'
        glom_proofs : bool, optional
            A flag indicating whether or not proofs should be re-glommed
            after sentences are split, by default `True`

        Returns
        -------
        List[str]
            A list of strings corresponding to Coq source file
            sentences, with proofs glommed (or not) depending on input
            flag.
        """
        if isinstance(file_contents, bytes):
            file_contents = ParserUtils._decode_byte_stream(
                file_contents,
                encoding)
        file_contents_no_comments = ParserUtils._strip_comments(
            file_contents,
            encoding)
        # Split sentences by instances of single periods followed by
        # whitespace. Double (or more) periods are specifically
        # excluded.
        sentences = re.split(r"(?<!\.)\.\s", file_contents_no_comments)

        theorems: List[Assertion] = []
        result: List[str] = []
        i = 0
        while i < len(sentences):  # `sentences` length may change
            # Replace any whitespace or group of whitespace with a
            # single space.
            sentence = sentences[i]
            sentence = re.sub(r"(\s)+", " ", sentence)
            sentence = sentence.strip()
            if not sentence.endswith("."):
                sentence += "."
            (braces_and_bullets,
             sentence) = ParserUtils.split_braces_and_bullets(sentence)
            if ParserUtils.is_theorem_starter(sentence):
                # push new context onto stack
                assert not braces_and_bullets
                theorems.append(Assertion(sentence, False))
            elif ParserUtils.is_proof_starter(sentence):
                if not theorems:
                    theorems.append(Assertion(result[-1], True))
                theorems[-1].start_proof(sentence, braces_and_bullets)
            elif (ParserUtils.is_tactic(sentence)
                  or (theorems and theorems[-1].in_proof)):
                # split on ellipses
                new_sentences = re.split(r"\.\.\.", sentence)
                offset = len(new_sentences) - 1
                if offset > 0:
                    sentences[i : i + 1] = [
                        (s + "...") if j < offset else s for j,
                        s in enumerate(new_sentences)
                    ]
                    sentence = sentences[i]
                if not theorems:
                    theorems.append(Assertion(result[-1], True))
                theorems[-1].apply_tactic(sentence, braces_and_bullets)
            elif ParserUtils.is_proof_ender(sentence):
                theorems[-1].end_proof(sentence, braces_and_bullets)
                glom_proofs = Assertion.discharge(
                    document_index,
                    theorems.pop(),
                    result,
                    glom_proofs)
            else:
                # not a theorem, tactic, proof starter, or proof ender
                # discharge theorem stack
                glom_proofs = Assertion.discharge_all(
                    document_index,
                    theorems,
                    result,
                    glom_proofs)
                theorems = []
                if ParserUtils.is_program_starter(sentence):
                    # push new context onto stack
                    theorems.append(Assertion(None, True))
                assert not braces_and_bullets
                result.append(sentence)
            i += 1
        # End of file; discharge any remaining theorems
        Assertion.discharge_all(document_index, theorems, result, glom_proofs)
        # Lop off the final line if it's just a period, i.e., blank.
        if result[-1] == ".":
            result.pop()
        return result


class SerAPIParser:
    """
    SerAPI-based sentence extracter/parser.
    """

    @classmethod
    def parse_sentences_from_source(
            cls,
            document: CoqDocument,
            glom_proofs: bool = True) -> List[str]:
        """
        Extract sentences from a Coq document using SerAPI.

        Parameters
        ----------
        document : CoqDocument
            The document from which to extract sentences.
        glom_proofs : bool, optional
            A flag indicating whether or not proofs should be re-glommed
            after sentences are split, by default `True`

        Returns
        -------
        List[str]
            The resulting sentences from the document.

        Notes
        -----
        This function is stitched together from at least two methods
        originally found in roosterize:
        * prism.interface.command_line.CommandLineInterface.
            infer_serapi_options
        * prism.data.miner.DataMiner.extract_data_project
        """
        # Constants
        RE_SERAPI_OPTIONS = re.compile(r"-R (?P<src>\S+) (?P<tgt>\S+)")
        source_code = document.source_code
        coq_file = document.abspath
        # Try to infer from _CoqProject
        coq_project_files = [
            pathlib.Path(document.project_path) / "_CoqProject",
            pathlib.Path(document.project_path) / "Make"
        ]
        possible_serapi_options = []
        for coq_project_file in coq_project_files:
            if coq_project_file.exists():
                coq_project = io.load(coq_project_file, io.Fmt.txt)
                for line in coq_project.splitlines():
                    match = RE_SERAPI_OPTIONS.fullmatch(line.strip())
                    if match is not None:
                        possible_serapi_options.append(
                            f"-R {match.group('src')},{match.group('tgt')}")
                break

        if len(possible_serapi_options) > 0:
            serapi_options = " ".join(possible_serapi_options)
        else:
            serapi_options = ""
        with pushd(document.project_path):
            vernac_sentences, _, _ = CoqParser.parse_all(
                coq_file,
                source_code,
                serapi_options)
        sentences = cls.process_vernac_sentences(
            document.index,
            vernac_sentences,
            glom_proofs)
        return sentences

    @classmethod
    def process_vernac_sentences(
            cls,
            document_index: str,
            sentences: List[VernacularSentence],
            glom_proofs: bool) -> List[str]:
        """
        Process vernacular sentences into strings.

        Parameters
        ----------
        vernac_sentences : List[VernacularSentence]
            Lis of vernacular sentences to convert to strings
        glom_proofs : bool
            If True, glom proofs while processing the vernacular
            sentences into strings

        Returns
        -------
        List[str]
            Processed vernacular sentences
        """
        if not glom_proofs:
            return [vs.str_minimal_whitespace() for vs in sentences]
        else:
            theorems: List[Assertion[VernacularSentence]] = []
            result: List[Union[VernacularSentence, str]] = []
            i = 0
            while i < len(sentences):  # `sentences` length may change
                # Replace any whitespace or group of whitespace with a
                # single space.
                sentence = sentences[i]
                is_brace_or_bullet = ParserUtilsSerAPI.is_brace_or_bullet(
                    sentence)
                if ParserUtilsSerAPI.is_theorem_starter(sentence):
                    # push new context onto stack
                    assert not is_brace_or_bullet
                    theorems.append(
                        Assertion(
                            sentence,
                            False,
                            parser_utils_cls=ParserUtilsSerAPI))
                elif ParserUtilsSerAPI.is_proof_starter(sentence):
                    if not theorems:
                        theorems.append(
                            Assertion(
                                result[-1],
                                True,
                                parser_utils_cls=ParserUtilsSerAPI))
                    theorems[-1].start_proof(sentence, None)
                elif (ParserUtilsSerAPI.is_tactic(sentence)
                      or (theorems and theorems[-1].in_proof)):
                    if not theorems:
                        theorems.append(
                            Assertion(
                                result[-1],
                                True,
                                parser_utils_cls=ParserUtilsSerAPI))
                    theorems[-1].apply_tactic(sentence, [])
                elif ParserUtilsSerAPI.is_proof_ender(sentence):
                    theorems[-1].end_proof(sentence, [])
                    glom_proofs = Assertion.discharge(
                        document_index,
                        theorems.pop(),
                        result,
                        glom_proofs,
                        ParserUtilsSerAPI)
                else:
                    # not a theorem, tactic, proof starter, or proof
                    # ender discharge theorem stack
                    glom_proofs = Assertion[VernacularSentence].discharge_all(
                        document_index,
                        theorems,
                        result,
                        glom_proofs,
                        ParserUtilsSerAPI)
                    theorems = []
                    if ParserUtilsSerAPI.is_program_starter(sentence):
                        # push new context onto stack
                        theorems.append(
                            Assertion(
                                None,
                                True,
                                parser_utils_cls=ParserUtilsSerAPI))
                    assert not is_brace_or_bullet
                    result.append(sentence)
                i += 1
            # End of file; discharge any remaining theorems
            Assertion[VernacularSentence].discharge_all(
                document_index,
                theorems,
                result,
                glom_proofs,
                parser_utils_cls=ParserUtilsSerAPI)
            # Convert any remaining VernacularSentences in the result to
            # str
            result = [str(r) for r in result]
            # Lop off the final line if it's just a period, i.e., blank.
            if result[-1] == ".":
                result.pop()
            return result
