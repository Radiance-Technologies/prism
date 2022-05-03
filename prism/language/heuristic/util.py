"""
Provides internal utilities for heuristic parsing of Coq source files.
"""

import re
from functools import partialmethod
from typing import Iterable, List, Optional, Tuple

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
    program_starters = {"Program"}
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
         "Succeed"},
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
            "Private"
        },
        True,
        False)
    """
    (Legacy) attributes are prefixes applied to certain sentences.

    See https://coq.inria.fr/refman/language/core/basic.html#attributes.
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
            sentence = cls.strip_attributes(sentence)
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
    def strip_attribute(cls, sentence: str) -> str:
        """
        Strip an attribute from the start of the sentence.
        """
        if re.match(ParserUtils.attributes, sentence) is not None:
            return re.split(
                ParserUtils.attributes,
                sentence,
                maxsplit=1)[1].lstrip()
        else:
            return sentence

    @classmethod
    def strip_attributes(cls, sentence: str) -> str:
        """
        Strip any attributes from the start of the sentence.
        """
        stripped = ParserUtils.strip_attribute(sentence)
        while len(stripped) < len(sentence):
            sentence = stripped
            stripped = ParserUtils.strip_attribute(sentence)
        return stripped

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
