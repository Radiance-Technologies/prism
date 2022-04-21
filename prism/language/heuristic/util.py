"""
Provides internal utilities for heuristic parsing of Coq source files.
"""
import re
from typing import List, Tuple, Union

from prism.data.sentence import VernacularSentence
from prism.language.gallina.parser import CoqParser
from prism.language.id import LanguageId
from prism.util.re import regex_from_options


class ParserUtils:
    """
    Namespace for utilities for heuristic parsing.

    Provides functions for splitting sentence elements.
    """

    program_starters = regex_from_options(
        {"Program",
         "Global Program",
         "Local Program"},
        True,
        False)
    """
    Vernacular commands that signal the beginning of a `Program`.

    Programs may require multiple distinct proofs to complete, which are
    each referred to as obligations.

    See https://coq.inria.fr/refman/addendum/program.html.
    """
    proof_enders = regex_from_options(
        {"Qed.",
         "Save",
         "Defined",
         "Admitted.",
         "Abort"},
        True,
        False)
    """
    Vernacular commands that signal the end of proof mode.

    See https://coq.inria.fr/refman/proofs/writing-proofs/proof-mode.html#entering-and-exiting-proof-mode.
    """  # noqa: W505, B950
    proof_starters = regex_from_options(
        {
            "Proof",
            "Next Obligation",
            "Solve Obligation",
            "Solve All Obligations",
            "Obligation",
            "Goal",
        },
        True,
        False)
    """
    Vernacular commands that signal the begining of proof mode.

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
    theorem_starters = {
        "Theorem",
        "Lemma",
        "Fact",
        "Remark",
        "Corollary",
        "Proposition",
        "Property",
        "Definition",
        "Example",
        "Instance"
    }
    """
    Commands that may but are not guaranteed to require proofs.

    See https://coq.inria.fr/refman/language/core/definitions.html#assertions-and-proofs.
    """  # noqa: W505, B950
    theorem_starters.update(
        {f"Global {st}" for st in theorem_starters}.union(
            {f"Local {st}" for st in theorem_starters}))
    theorem_starters = regex_from_options(theorem_starters, True, False)
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

    @staticmethod
    def strip_comments(
            file_contents: Union[str,
                                 bytes],
            encoding: str = 'utf-8') -> str:
        """
        Strip comments from given Coq code.

        Parameters
        ----------
        file_contents : Union[str, bytes]
            Coq file contents
        encoding : str, optional
            Encoding of Coq file, by default 'utf-8'

        Returns
        -------
        str
            Coq code stripped of comments
        """
        if isinstance(file_contents, bytes):
            file_contents = CoqParser.decode_byte_string(
                file_contents,
                encoding=encoding)
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

    @staticmethod
    def is_program_starter(sentence: str) -> bool:
        """
        Return whether the given sentence starts a program.

        See https://coq.inria.fr/refman/addendum/program.html.
        """
        return re.match(ParserUtils.program_starters, str(sentence)) is not None

    @staticmethod
    def is_proof_starter(sentence: str) -> bool:
        """
        Return whether the given sentence starts a proof.
        """
        sentence = str(sentence)
        if re.match(ParserUtils.proof_non_starters, sentence) is not None:
            return False
        return re.match(ParserUtils.proof_starters, sentence) is not None

    @staticmethod
    def is_proof_ender(sentence: str) -> bool:
        """
        Return whether the given sentence concludes a proof.
        """
        sentence = str(sentence)
        if re.match(ParserUtils.proof_enders, sentence) is not None:
            return True
        # Proof <term> starts and ends a proof in one command.
        return (
            sentence.startswith("Proof ") and sentence[6 : 11] != "with "
            and sentence[6 :].lstrip() != ".")

    @staticmethod
    def is_tactic(sentence: str) -> bool:
        """
        Return whether the given sentence is a tactic.
        """
        # as long as we're using heuristics...
        return sentence[0].islower()
        # for tactic in ProjectBase.tactics:
        #     if sentence.startswith(tactic):
        #         return True
        # return False

    @staticmethod
    def is_theorem_starter(sentence: str) -> bool:
        """
        Return whether the given sentence starts a theorem.
        """
        return re.match(ParserUtils.theorem_starters, str(sentence)) is not None

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


class ParserUtilsSerAPI(ParserUtils):
    """
    Namespace for utilities for SerAPI parsing.

    Provides functions for splitting sentence elements.
    """

    @staticmethod
    def is_brace_or_bullet(sentence: VernacularSentence) -> bool:
        """
        Return whether given sentence is a brace or a bullet.
        """
        return re.match(
            r"^(\{|\}|\*+|\++|\-+)$",
            sentence.str_minimal_whitespace()) is not None

    @staticmethod
    def is_tactic(sentence: VernacularSentence) -> bool:
        """
        Return whether the given sentence is a tactic.
        """
        sclid = sentence.classify_lid()
        return (
            sclid == LanguageId.Ltac
            or sclid == LanguageId.LtacMixedWithGallina)

    @staticmethod
    def split_brace(sentence: VernacularSentence):
        """
        Do not use.
        """
        pass

    @staticmethod
    def split_braces_and_bullets(sentence: VernacularSentence):
        """
        Do not use.
        """
        pass

    @staticmethod
    def split_bullet(sentence: VernacularSentence):
        """
        Do not use.
        """
        pass
