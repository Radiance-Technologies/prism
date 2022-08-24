"""
Provides internal utilities for heuristic parsing of Coq source files.
"""

import re
from dataclasses import dataclass
from functools import partialmethod
from typing import Iterable, List, Optional, Set, Tuple, Union

from prism.language.gallina.analyze import SexpInfo
from prism.util.re import regex_from_options


class ParserUtils:
    """
    Namespace for utilities for heuristic parsing.

    Provides functions for splitting sentence elements.
    """

    obligation_starters = {
        "Next Obligation",
        "Solve Obligation",
        "Solve All Obligations",
        "Obligation",
    }
    """
    Special proof environments associated with Programs.

    See Also
    --------
    ParserUtils.program_starters : For more about ``Program`` commands.
    """
    proof_starters = regex_from_options(
        {
            "Proof",
            "Admitted",
            "Abort",
        }.union(obligation_starters),
        True,
        False)
    """
    Vernacular commands that signal the begining of proof mode.

    See https://coq.inria.fr/refman/proofs/writing-proofs/proof-mode.html#entering-and-exiting-proof-mode.
    """  # noqa: W505, B950
    obligation_starters = regex_from_options(obligation_starters, True, False)
    proof_enders = regex_from_options(
        {
            "Qed.",
            "Save",
            "Defined",
            "Admitted.",
            "Abort",
            "Solve All Obligations",
            "Solve Obligations",
            "Proof (?!with|using)"
        },
        True,
        False)
    """
    Vernacular commands that signal the end of proof mode.

    See https://coq.inria.fr/refman/proofs/writing-proofs/proof-mode.html#entering-and-exiting-proof-mode.
    """  # noqa: W505, B950
    proof_non_starters = regex_from_options(
        {"Obligation Tactic",
         "Obligations"},
        True,
        False)
    """
    Commands that could be mistakenly attributed as proof starters.
    """
    program_starters = {"Program",
                        r"#\[.*program.*\]"}
    """
    Vernacular commands that signal the beginning of a `Program`.

    Programs may require multiple distinct proofs to complete, which are
    each referred to as obligations.

    See https://coq.inria.fr/refman/addendum/program.html.
    """
    theorem_starters = regex_from_options(
        {
            "Goal",
            "Theorem",
            "Lemma",
            "Fact",
            "Remark",
            "Corollary",
            "Proposition",
            "Property",
            "Definition",
            "Example",
            "Instance",
            "Let",
            "Add Morphism",
            "Add Setoid",
            "Declare Morphism",
            "Add Parametric Morphism",
            "Function",
            "Fixpoint",
            "Coercion"
        }.union(program_starters),
        True,
        False)
    """
    Commands that may but are not guaranteed to require proofs.

    See https://coq.inria.fr/refman/language/core/definitions.html#assertions-and-proofs.
    """  # noqa: W505, B950
    program_starters = regex_from_options(program_starters, True, False)
    tactics = regex_from_options(
        {
            "abstract",
            "absurd",
            "admit",
            "all",
            "apply",
            "assert",
            "assert_fails",
            "assert_succeeds",
            "assumption",
            "auto",
            "autoapply",
            "autorewrite",
            "autounfold",
            "bfs",
            "btauto",
            "by",
            "case",
            "case_eq",
            "casetype",
            "cbn",
            "cbv",
            "change",
            "change_no_check",
            "classical_left",
            "classical_right",
            "clear",
            "clearbody",
            "cofix",
            "compare",
            "compute",
            "congr",
            "congruence",
            "constr_eq",
            "constr_eq_nounivs",
            "constr_eq_strict",
            "constructor",
            "context",
            "contradict",
            "contradiction",
            "cut",
            "cutrewrite",
            "cycle",
            "debug",
            "decide",
            "decompose",
            "dependent",
            "destruct",
            "dintuition",
            "discriminate",
            "discrR",
            "do",
            "done",
            "dtauto",
            "eapply",
            "eassert",
            "eassumption",
            "easy",
            "eauto",
            "ecase",
            "econstructor",
            "edestruct",
            "ediscriminate",
            "eelim",
            "eenough",
            "eexact",
            "eexists",
            "einduction",
            "einjection",
            "eintros",
            "eleft",
            "elim",
            "elimtype",
            "enough",
            "epose",
            "epose",
            "eremember",
            "erewrite",
            "eright",
            "eset",
            "esimplify_eq",
            "esplit",
            "etransitivity",
            "eval",
            "evar",
            "exact",
            "exact_no_check",
            "exactly_once",
            "exfalso",
            "exists",
            "f_equal",
            "fail",
            "field",
            "field_simplify",
            "field_simplify_eq",
            "finish_timing",
            "first",
            "first",
            "firstorder",
            "fix",
            "fold",
            "fresh",
            "fun",
            "functional",
            "generalize",
            "generally",
            "gfail",
            "give_up",
            "guard",
            "has_evar",
            "have",
            "hnf",
            "idtac",
            "if-then-else",
            "in",
            "induction",
            "info_auto",
            "info_eauto",
            "info_trivial",
            "injection",
            "instantiate",
            "intro",
            "intros",
            "intuition",
            "inversion",
            "inversion_clear",
            "inversion_sigma",
            "is_cofix",
            "is_const",
            "is_constructor",
            "is_evar",
            "is_fix",
            "is_ground",
            "is_ind",
            "is_proj",
            "is_var",
            "lapply",
            "last",
            "lazy",
            "lazy_match",
            "lazymatch",
            "left",
            "let",
            "lia",
            "lra",
            "ltac-seq",
            "match",
            "move",
            "multi_match",
            "multimatch",
            "native_cast_no_check",
            "native_compute",
            "nia",
            "notypeclasses",
            "now",
            "now_show",
            "nra",
            "nsatz",
            "numgoals",
            "omega",
            "once",
            "only",
            "optimize_heap",
            "over",
            "pattern",
            "pose",
            "progress",
            "psatz",
            "rapply",
            "red",
            "refine",
            "reflexivity",
            "remember",
            "rename",
            "repeat",
            "replace",
            "reset",
            "restart_timer",
            "revert",
            "revgoals"
            "rewrite",
            "rewrite_db",
            "rewrite_strat",
            "right",
            "ring",
            "ring_simplify",
            "rtauto",
            "set",
            "setoid_reflexivity",
            "setoid_replace",
            "setoid_rewrite",
            "setoid_symmetry",
            "setoid_transitivity",
            "shelve",
            "shelve_unifiable",
            "show",
            "simpl",
            "simple",
            "simplify_eq",
            "solve",
            "solve_constraints",
            "specialize",
            "split",
            "split_Rabs",
            "split_Rmult",
            "start",
            "subst",
            "substitute",
            "suff",
            "suffices",
            "swap",
            "symmetry",
            "tauto",
            "time",
            "time_constr",
            "timeout",
            "transitivity",
            "transparent_abstract",
            "trivial",
            "try",
            "tryif",
            "type",
            "type_term",
            "typeclasses",
            "under",
            "unfold",
            "unify",
            "unlock",
            "unshelve",
            "vm_cast_no_check",
            "vm_compute",
            "with_strategy",
            "without",
            "wlog",
            "zify"
        },
        True,
        False)
    """
    An enumeration of standard tactics.

    Note that they are all lower-case.
    This trend does not carry over to custom tactics.

    See https://coq.inria.fr/refman/coq-tacindex.html
    """
    tactic_definers = regex_from_options({"Ltac"},
                                         True,
                                         False)
    """
    Commands that define custom tactics.

    See https://coq.inria.fr/refman/proof-engine/ltac.html?highlight=ltac#coq:cmd.Ltac.
    """  # noqa: W505
    controllers = regex_from_options(
        {"Time",
         "Redirect",
         "Fail",
         "Succeed",
         "Timeout"},
        True,
        False)
    """
    Control commands that modify arbitrary sentences.

    See https://coq.inria.fr/refman/proof-engine/vernacular-commands.html?highlight=time#coq:cmd.Time.
    """  # noqa: W505, B950
    queries = regex_from_options(
        {"About",
         "Check",
         "Search",
         "Print",
         "Locate"},
        True,
        False)
    """
    Queries are not part of the program and should be ignored.

    See https://coq.inria.fr/refman/proof-engine/vernacular-commands.html?highlight=time#query-commands
    """  # noqa: W505, B950
    attributes = regex_from_options(
        {
            'Global',
            'Local',
            'Polymorphic',
            'Monomorphic',
            'Cumulative',
            'NonCumulative',
            "Private",
            "Program",
            r"#\[.+\]"
        },
        True,
        False)
    """
    (Legacy) attributes are prefixes applied to certain sentences.

    See https://coq.inria.fr/refman/language/core/basic.html#attributes.
    """
    requirement_starters = regex_from_options({"From",
                                               "Require"},
                                              True,
                                              False)
    """
    Commands to require loading compiled files and libraries.
    """
    logical_path_definers = regex_from_options(
        ['Require Import',
         'Require Export',
         'Require'],
        False,
        False)
    """
    Used to define logical paths of loaded files and libraries.
    """

    @classmethod
    def _is_command_type(
        cls,
        command_regex: re.Pattern,
        sentence: str,
        strip_mods: bool = False,
        forbidden_regex: Optional[re.Pattern] = None,
    ) -> bool:
        if strip_mods:
            sentence = cls.strip_control(sentence)
            sentence, _ = cls.strip_attributes(sentence)
        if (forbidden_regex is not None and re.match(forbidden_regex,
                                                     sentence) is not None):
            return False
        return re.match(command_regex, sentence) is not None

    @staticmethod
    def _strip_comments(file_contents: str, encoding: str = 'utf-8') -> str:
        # comments can be nested, so a single regex cannot be used
        # to detect this recursive structure.
        # Instead, split on comment boundaries and manually match
        # openers and closers.
        comment_depth = 0
        comment_delimited = re.split(r"(\(\*|\*\))", file_contents)
        str_no_comments = []
        for segment in comment_delimited:
            if segment == '(*':
                comment_depth += 1
            if comment_depth == 0:
                str_no_comments.append(segment)
            if segment == '*)':
                if comment_depth > 0:
                    comment_depth -= 1
        str_no_comments = ''.join(str_no_comments)
        return str_no_comments

    defines_tactic = partialmethod(_is_command_type, tactic_definers)
    """
    Return whether the given sentence defines a tactic.
    """
    defines_requirement = partialmethod(_is_command_type, requirement_starters)
    """
    Return whether given sentence defines a required module or file.
    """

    @classmethod
    def extract_identifier(cls, sentence: str) -> Tuple[str, str]:
        """
        Get the identifier and type for a sentence.

        Assumes the sentence can be identified.

        Returns
        -------
        type : str
            The type of the command, e.g., ``"Theorem"``.
        identifier : str
            The name of the command, e.g., ``"plus_n"``.
        """
        sentence_sans_control = ParserUtils.strip_control(sentence)
        sentence_sans_attributes, _ = ParserUtils.strip_attributes(
            sentence_sans_control)
        tokens = sentence_sans_attributes.split()
        if len(tokens) >= 2:
            return tokens[0], tokens[1]
        else:
            return tokens[0], ""

    @classmethod
    def extract_tactic_name(cls, sentence: str) -> str:
        """
        Get the name of a custom tactic from its definition.

        Assumes `ParserUtils.defines_tactic` is True for the sentence.
        """
        remainder = re.split(
            ParserUtils.tactic_definers,
            sentence,
            maxsplit=1)[1].lstrip()
        return re.split(r"\s+", remainder, maxsplit=1)[0]

    @classmethod
    def extract_requirements(cls, sentence: str) -> Set[str]:
        """
        Return logical name of loaded files from a load command.

        Assumes `ParserUtils.defines_requirement` is True for sentence.
        The full logical path is returned, including the ``dirpath``
        specified by the ``From`` command.

        See coq documentation for loading compiled files for
        more details:
        https://coq.inria.fr/distrib/current/refman/proof-engine/vernacular-commands.html?highlight=from#compiled-files
        """  # noqa: B950
        dirpath: str = ''
        # Split sentence into either a string containing requirements.
        # If there is a From command, it will be in the first value of
        # returned array
        reqs = re.split(cls.logical_path_definers, sentence)
        # Remove empty strings to ensure check for from command works.
        # Otherwise an empty string could be first in ``reqs``.
        reqs = [r for r in reqs if r]
        # Check if there is a From command
        if cls.defines_requirement(reqs[0]):
            dirpath = ''.join(re.split(cls.requirement_starters,
                                       reqs.pop(0))).strip()
        # Split remainder requirements, accounting for multiple
        # requirements in a single string.
        reqs = [r_ for r in reqs for r_ in r.split() if r_]
        # Append dirpath to requirements to form the full logical path
        # for each requirement.
        if dirpath:
            reqs = ['.'.join((dirpath, r)) for r in reqs if r]
        # Remove period that end the sentence and remove
        # leading and trailing whitespaces.
        return {r.rstrip('.').lstrip(' ').rstrip(' ') for r in reqs if r}

    is_fail = partialmethod(_is_command_type, re.compile("^Fail"))
    """
    Return whether the given sentence is meant to ``Fail``.
    """

    is_obligation_starter = partialmethod(_is_command_type, obligation_starters)
    """
    Return whether the given sentence starts an obligation proof.
    """

    is_program_starter = partialmethod(_is_command_type, program_starters)
    """
    Return whether the given sentence starts a program.

    See https://coq.inria.fr/refman/addendum/program.html.
    """

    is_proof_ender = partialmethod(_is_command_type, proof_enders)
    """
    Return whether the given sentence concludes a proof.
    """

    is_proof_starter = partialmethod(
        _is_command_type,
        proof_starters,
        forbidden_regex=proof_non_starters)
    """
    Return whether the given sentence starts a proof.
    """

    is_query = partialmethod(_is_command_type, queries)
    """
    Return whether the given sentence is a query.
    """

    @classmethod
    def is_tactic(cls, sentence: str, custom_tactics: Iterable[str]) -> bool:
        """
        Return whether the given sentence is a tactic.
        """
        # as long as we're using heuristics...
        if sentence[0].islower() or sentence[0].isnumeric():
            return True
        else:
            for tactic in custom_tactics:
                if sentence.startswith(tactic):
                    return True
            return False

    is_theorem_starter = partialmethod(_is_command_type, theorem_starters)
    """
    Return whether the given sentence starts a theorem.
    """

    @classmethod
    def sets_nested_proofs(cls,
                           sentence: str,
                           strip_mods: bool = False) -> Optional[bool]:
        """
        Determine whether the command enables or disables proof nesting.

        Parameters
        ----------
        sentence : str
            A sentence.
        strip_mods : bool, optional
            Whether to strip control or attribute modifiers from the
            start of the sentence, by default False.
            If False, then these modifiers are presumed to already by
            stripped from the sentence.

        Returns
        -------
        Optional[bool]
            True if the sentence sets nested proofs, False if it unsets
            nested proofs, and None if it does neither.
        """
        if strip_mods:
            sentence = cls.strip_control(sentence)
            sentence = cls.strip_attributes(sentence)
        if sentence == "Set Nested Proofs Allowed.":
            return True
        elif sentence == "Unset Nested Proofs Allowed.":
            return False
        else:
            return None

    @classmethod
    def strip_attribute(cls, sentence: str) -> Tuple[str, Optional[str]]:
        """
        Strip an attribute from the start of the sentence.

        Returns
        -------
        stripped : str
            The sentence stripped of its leading attribute.
        attribute : Optional[str]
            The leading attribute or None if there is no attribute.
        """
        attribute = re.match(ParserUtils.attributes, sentence)
        if attribute is not None:
            attribute = attribute.group()
            stripped = re.split(
                ParserUtils.attributes,
                sentence,
                maxsplit=1)[1].lstrip()
            return stripped, attribute
        else:
            return sentence, attribute

    @classmethod
    def strip_attributes(cls, sentence: str) -> Tuple[str, List[str]]:
        """
        Strip any attributes from the start of the sentence.

        Returns
        -------
        stripped : str
            The sentence stripped of its leading attributes.
        attributes : List[str]
            The stripped attributes in order of appearance.
        """
        attributes = []
        stripped, attribute = ParserUtils.strip_attribute(sentence)
        while attribute is not None:
            attributes.append(attribute)
            sentence = stripped
            stripped, attribute = ParserUtils.strip_attribute(sentence)
        return stripped, attributes

    @classmethod
    def strip_control(cls, sentence: str) -> str:
        """
        Strip any control commands from the start of the sentence.
        """
        if re.match(ParserUtils.controllers, sentence) is not None:
            return re.split(
                ParserUtils.controllers,
                sentence,
                maxsplit=1)[1].lstrip()
        else:
            return sentence

    @staticmethod
    def split_brace(sentence: str) -> Tuple[str, str]:
        """
        Split the bullets from the start of a sentence.

        Parameters
        ----------
        sentence : str
            A sentence.

        Returns
        -------
        bullet : str
            The brace or an empty string if no bullets are found.
        remainder : str
            The rest of the sentence after the bullet.

        Notes
        -----
        The sentence is assumed to have already been split from a
        document based upon ending periods.
        Thus we assume that `sentence` concludes with a period.
        """
        bullet_re = re.split(r"^\s*(\{|\})", sentence, maxsplit=1)
        if len(bullet_re) > 1:
            # throw away empty first token
            # by structure of regex, there can be only 2 sections
            return bullet_re[1], bullet_re[2]
        else:
            return "", sentence

    @staticmethod
    def split_braces_and_bullets(sentence: str) -> Tuple[List[str], str]:
        """
        Split braces and bullets from the start of a sentence.

        Parameters
        ----------
        sentence : str
            A sentence.

        Returns
        -------
        braces_and_bullets : List[str]
            The braces or bullets.
            If none are found, then an empty list is returned.
        remainder : str
            The rest of the sentence after the braces and bullets.

        Notes
        -----
        The sentence is assumed to have already been split from a
        document based upon ending periods.
        Thus we assume that `sentence` concludes with a period.
        """
        braces_and_bullets = []
        while True:
            maybe_bullet, sentence = ParserUtils.split_bullet(sentence)
            maybe_brace, sentence = ParserUtils.split_brace(sentence)
            if maybe_bullet:
                braces_and_bullets.append(maybe_bullet)
            if maybe_brace:
                braces_and_bullets.append(maybe_brace)
            if maybe_bullet == "" and maybe_brace == "":
                break
        return braces_and_bullets, sentence.lstrip()

    @staticmethod
    def split_bullet(sentence: str) -> Tuple[str, str]:
        """
        Split a bullet from the start of a sentence.

        Parameters
        ----------
        sentence : str
            A sentence.

        Returns
        -------
        bullet : str
            The bullet or an empty string if no bullets are found.
        remainder : str
            The rest of the sentence after the bullet.

        Notes
        -----
        The sentence is assumed to have already been split from a
        document based upon ending periods.
        Thus we assume that `sentence` concludes with a period.
        """
        bullet_re = re.split(r"^\s*(-+|\++|\*+)", sentence, maxsplit=1)
        if len(bullet_re) > 1:
            # throw away empty first token
            # by structure of regex, there can be only 2 sections
            return bullet_re[1], bullet_re[2]
        else:
            return "", sentence

    @dataclass
    class StrWithLocation:
        """
        Class that ties strings to their original in-file locations.

        Strings stored in objects of this class should only be those
        that have been loaded from files. The location data is only
        meaningful in that context.

        If a string spans multiple lines, it is assumed that the newline
        and other whitespace characters that situate the lines are
        present in the string.
        """

        string: str
        """The string itself."""
        indices: List[Tuple[int, int]]
        """
        The string's original location. Should only be None if `string`
        is empty.
        """

        def __add__(self, other: 'ParserUtils.StrWithLocation'):
            """
            Combine this instance with another using '+'.
            """
            if isinstance(other, ParserUtils.StrWithLocation):
                return ParserUtils.StrWithLocation(
                    self.string + other.string,
                    self.indices + other.indices)
            else:
                raise TypeError(
                    "Second addened must be of the same type as the first addend."
                )

        def __bool__(self) -> bool:
            """
            Tie truth value to string field.
            """
            return len(self.string) > 0

        def __getitem__(
                self,
                idx: Union[int,
                           slice]) -> 'ParserUtils.StrWithLocation':
            """
            Return a portion of the located string at the given idx.
            """
            return ParserUtils.StrWithLocation(
                self.string[idx],
                self.indices[idx])

        def __len__(self) -> int:
            """
            Get the length of the located string.
            """
            return len(self.string)

        def __post_init__(self):
            """
            Verify inputs.

            Raises
            ------
            ValueError
                If the length of the string list does not match the
                length of the loc list
            """
            if len(self.string) != len(self.loc):
                raise ValueError("Each string should have a location.")

        def __str__(self) -> str:
            """
            Return a plain-string representation of the located string.
            """
            return self.string

        @property
        def start(self) -> Optional[int]:  # noqa: D102
            return self.indices[0][0] if self.indices else None

        @property
        def end(self) -> Optional[int]:  # noqa: D102
            return self.indices[-1][1] if self.indices else None

        def get_location(
                self,
                file_contents: str,
                filename: str) -> SexpInfo.Loc:
            """
            Derive the SexpInfo.Loc location from the located string.

            Parameters
            ----------
            file_contents : str
                The full file contents in string form
            filename : str
                The filename the file contents were loaded from

            Returns
            -------
            SexpInfo.Loc
                The derived SexpInfo.Loc location
            """
            num_newlines_before_string = file_contents[: self.start].count(
                r"\n")
            num_newlines_in_string = file_contents[self.start,
                                                   self.end].count(r"\n")
            bol_match = re.search(
                r"(?<=\n)[^\S\n]+$",
                file_contents[: self.start])
            bol_pos = len(bol_match[0]) if bol_match is not None else 0
            bol_last_match = re.search(
                r"(?<=\n)[^\S\n]+(?=\S[^\n]*$)",
                file_contents[: self.end])
            bol_pos_last = len(
                bol_last_match[0]) if bol_last_match is not None else 0
            return SexpInfo.Loc(
                filename=filename,
                lineno=num_newlines_before_string,
                bol_pos=bol_pos,
                lineno_last=num_newlines_before_string + num_newlines_in_string,
                bol_pos_last=bol_pos_last,
                beg_charno=self.start,
                end_charno=self.end)

        def lstrip(self):
            """
            Mimic str lstrip method, keeping track of location.
            """
            match = re.search(r"^\s+", self.string)
            if match is not None:
                self.string = self.string[match.end():]
                self.indices = self.indices[match.end():]

        def restore_final_period(self) -> 'ParserUtils.StrWithLocation':
            """
            Restore the final period at the end of a sentence.
            """
            if not self.string.endswith("."):
                self.string += "."
                self.indices.append(
                    (self.indices[-1][1],
                     self.indices[-1][1] + 1))

        def rstrip(self):
            """
            Mimic str rstrip method, keeping track of location.
            """
            match = re.search(r"\s+$", self.string)
            if match is not None:
                self.string = self.string[: match.start()]
                self.indices = self.indices[: match.start()]

        def strip(self):
            """
            Mimic str strip method, but don't take an argument.
            """
            self.lstrip()
            self.rstrip()

        @classmethod
        def create_from_file_contents(
                cls,
                file_contents: str) -> 'ParserUtils.StrWithLocation':
            """
            Create an instance of StrWithLocation from doc contents str.

            Parameters
            ----------
            file_contents : str
                A single string containing a the unaltered, full
                contents of a Coq file

            Returns
            -------
            ParserUtils.StrWithLocation
                The instance created from the file contents
            """
            return cls(
                file_contents,
                [(i,
                  i + 1) for i in range(len(file_contents))])

        @classmethod
        def re_split(
            cls,
            pattern: Union[str,
                           re.Pattern],
            string: 'ParserUtils.StrWithLocation',
            maxsplit: int = 0,
            flags: Union[int,
                         re.RegexFlag] = 0
        ) -> List['ParserUtils.StrWithLocation']:
            """
            Mimic re.split, but maintain location information.

            Parameters
            ----------
            pattern : Union[str, re.Pattern[str]]
                Pattern to match for split
            string : ParserUtils.StrWithLocation
                The string with location to split
            maxsplit : int, optional
                Maximum number of splits to do; unlimited if 0, by
                default 0
            flags : int or re.RegexFlag, optional
                Flags to pass to compile operation if pattern is a str,
                by default 0

            Returns
            -------
            List[StrWithLocation]
                A list of strings with locations after being split by
                the pattern
            """
            if isinstance(pattern, str):
                pattern = re.compile(pattern, flags)
            located_result: List[ParserUtils.StrWithLocation] = []
            remaining_str = cls(string.string, string.indices)
            current_split = 0
            while remaining_str:
                match = pattern.search(remaining_str)
                if match is None or (maxsplit > 0
                                     and current_split >= maxsplit):
                    # Either pattern is not found or maxsplit limit has
                    # been reached. In both cases, stop splitting.
                    located_result.append(remaining_str)
                    remaining_str = cls("", [])
                else:
                    # Carry on splitting
                    if match.start() > 0:
                        # If part of the remaining string lies before
                        # the first split pattern occurrence...
                        located_result.append(remaining_str[: match.start()])
                    remaining_str = remaining_str[match.end():]
                current_split += 1
            return located_result

        @classmethod
        def re_sub(
            cls,
            pattern: Union[str,
                           re.Pattern],
            repl: str,
            string: 'ParserUtils.StrWithLocation',
            count: int = 0,
            flags: Union[int,
                         re.RegexFlag] = 0) -> 'ParserUtils.StrWithLocation':
            """
            Mimic re.sub, but maintain location information.

            Parameters
            ----------
            pattern : Union[str, re.Pattern]
                Pattern to match for split
            repl : str
                String to substitute in when pattern is found
            string : ParserUtils.StrWithLocation
                The string to perform the substitution on
            count : int, optional
                Maximum number of substitutions to do; unlimited if 0,
                by default 0
            flags : int or re.RegexFlag, optional
                Flags to pass to compile operation if pattern is a str,
                by default 0

            Returns
            -------
            StrWithLocation
                Located string with substitution performed
            """
            string = cls(string.string, string.indices)
            if isinstance(pattern, str):
                pattern = re.compile(pattern, flags)
            match = pattern.search(string.string)
            idx = 0
            while match is not None and not (idx > count > 0):
                start, end = match.start(), match.end()
                pre_match = string[: start]
                post_match = string[end :]
                repl_indices = [(start, end) for _ in range(len(repl))]
                string = pre_match + cls(repl, repl_indices) + post_match
                match = pattern.search(string.string, pos=start + len(repl))
                idx += 1
            return string
