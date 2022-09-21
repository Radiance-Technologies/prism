"""
Provides quick parsing utilities relying on heuristics.
"""
import pathlib
import re
import warnings
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple

from seutil import io

import prism.language.gallina.util as gu
from prism.data.document import CoqDocument
from prism.language.gallina.analyze import SexpAnalyzer, SexpInfo
from prism.language.gallina.parser import CoqParser
from prism.language.heuristic.str_with_location import StrWithLocation
from prism.util.iterable import CallableIterator, CompareIterator
from prism.util.radpytools.dataclasses import default_field
from prism.util.radpytools.os import pushd

from ..sexp.list import SexpList
from ..sexp.node import SexpNode
from ..sexp.string import SexpString
from .assertion import Assertion
from .util import ParserUtils


@dataclass
class CoqSentence:
    """
    A sentence in a Coq document.
    """

    text: str
    """
    The raw text of the sentence.

    Note that whitespace may not be preserved.
    """
    location: Optional[SexpInfo.Loc] = None
    """
    The location of the sentence in the original document.
    """
    ast: Optional[SexpNode] = None
    """
    The abstract syntax tree of the sentence.
    """

    def __len__(self) -> int:  # noqa: D105
        return len(self.text)

    def __str__(self) -> str:  # noqa: D105
        return self.text


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

    notation_mask = "<_nOtAtIoN_mAsK_>"
    """
    A sequence that is unlikely to occur in natural Coq code.

    This sequence is used to replace notation definitions.
    More precisely, it replaces the ``Notation "..."`` part of the
    sentence.
    """
    string_mask = "<_sTrInG_mAsK_>"
    """
    A sequence that is unlikely to occur in natural Coq code.

    This sequence is used to replace strings.
    More precisely, it replaces any non-empty sequence delimited by
    single double-quotes.
    """

    @dataclass
    class SentenceStatistics:
        """
        A collection of statistics regarding a document's sentences.

        Note that "statistics" is used somewhat loosely here.
        """

        depths: List[int] = default_field([])
        """
        The estimated depths of sentences within nested proof modes.
        """
        theorem_indices: Set[int] = default_field(set())
        """
        Indices of commands that potentially require proofs.
        """
        starter_indices: Set[int] = default_field(set())
        """
        Indices of commands that explicitly start a proof.
        """
        tactic_indices: Set[int] = default_field(set())
        """
        Indices of sentences corresponding to applied proof tactics.
        """
        ender_indices: List[int] = default_field([])
        """
        Indices of commands that explicitly end a proof.
        """
        program_indices: List[int] = default_field([])
        """
        Indices of program commands.
        """
        obligation_indices: List[int] = default_field([])
        """
        Indices of obligation commands.
        """
        proof_indices: Set[int] = default_field(set())
        """
        Indices of sentences that are unambiguously part of a proof.
        """
        query_indices: Set[int] = default_field(set())
        """
        Indices of commands that are effectively no-ops.
        """
        fail_indices: Set[int] = default_field(set())
        """
        Indices of commands that are expected to fail.

        For example, ``Fail Qed.`` would succeed if goals remain in the
        proof but will also not close the proof.
        """
        nesting_allowed: List[bool] = default_field([])
        """
        A sentence mask indicating where nested proofs are allowed.

        Note that certain commands that require proof are always
        allowed to be nested.
        """
        custom_tactics: Set[str] = default_field(set())
        """
        Custom tactics defined in the document via `Ltac` commands.
        """
        requirements: Set[str] = default_field(set())
        """
        Required modules and files in parsed file.
        """
        _depth: int = field(init=False)
        """
        The depth after the final recorded sentence.

        Satisfies invariant that it is always equal to or one less than
        the final element of ``self.depths``.
        """
        _max_proof_index: int = field(init=False)
        """
        The maximum sentence index of a proof element.

        Satisfies the invariant that it is always equal to the maximum
        of ``self.proof_indices``.
        """

        def __post_init__(self):  # noqa: D105
            self.depths = list(self.depths)
            self.theorem_indices = set(self.theorem_indices)
            self.starter_indices = set(self.starter_indices)
            self.tactic_indices = set(self.tactic_indices)
            self.ender_indices = list(self.ender_indices)
            self.program_indices = list(self.program_indices)
            self.obligation_indices = list(self.obligation_indices)
            self.query_indices = set(self.query_indices)
            self.fail_indices = set(self.fail_indices)
            self.nesting_allowed = list(self.nesting_allowed)
            self.custom_tactics = set(self.custom_tactics)
            assert self.starter_indices.issuperset(self.obligation_indices)
            assert self.theorem_indices.issuperset(self.program_indices)
            assert self.proof_indices.issuperset(self.tactic_indices)
            assert self.proof_indices.issuperset(self.theorem_indices)
            assert self.proof_indices.issuperset(self.starter_indices)
            assert self.proof_indices.issuperset(self.ender_indices)
            assert self.proof_indices.issuperset(self.program_indices)
            assert self.proof_indices.issuperset(self.obligation_indices)
            self._depth = self.depths[-1] if self.depths else 0
            self._max_proof_index = max(-1, -1, *self.proof_indices)

        @property
        def depth(self) -> int:
            """
            Get the depth after the final sentence.
            """
            return self._depth

        @property
        def max_proof_index(self) -> int:
            """
            Get the maximum sentence index of a proof element.
            """
            return self._max_proof_index

        @property
        def num_sentences(self) -> int:
            """
            Get the number of sentences in the document.
            """
            return len(self.depths)

        def _add_failure(self) -> None:
            """
            Record the occurrence of a ``Fail`` command.

            A Fail command is not otherwise recorded.

            Parameters
            ----------
            sentence_sans_attributes : str
                A sentence that explicitly starts a proof without any
                preceding modifiers or attributes.
            """
            self.fail_indices.add(self.num_sentences)
            self._increment_depth(0)

        def _add_proof_ender(self, sentence_sans_attributes: str) -> None:
            """
            Record the occurrence of a proof ender (e.g., ``Qed.``).

            Parameters
            ----------
            sentence_sans_attributes : str
                A sentence that explicitly starts a proof without any
                preceding modifiers or attributes.
            """
            index = self.num_sentences
            self.ender_indices.append(index)
            if ParserUtils.is_proof_starter(sentence_sans_attributes):
                self.starter_indices.add(index)
            self._increment_depth(-1)
            self._add_proof_index(index)

        def _add_proof_index(self, index: int) -> None:
            """
            Record a new proof index.

            Maintains the invariant for ``self._max_proof_index``.

            Parameters
            ----------
            index : int
                The index of a sentence that is unambiguously part of a
                proof.
            """
            self._max_proof_index = max(index, self._max_proof_index)
            self.proof_indices.add(index)

        def _add_proof_starter(self, sentence_sans_attributes: str) -> None:
            """
            Record the occurrence of a proof starter (e.g., ``Proof.``).

            Parameters
            ----------
            sentence_sans_attributes : str
                A sentence that explicitly starts a proof without any
                preceding modifiers or attributes.
            """
            depth_change = 0
            index = self.num_sentences
            self.starter_indices.add(index)
            is_obligation = ParserUtils.is_obligation_starter(
                sentence_sans_attributes)
            is_ender = ParserUtils.is_proof_ender(sentence_sans_attributes)
            if is_obligation:
                self.obligation_indices.append(index)
                depth_change = 1
                # update depths of commands between obligations
                if self._max_proof_index >= 0:
                    new_depth = self.depth + 1
                    for j in range(self._max_proof_index, index):
                        if self.depths[j] < new_depth:
                            self.depths[j] = new_depth
                self._max_proof_index = index
            if is_ender:
                self.ender_indices.append(index)
                depth_change = -1
            if is_obligation and is_ender:
                # both pre-increment and post-decrement.
                self._increment_depth(1)
                self._depth -= 1
            else:
                self._increment_depth(depth_change)
            self._add_proof_index(index)

        def _add_requirements(self, sentence_sans_attributes: str) -> None:
            """
            Record requirements given by sentence.

            Parameters
            ----------
            sentence_sans_attributes : str
                A sentence that defines required logical path(s).
            """
            new_reqs = ParserUtils.extract_requirements(
                sentence_sans_attributes)
            self.requirements = self.requirements.union(new_reqs)
            self._increment_depth(0)

        def _add_tactic(self) -> None:
            """
            Record the occurrence of a tactic in proof mode.
            """
            index = self.num_sentences
            self.tactic_indices.add(index)
            self._increment_depth(0)
            self._add_proof_index(index)

        def _add_theorem(
                self,
                sentence_sans_attributes: str,
                is_program: bool) -> None:
            """
            Record the occurrence of a "theorem" that may require proof.

            A "theorem" in this sence is any statement that can cause
            Coq to enter proof mode regardless of whether proof mode is
            in fact entered in a subsequent sentence.

            Parameters
            ----------
            sentence_sans_attributes : str
                A sentence that explicitly starts a proof without any
                preceding modifiers or attributes.
            is_program : bool
                Whether this sentence is adorned with a ``program``
                attribute.
            """
            index = self.num_sentences
            self.theorem_indices.add(index)
            if is_program:
                self.program_indices.append(index)
            self._increment_depth(1)
            self._add_proof_index(index)

        def _define_tactic(self, sentence_sans_attributes: str) -> None:
            """
            Record the definition of a custom tactic.

            Parameters
            ----------
            sentence_sans_attributes : str
                A sentence that explicitly starts a proof without any
                preceding modifiers or attributes.
            """
            self.custom_tactics.add(
                ParserUtils.extract_tactic_name(sentence_sans_attributes))
            self._increment_depth(0)

        def _increment_depth(self, sign: int) -> None:
            """
            Increment the depth for a new sentence.

            Maintains the invariant for ``self._depth``.

            Parameters
            ----------
            sign : int
                The sign of the increment as a negative, positive, or
                null (zero) integer.
            """
            if sign > 0:
                self._depth += 1
            self.depths.append(self._depth)
            if sign < 0:
                self._depth -= 1

        def add_sentence(self, sentence: str) -> None:
            """
            Update document statistics with the given sentence.

            Parameters
            ----------
            sentence : str
                An unaltered sentence from the document presumed to
                occur after any previously recorded sentence in the
                statistics.
            """
            sentence_sans_control = ParserUtils.strip_control(sentence)
            sentence_sans_attributes, attributes = ParserUtils.strip_attributes(
                sentence_sans_control)
            is_program = any(
                [ParserUtils.is_program_starter(a) for a in attributes])
            nested_proof_command = ParserUtils.sets_nested_proofs(
                sentence_sans_attributes)
            if nested_proof_command is not None:
                self.nesting_allowed.append(nested_proof_command)
                self._increment_depth(0)
            else:
                if self.nesting_allowed:
                    nesting_allowed = self.nesting_allowed[-1]
                else:
                    nesting_allowed = False
                self.nesting_allowed.append(nesting_allowed)
                if ParserUtils.is_fail(sentence):
                    self._add_failure()
                elif (ParserUtils.is_theorem_starter(sentence_sans_attributes)
                      or is_program):
                    self._add_theorem(sentence_sans_attributes, is_program)
                elif ParserUtils.is_proof_starter(sentence_sans_attributes):
                    self._add_proof_starter(sentence_sans_attributes)
                elif ParserUtils.is_proof_ender(sentence_sans_attributes):
                    self._add_proof_ender(sentence_sans_attributes)
                elif ParserUtils.defines_tactic(sentence_sans_attributes):
                    self._define_tactic(sentence_sans_attributes)
                elif ParserUtils.is_tactic(sentence_sans_attributes,
                                           self.custom_tactics):
                    self._add_tactic()
                elif ParserUtils.defines_requirement(sentence_sans_attributes):
                    self._add_requirements(sentence_sans_attributes)
                else:
                    if ParserUtils.is_query(sentence_sans_attributes):
                        index = self.num_sentences
                        self.query_indices.add(index)
                    self._increment_depth(0)

    @classmethod
    def _compute_proof_mask(
            cls,
            depths: List[int],
            ender_indices: List[int],
            program_indices: Set[int]) -> List[bool]:
        """
        Compute a mask indicating sentences that occur in proof mode.

        A sentence is considered to occur in proof mode if and only if
        it resides between a proof starter and proof ender at the same
        *true* level of nesting.

        Parameters
        ----------
        depths : List[int]
            The estimated depths of each sentence in the document within
            nested proof modes.
        ender_indices : List[int]
            Indices of sentences known to exit proof modes.
        program_indices : Set[int]
            Indices of sentences known to start programs.

        Returns
        -------
        proof_mask : List[bool]
            A Boolean value for each sentence in the document indicating
            whether the sentence occurs in proof mode or not.
        """
        max_index = len(depths) - 1
        ender_idx = CompareIterator(ender_indices, reverse=True)
        ender_depth_stack: List[int] = [max_index]
        proof_mask: List[bool] = []
        # Increases in depth in a forward iteration are not a reliable
        # indicator of deepening proof modes.
        for (i, depth) in enumerate(reversed(depths)):
            idx = max_index - i
            nesting_depth = len(ender_depth_stack) - 1
            if depth < ender_depth_stack[-1] and nesting_depth > 0:
                # we've exited a proof depth
                ender_depth_stack.pop()
                nesting_depth -= 1
            if idx == ender_idx:
                if (nesting_depth == 0 or depth > ender_depth_stack[-1]):
                    # we've entered a new proof depth
                    ender_depth_stack.append(depth)
            assert ender_depth_stack[0] == 0 or ender_depth_stack[-1] > 0
            proof_mask.append(
                depth >= ender_depth_stack[-1] or idx in program_indices)
        return list(reversed(proof_mask))

    @classmethod
    def _compute_sentence_statistics(
            cls,
            sentences: List[str]) -> SentenceStatistics:
        """
        Compute the statistics for the given sentences.

        Parameters
        ----------
        sentences : List[str]
            A sequence of sentences presumed to match the order of
            sentences extracted from a Coq document.

        Returns
        -------
        SentenceStatistics
            The statistics of the given sentences.
        """
        stats = HeuristicParser.SentenceStatistics()
        for sentence in sentences:
            stats.add_sentence(sentence)
        return stats

    @classmethod
    def _glom_proofs(
            cls,
            document_index: str,
            sentences: List[str],
            stats: SentenceStatistics) -> List[str]:
        """
        Process proofs such that each yields a single "sentence".

        The raw sentences comprising each proof are joined by spaces.
        Other sentences including theorem statements are unaffected.

        Parameters
        ----------
        document_index : str
            A unique identifier for the document.
        sentences : List[str]
            The sentences of the document.
        stats : SentenceStatistics
            Precomputed statistics for the given `sentences`.

        Returns
        -------
        List[str]
            The given `sentences` in the given order with two notable
            exceptions: (1) each block of sentences corresponding to a
            proof in the original list is replaced with a single `str`
            in the output; (2) nested proofs appear in the list before
            their enclosing proof.
        """
        result = []
        theorems: List[Assertion] = []
        # make theorem mask
        proof_mask = cls._compute_proof_mask(
            stats.depths,
            stats.ender_indices,
            set(stats.program_indices))
        ender_idx = CompareIterator(stats.ender_indices)
        obligation_idx = CompareIterator(stats.obligation_indices)
        program_idx = CompareIterator(stats.program_indices)
        for (i, (sentence, is_proof)) in enumerate(zip(sentences, proof_mask)):
            if not is_proof:
                if i in stats.tactic_indices or i in stats.starter_indices:
                    warnings.warn(
                        "Found an unterminated proof environment in "
                        f"{document_index}. ")
                result.append(sentence)
            elif i in stats.theorem_indices:
                theorems.append(
                    Assertion(document_index,
                              sentence,
                              i == program_idx))
            elif i == obligation_idx:
                theorems[-1].start_proof(sentence, [])
                if i in stats.ender_indices:
                    # either not a program or no more obligations
                    if (not theorems[-1].is_program
                            or obligation_idx.next >= program_idx.next):
                        Assertion.discharge(
                            document_index,
                            theorems.pop(),
                            result,
                            True)
            elif i == ender_idx:
                if i in stats.starter_indices:
                    theorems[-1].start_proof(sentence, [])
                else:
                    theorems[-1].end_proof(sentence, [])
                # either not a program or no more obligations
                if (not theorems[-1].is_program
                        or obligation_idx.next >= program_idx.next):
                    Assertion.discharge(
                        document_index,
                        theorems.pop(),
                        result,
                        True)
            elif theorems:
                theorems[-1].apply_tactic(sentence, [])
            else:
                theorems.append(Assertion(document_index, sentence, False))
        Assertion.discharge_all(document_index, theorems, result, True)
        return result

    @classmethod
    def _get_sentences(cls, file_contents: str) -> List['StrWithLocation']:
        """
        Get the sentences of the given file.

        Parameters
        ----------
        file_contents : str
            The contents of a Coq document.

        Returns
        -------
        List['StrWithLocation']
            The sentences of the Coq document.
        """
        located_file_contents = StrWithLocation.create_from_file_contents(
            file_contents)
        # Remove comments
        file_contents_no_comments = ParserUtils._strip_comments(
            located_file_contents)
        # Mask notations to avoid accidental splitting on quoted
        # periods.
        notations = re.findall(r"Notation\s+\".*\"", file_contents_no_comments)
        file_contents_no_comments = StrWithLocation.re_sub(
            r"Notation \".*\"",
            cls.notation_mask,
            file_contents_no_comments)
        # Mask strings to avoid accidental splitting on quoted periods.
        strings = re.findall(r"\".*\"", file_contents_no_comments)
        file_contents_no_comments = StrWithLocation.re_sub(
            r"Notation \".*\"",
            cls.string_mask,
            file_contents_no_comments)
        # Split sentences by instances of single periods followed by
        # whitespace. Double (or more) periods are specifically
        # excluded.
        # Ellipses will be handled later.
        # Due to the parenthetical grouping, this split keeps the period
        # characters as separate items between each pair of sentences.
        sentences = StrWithLocation.re_split(
            r"(?<!\.)(\.\s)",
            file_contents_no_comments)
        # Now perform further splitting of braces, bullets, and ellipses
        i = 0
        notation_it = iter(notations)
        # re.sub will pull from this automatically to make substitutions
        string_it = CallableIterator(strings)
        processed_sentences: List[StrWithLocation] = []
        while i < len(sentences):  # `sentences` length may change
            # Replace any whitespace or group of whitespace with a
            # single space.
            sentence = sentences[i]
            # If the sentence is whitespace only, skip it.
            if not sentence.strip():
                i += 1
                continue
            # If the sentence is just a period, skip it
            if re.match(r"\.\s", sentence):
                i += 1
                continue
            sentence = StrWithLocation.re_sub(r"(\s)+", " ", sentence)
            sentence = sentence.strip()
            # restore periods
            if not sentence.endswith("."):
                period = sentences[i + 1][0]
                assert str(period) == "."
                sentence += period
            # split braces and bullets
            (braces_and_bullets,
             sentence) = ParserUtils.split_braces_and_bullets(sentence)
            # split on ellipses
            new_sentences = StrWithLocation.re_split(r"(\.\.\.)", sentence)
            new_new_sentences = []
            for j, new_sentence in enumerate(new_sentences):
                if not new_sentence or new_sentence == "...":
                    continue
                elif (j < len(new_sentences) - 1
                      and new_sentences[j + 1] == "..."):
                    # Restore the ellipsis if one is present
                    new_new_sentences.append(
                        new_sentence + new_sentences[j + 1])
                else:
                    new_new_sentences.append(new_sentence)
            num_new = len(new_new_sentences) - 1
            if num_new > 0:
                sentences[i : i + 1] = new_new_sentences
                sentence = sentences[i]
            sentence_sans_control = ParserUtils.strip_control(sentence)
            sentence_sans_attributes, _ = ParserUtils.strip_attributes(
                sentence_sans_control)
            # restore notation
            if sentence_sans_attributes.startswith(cls.notation_mask):
                sentence = StrWithLocation.re_sub(
                    cls.notation_mask,
                    next(notation_it),
                    sentence)
            # restore strings
            sentence = StrWithLocation.re_sub(
                cls.string_mask,
                string_it,
                sentence)
            processed_sentences.extend(braces_and_bullets)
            processed_sentences.append(sentence)
            i += 1
        # Lop off the final line if it's just a period, i.e., blank.
        if processed_sentences[-1] == ".":
            processed_sentences.pop()
        return processed_sentences

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
    def parse_sentences_from_file(
            cls,
            file_path: str,
            encoding: str = 'utf-8',
            glom_proofs: bool = True,
            project_path: str = "",
            return_locations: bool = False,
            **kwargs) -> List[CoqSentence]:
        """
        Split the Coq file text by sentences.

        An alternative interface for `HeuristicParser.parse_sentences`.

        Parameters
        ----------
        file_path : str
            The path to a Coq source file.
        encoding : str, optional
            The encoding to use for decoding if a bytestring is
            provided, by default 'utf-8'.
        glom_proofs : bool, optional
            A flag indicating whether or not proofs should be re-glommed
            after sentences are split, by default `True`. If glom_proofs
            is True, return_locations is set to False no matter the
            given value.
        project_path : str, optional
            Path to the project this file is from, by default "".
        return_locations : bool, optional
            A flag indicating whether sentence locations are returned,
            by default False. If glom_proofs is True, locations are not
            returned no matter what.
        kwargs : Dict[str, Any]
            Optional keyword arguments to
            `parse_sentences_from_document`.

        Returns
        -------
        List[CoqSentence]
            A list of the sentences in the file.
        """
        document = CoqDocument(
            file_path,
            CoqParser.parse_source(file_path),
            project_path=project_path)
        return cls.parse_sentences_from_document(
            document,
            encoding,
            glom_proofs,
            return_locations,
            **kwargs)

    @classmethod
    def parse_sentences_from_document(
            cls,
            document: CoqDocument,
            encoding: str = 'utf-8',
            glom_proofs: bool = True,
            return_locations: bool = False,
            **kwargs) -> List[CoqSentence]:
        """
        Split the Coq file text by sentences.

        By default, proofs are then re-glommed into their own entries.
        This behavior can be switched off.

        Parameters
        ----------
        document : str
            CoqDocument to be parsed.
        encoding : str, optional
            The encoding to use for decoding if a bytestring is
            provided, by default 'utf-8'.
        glom_proofs : bool, optional
            A flag indicating whether or not proofs should be re-glommed
            after sentences are split, by default `True`. If glom_proofs
            is True, return_locations is set to False no matter the
            given value.
        return_locations : bool, optional
            A flag indicating whether sentence locations are returned,
            by default False. If glom_proofs is True, locations are not
            returned no matter what.
        kwargs : Dict[str, Any]
            Optional keyword arguments for subclass implementations.

        Returns
        -------
        List[CoqSentence]
            A list of the sentences in the `document`.
        """
        if glom_proofs and return_locations:
            raise NotImplementedError(
                "Returning locations alongside glommed proofs "
                "is not currently supported.")
        file_contents = document.source_code
        sentences = cls._get_sentences(file_contents)
        if return_locations:
            start_idx = 0
            newlines_so_far = 0
            located_sentences: List[CoqSentence] = []
            for ls in sentences:
                loc = ls.get_location(
                    file_contents,
                    document.abspath,
                    start_idx,
                    newlines_so_far)
                located_sentences.append(CoqSentence(str(ls), loc))
                start_idx = loc.end_charno
                newlines_so_far = loc.lineno_last
            sentences = located_sentences
        else:
            sentences = [str(s) for s in sentences]
            if glom_proofs:
                stats = cls._compute_sentence_statistics(sentences)
                sentences = cls._glom_proofs(document.index, sentences, stats)
            sentences = [CoqSentence(s) for s in sentences]
        return sentences


class SerAPIParser(HeuristicParser):
    """
    SerAPI-based sentence extracter/parser.
    """

    RE_SERAPI_OPTIONS = re.compile(r"-R (?P<src>\S+) (?P<tgt>\S+)")

    @classmethod
    def _glom_ltac(
        cls,
        vernac_sentences: List[str],
        sexp_asts: List[SexpNode],
        locations: List[SexpInfo.Loc],
    ) -> Tuple[List[str],
               List[SexpNode],
               List[SexpInfo.Loc]]:
        """
        Combine contiguous Ltac sentences together.

        Parameters
        ----------
        vernac_sentences : List[str]
            List of vernacular sentences from a document.
        sexp_asts : List[SexpNode]
            List of s-expression ASTs for each vernacular sentence
            in `vernac_sentences`.
        locations : List[SexpInfo.Loc]
            List of locations for each sentence in `vernac_sentences`.

        Returns
        -------
        List[str]
            The given list of vernacular sentences with contiguous
            spans of Ltac sentences combined into one "sentence".
        List[SexpNode]
            The given list of ASTs with contiguous spans of Ltac ASTs
            combined into a single "AST" under a placeholder
            ``"glommed_ltac"`` type (node).
        List[SexpInfo.Loc]
            The given list of locations with contiguous spans of Ltac
            sentence locations merged into one location.
        """
        sentences = []
        asts = []
        locs = []
        in_ltac_region = False
        for sentence, ast, loc in zip(vernac_sentences, sexp_asts, locations):
            if SexpAnalyzer.is_ltac(ast):
                if not in_ltac_region:
                    # Enter ltac region and create empty buffers
                    in_ltac_region = True
                    ltac_sentences = []
                    ltac_asts = [SexpString("glommed_ltac")]
                    ltac_locs = []
                # Add Ltac sentence and ast to buffers
                ltac_sentences.append(sentence)
                ltac_asts.append(ast)
                ltac_locs.append(loc)
            else:
                if in_ltac_region:
                    # Join sentences by a space
                    ltac_sentences = ' '.join(ltac_sentences)
                    # Create a single node containing all
                    # contigous Ltac asts.
                    ltac_asts = SexpList(ltac_asts)
                    # Merge the contiguous sentence locations
                    ltac_locs = SexpInfo.Loc.span(*ltac_locs)
                    # Exit ltac region
                    in_ltac_region = False
                    sentences.append(ltac_sentences)
                    asts.append(ltac_asts)
                    locs.append(ltac_locs)
                # pair sentence with ast node.
                sentences.append(sentence)
                asts.append(ast)
                locs.append(loc)
        return sentences, asts, locs

    @classmethod
    def _infer_serapi_options(cls, document: CoqDocument) -> str:
        """
        Try to infer SerAPI options from a _CoqProject file if present.
        """
        coq_project_files = [
            pathlib.Path(document.project_path) / "_CoqProject",
            pathlib.Path(document.project_path) / "Make"
        ]
        possible_serapi_options = []
        for coq_project_file in coq_project_files:
            if coq_project_file.exists():
                coq_project = io.load(coq_project_file, io.Fmt.txt)
                for line in coq_project.splitlines():
                    match = cls.RE_SERAPI_OPTIONS.fullmatch(line.strip())
                    if match is not None:
                        possible_serapi_options.append(
                            f"-R {match.group('src')},{match.group('tgt')}")
                break

        if len(possible_serapi_options) > 0:
            serapi_options = " ".join(possible_serapi_options)
        else:
            serapi_options = ""
        return serapi_options

    @classmethod
    def parse_sentences_from_document(
            cls,
            document: CoqDocument,
            _encoding: str = "utf-8",
            glom_proofs: bool = True,
            return_locations: bool = False,
            glom_ltac: bool = False,
            return_asts: bool = False,
            offset_locs: bool = True,
            **kwargs) -> List[CoqSentence]:
        """
        Extract sentences from a Coq document using SerAPI.

        Parameters
        ----------
        document : CoqDocument
            The document from which to extract sentences.
        _encoding : str, optional
            Ignore, by default "utf-8".
        glom_proofs : bool, optional
            A flag indicating whether or not proofs should be re-glommed
            after sentences are split, by default `True`.
        return_locations : bool, optional
            Currently ignored, by default False.
        glom_ltac : bool, optional
            Glom together contiguous regions of Ltac code,
            by default `False`.
        return_asts : bool, optional
            If True, then also return asts. By default `False`.
        offset_locs : bool, optional
            If True, then offset the locations in the returned ASTs to
            match the indices of characters in the returned sentences.
            If False, then the locations in the ASTs will instead match
            the indices of bytes in an encoded bytestring of the file.
        kwargs : Dict[str, Any]
            Optional keyword arguments to `CoqParser.parse_asts`, such
            as `opam_switch` or `serapi_options`.

        Returns
        -------
        sentences : List[CoqSentence]
            The resulting sentences from the document.

        Raises
        ------
        ValueError
            If `glom_proofs` and `glom_ltac` are both True.
        """
        if glom_ltac and glom_proofs:
            raise ValueError(
                "'glom_proofs' and 'glom_ltac' cannot both be True at the same time."
            )
        if glom_proofs and return_asts:
            raise NotImplementedError(
                "Returning ASTs alongside glommed proofs is not currently supported."
            )
        if glom_proofs and return_locations:
            raise NotImplementedError(
                "Returning locations alongside glommed proofs "
                "is not currently supported.")
        source_code = document.source_code
        unicode_offsets = gu.ParserUtils.get_unicode_offsets(source_code)
        coq_file = document.abspath
        serapi_options = kwargs.pop('serapi_options', None)
        if serapi_options is None:
            # Try to infer from _CoqProject
            serapi_options = cls._infer_serapi_options(document)
        with pushd(document.project_path):
            asts = CoqParser.parse_asts(coq_file, serapi_options, **kwargs)
        # get raw sentences
        sentences = []
        locs = []
        for ast in asts:
            loc: SexpInfo.Loc = SexpInfo.Loc.span(
                *SexpAnalyzer.get_locs(ast,
                                       unicode_offsets))
            sentences.append(source_code[loc.beg_charno : loc.end_charno])
            locs.append(loc)
        if glom_ltac:
            sentences, asts, locs = cls._glom_ltac(sentences, asts, locs)
        if glom_proofs:
            stats = cls._compute_sentence_statistics(sentences)
            sentences = cls._glom_proofs(document.index, sentences, stats)
        sentences = [CoqSentence(s) for s in sentences]
        if return_asts:
            for s, ast in zip(sentences, asts):
                if offset_locs:
                    ast = SexpAnalyzer.offset_locs(ast, unicode_offsets)
                s.ast = ast
        if return_locations:
            for s, loc in zip(sentences, locs):
                s.location = loc
        return sentences
