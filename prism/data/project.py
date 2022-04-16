"""
Module providing CoqGym project class representations.
"""
import logging
import pathlib
import random
import re
import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union
from warnings import warn

from git import Commit, Repo
from seutil import BashUtils

from prism.data.document import CoqDocument
from prism.language.gallina.parser import CoqParser
from prism.util.logging import default_log_level

logger: logging.Logger = logging.getLogger(__name__)
logger.setLevel(default_log_level())


class DirHasNoCoqFiles(Exception):
    """
    Exception indicating that the current directory has no Coq files.

    Sub-directories should be checked as well before raising this
    exception.
    """

    pass


class ProjectBase(ABC):
    """
    Abstract base class for representing a Coq project.

    Parameters
    ----------
    dir_abspath : str
        The absolute path to the project's root directory.
    build_cmd : str or None
        The terminal command used to build the project, by default None.
    clean_cmd : str or None
        The terminal command used to clean the project, by default None.
    install_cmd : str or None
        The terminal command used to install the project, by default
        None.

    Attributes
    ----------
    name : str
        The stem of the working directory, used as the project name
    size_bytes : int
        The total space on disk occupied by the files in the dir in
        bytes
    build_cmd : str or None
        The terminal command used to build the project.
    clean_cmd : str or None
        The terminal command used to clean the project.
    install_cmd : str or None
        The terminal command used to install the project..
    """

    program_starters = {"Program",
                        "Global Program",
                        "Local Program"}
    proof_enders = {"Qed.",
                    "Save",
                    "Defined",
                    "Admitted.",
                    "Abort"}
    proof_starters = {
        "Proof",
        "Next Obligation",
        "Solve Obligation",
        "Solve All Obligations",
        "Obligation",
        "Goal",
    }
    proof_non_starters = {"Obligation Tactic",
                          "Obligations"}
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
    theorem_starters.update(
        {f"Global {st}" for st in theorem_starters}.union(
            {f"Local {st}" for st in theorem_starters}))
    # See https://coq.inria.fr/refman/coq-tacindex.html
    tactics = {
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
    }

    def __init__(
            self,
            dir_abspath: str,
            build_cmd: Optional[str] = None,
            clean_cmd: Optional[str] = None,
            install_cmd: Optional[str] = None):
        """
        Initialize Project object.
        """
        self.name = pathlib.Path(dir_abspath).stem
        self.size_bytes = self._get_size_bytes()
        self.build_cmd: Optional[str] = build_cmd
        self.clean_cmd: Optional[str] = clean_cmd
        self.install_cmd: Optional[str] = install_cmd

    @property
    @abstractmethod
    def path(self) -> str:
        """
        Get the path to the project's root directory.
        """
        pass

    @property
    def serapi_options(self) -> str:
        """
        Get the SerAPI options for parsing this project's files.

        Returns
        -------
        str
            The command-line options for invoking SerAPI tools, e.g.,
            ``f"sercomp {serapi_options} file.v"``.
        """
        # TODO: Get from project metadata.
        return ""

    @abstractmethod
    def _get_file(self, filename: str, *args, **kwargs) -> CoqDocument:
        """
        Return a specific Coq source file.

        See Also
        --------
        ProjectBase.get_file : For public API.
        """
        pass

    def _get_size_bytes(self) -> int:
        """
        Get size in bytes of working directory.
        """
        return sum(
            f.stat().st_size
            for f in pathlib.Path(self.path).glob('**/*')
            if f.is_file())

    @abstractmethod
    def _pre_get_random(self, **kwargs):
        """
        Handle tasks needed before getting a random file (or pair, etc).
        """
        pass

    @abstractmethod
    def _traverse_file_tree(self) -> List[CoqDocument]:
        """
        Traverse the file tree and return a list of Coq file objects.
        """
        pass

    def build(self) -> Tuple[int, str, str]:
        """
        Build the project.
        """
        if self.build_cmd is None:
            raise RuntimeError(f"Build command not set for {self.name}.")
        r = BashUtils.run(self.build_cmd)
        if r.return_code != 0:
            raise Exception(
                f"Compilation failed! Return code is {r.return_code}! "
                f"stdout:\n{r.stdout}\n; stderr:\n{r.stderr}")
        else:
            logger.debug(
                f"Compilation finished. Return code is {r.return_code}. "
                f"stdout:\n{r.stdout}\n; stderr:\n{r.stderr}")
        return (r.return_code, r.stdout, r.stderr)

    def clean(self) -> Tuple[int, str, str]:
        """
        Clean the build status of the project.
        """
        if self.clean_cmd is None:
            raise RuntimeError(f"Clean command not set for {self.name}.")
        r = BashUtils.run(self.clean_cmd)
        if r.return_code != 0:
            raise Exception(
                f"Cleaning failed! Return code is {r.return_code}! "
                f"stdout:\n{r.stdout}\n; stderr:\n{r.stderr}")
        else:
            logger.debug(
                f"Cleaning finished. Return code is {r.return_code}. "
                f"stdout:\n{r.stdout}\n; stderr:\n{r.stderr}")
        return (r.return_code, r.stdout, r.stderr)

    def get_file(self, filename: str, *args, **kwargs) -> CoqDocument:
        """
        Return a specific Coq source file.

        Parameters
        ----------
        filename : str
            The absolute path to the file to return.

        Returns
        -------
        CoqDocument
            A CoqDocument corresponding to the selected Coq source file

        Raises
        ------
        ValueError
            If given `filename` does not end in ".v"
        """
        if not filename.endswith(".v"):
            raise ValueError("filename must end in .v")
        return self._get_file(filename, *args, **kwargs)

    @abstractmethod
    def get_file_list(self, **kwargs) -> List[str]:
        """
        Return a list of all Coq files associated with this project.

        Returns
        -------
        List[str]
            The list of absolute paths to all Coq files in the project
        """
        pass

    def get_random_file(self, **kwargs) -> CoqDocument:
        """
        Return a random Coq source file.

        Returns
        -------
        CoqDocument
            A random Coq source file in the form of a CoqDocument
        """
        self._pre_get_random(**kwargs)
        files = self._traverse_file_tree()
        result = random.choice(files)
        return result

    def get_random_sentence(
            self,
            filename: Optional[str] = None,
            glom_proofs: bool = True,
            **kwargs) -> str:
        """
        Return a random sentence from the project.

        Filename is random unless it is provided.

        Parameters
        ----------
        filename : Optional[str], optional
            Absolute path to file to load sentence from, by default None
        glom_proofs : bool, optional
            Boolean flag indicating whether proofs should form their own
            pseudo-sentences, by default True

        Returns
        -------
        str
            A random sentence from the project
        """
        if filename is None:
            obj = self.get_random_file(**kwargs)
        else:
            obj = self.get_file(filename, **kwargs)
        sentences = self.split_by_sentence(obj, 'utf-8', glom_proofs)
        sentence = random.choice(sentences)
        return sentence

    def get_random_sentence_pair_adjacent(
            self,
            filename: Optional[str] = None,
            glom_proofs: bool = True,
            **kwargs) -> List[str]:
        """
        Return a random adjacent sentence pair from the project.

        Filename is random unless it is provided.

        Parameters
        ----------
        filename : Optional[str], optional
            Absolute path to file to load sentences from, by default
            None
        glom_proofs : bool, optional
            Boolean flag indicating whether proofs should form their own
            pseudo-sentences, by default True

        Returns
        -------
        List of str
            A list of two adjacent sentences from the project, with the
            first sentence chosen at random
        """
        sentences: List[str] = []
        counter = 0
        THRESHOLD = 100
        while len(sentences) < 2:
            if counter > THRESHOLD:
                raise RuntimeError(
                    "Can't find file with more than 1 sentence after",
                    THRESHOLD,
                    "attempts. Try different inputs.")
            if filename is None:
                obj = self.get_random_file(**kwargs)
            else:
                obj = self.get_file(filename, **kwargs)
            sentences = self.split_by_sentence(obj, 'utf-8', glom_proofs)
            counter += 1
        first_sentence_idx = random.randint(0, len(sentences) - 2)
        return sentences[first_sentence_idx : first_sentence_idx + 2]

    def install(self) -> Tuple[int, str, str]:
        """
        Install the project system-wide in "coq-contrib".
        """
        if self.install_cmd is None:
            raise RuntimeError(f"Install command not set for {self.name}.")
        self.build()
        r = BashUtils.run(self.install_cmd)
        if r.return_code != 0:
            raise Exception(
                f"Installation failed! Return code is {r.return_code}! "
                f"stdout:\n{r.stdout}\n; stderr:\n{r.stderr}")
        else:
            logger.debug(
                f"Installation finished. Return code is {r.return_code}. "
                f"stdout:\n{r.stdout}\n; stderr:\n{r.stderr}")
        return (r.return_code, r.stdout, r.stderr)

    @staticmethod
    def _decode_byte_stream(
            data: Union[bytes,
                        str],
            encoding: str = 'utf-8') -> str:
        """
        Decode the incoming data if it's a byte string.

        Parameters
        ----------
        data : Union[bytes, str]
            Byte-string or string data to be decoded if byte-string
        encoding : str, optional
            Encoding to use in decoding, by default 'utf-8'

        Returns
        -------
        str
            String representation of input data
        """
        return data.decode(encoding) if isinstance(data, bytes) else data

    @staticmethod
    def _strip_comments(
            file_contents: Union[str,
                                 bytes],
            encoding: str = 'utf-8') -> str:
        if isinstance(file_contents, bytes):
            file_contents = ProjectBase._decode_byte_stream(
                file_contents,
                encoding)
        comment_depth = 0
        comment_delimited = re.split(r"(\(\*|\*\))", file_contents)
        str_no_comments = []
        for segment in comment_delimited:
            if segment == '(*':
                comment_depth += 1
            if comment_depth == 0:
                str_no_comments.append(segment)
            if segment == '*)':
                comment_depth -= 1
        str_no_comments = ''.join(str_no_comments)
        return str_no_comments

    @staticmethod
    def is_program_starter(sentence: str) -> bool:
        """
        Return whether the given sentence starts a program.

        See https://coq.inria.fr/refman/addendum/program.html.
        """
        for starter in ProjectBase.program_starters:
            if sentence.startswith(starter):
                return True
        return False

    @staticmethod
    def is_proof_starter(sentence: str) -> bool:
        """
        Return whether the given sentence starts a proof.
        """
        for non_starter in ProjectBase.proof_non_starters:
            if sentence.startswith(non_starter):
                return False
        for starter in ProjectBase.proof_starters:
            if sentence.startswith(starter):
                return True
        return False

    @staticmethod
    def is_proof_ender(sentence: str) -> bool:
        """
        Return whether the given sentence concludes a proof.
        """
        for ender in ProjectBase.proof_enders:
            if sentence.startswith(ender):
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
        for starter in ProjectBase.theorem_starters:
            if sentence.startswith(starter):
                return True
        return False

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
            maybe_bullet, sentence = ProjectBase.split_bullet(sentence)
            maybe_brace, sentence = ProjectBase.split_brace(sentence)
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

    @staticmethod
    def split_by_sentence(
            document: CoqDocument,
            encoding: str = 'utf-8',
            glom_proofs: bool = True) -> List[str]:
        """
        Split the Coq file text by sentences.

        By default, proofs are then re-glommed into their own entries.
        This behavior can be switched off.

        Parameters
        ----------
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
        file_contents = document.source_code
        if isinstance(file_contents, bytes):
            file_contents = ProjectBase._decode_byte_stream(
                file_contents,
                encoding)
        file_contents_no_comments = ProjectBase._strip_comments(
            file_contents,
            encoding)
        # Split sentences by instances of single periods followed by
        # whitespace. Double (or more) periods are specifically
        # excluded.
        sentences = re.split(r"(?<!\.)\.\s", file_contents_no_comments)

        @dataclass
        class Assertion:
            statement: Optional[str]
            proofs: List[List[str]]  # or obligations

            @property
            def is_program(self) -> bool:
                return self.statement is None

            @property
            def in_proof(self) -> bool:
                return (
                    self.proofs and self.proofs[-1]
                    and not ProjectBase.is_proof_ender(self.proofs[-1][-1]))

            def start_proof(
                    self,
                    starter: Optional[str],
                    braces_and_bullets: List[str]) -> None:
                # assert there is either
                # * a theorem statement without proof, or
                # * a program with zero or more proofs
                assert self.is_program or (
                    not self.is_program and len(self.proofs) <= 1)
                assert not braces_and_bullets
                if self.in_proof:
                    assert starter is not None
                    self.proofs[-1].append(starter)
                else:
                    self.proofs.append([] if starter is None else [starter])

            def apply_tactic(
                    self,
                    tactic: str,
                    braces_and_bullets: List[str]) -> None:
                if not self.proofs:
                    self.start_proof(None, [])
                self.proofs[-1].extend(braces_and_bullets)
                self.proofs[-1].append(tactic)

            def end_proof(
                    self,
                    ender: str,
                    braces_and_bullets: List[str]) -> None:
                # assert we are in a proof
                assert self.proofs and self.proofs[-1]
                self.proofs[-1].extend(braces_and_bullets)
                self.proofs[-1].append(ender)

            @classmethod
            def discharge(cls, theorem: 'Assertion', result: List[str]) -> None:
                nonlocal glom_proofs
                if theorem.statement is not None:
                    result.append(theorem.statement)
                proofs = theorem.proofs
                for proof in proofs:
                    if not ProjectBase.is_proof_ender(proof[-1]):
                        warn(
                            "Found an unterminated proof environment in "
                            f"{document.index}. "
                            "Abandoning proof glomming.")
                        glom_proofs = False
                accum = result.extend
                if glom_proofs:
                    proofs = [" ".join(proof) for proof in proofs]
                    accum = result.append
                for proof in proofs:
                    accum(proof)

            @classmethod
            def discharge_all(
                    cls,
                    theorems: List['Assertion'],
                    result: List[str]) -> None:
                for theorem in reversed(theorems):
                    cls.discharge(theorem, result)

        theorems: List[Assertion] = []
        result: List[str] = []
        for sentence in sentences:
            # Replace any whitespace or group of whitespace with a
            # single space.
            sentence = re.sub(r"(\s)+", " ", sentence)
            sentence = sentence.strip()
            sentence += "."
            (braces_and_bullets,
             sentence) = ProjectBase.split_braces_and_bullets(sentence)
            if ProjectBase.is_theorem_starter(sentence):
                # push new context onto stack
                assert not braces_and_bullets
                theorems.append(Assertion(sentence, []))
            elif ProjectBase.is_proof_starter(sentence):
                if not theorems:
                    theorems.append(Assertion(None, []))
                theorems[-1].start_proof(sentence, braces_and_bullets)
            elif (ProjectBase.is_tactic(sentence)
                  or (theorems and theorems[-1].in_proof)):
                if not theorems:
                    theorems.append(Assertion(None, []))
                theorems[-1].apply_tactic(sentence, braces_and_bullets)
            elif ProjectBase.is_proof_ender(sentence):
                theorems[-1].end_proof(sentence, braces_and_bullets)
                Assertion.discharge(theorems.pop(), result)
            else:
                # not a theorem, tactic, proof starter, or proof ender
                # discharge theorem stack
                Assertion.discharge_all(theorems, result)
                theorems = []
                if ProjectBase.is_program_starter(sentence):
                    # push new context onto stack
                    theorems.append(Assertion(None, []))
                assert not braces_and_bullets
                result.append(sentence)
        # End of file; discharge any remaining theorems
        Assertion.discharge_all(theorems, result)
        # Lop off the final line if it's just a period, i.e., blank.
        if result[-1] == ".":
            result.pop()
        return result


class ProjectRepo(Repo, ProjectBase):
    """
    Class for representing a Coq project.

    Based on GitPython's `Repo` class.
    """

    def __init__(self, dir_abspath: str):
        """
        Initialize Project object.
        """
        Repo.__init__(self, dir_abspath)
        ProjectBase.__init__(self, dir_abspath)
        self.current_commit_name = None  # i.e., HEAD

    @property
    def path(self) -> str:  # noqa: D102
        return self.working_dir

    def _get_file(
            self,
            filename: str,
            commit_name: Optional[str] = None) -> CoqDocument:
        """
        Return a specific Coq source file from a specific commit.

        Parameters
        ----------
        filename : str
            The absolute path to the file to return.
        commit_name : str or None, optional
            A commit hash, branch name, or tag name from which to fetch
            the file. Defaults to HEAD.

        Returns
        -------
        CoqDocument
            A CoqDocument corresponding to the selected Coq source file

        Raises
        ------
        ValueError
            If given `filename` does not end in ".v"
        """
        commit = self.commit(commit_name)
        # Compute relative path
        rel_filename = filename.replace(commit.tree.abspath, "")[1 :]
        return CoqDocument(
            rel_filename,
            project_path=self.path,
            source_code=(commit.tree / rel_filename).data_stream.read())

    def _pre_get_file(self, **kwargs):
        """
        Set the current commit; use HEAD if none given.
        """
        self.current_commit_name = kwargs.get("commit_name", None)

    def _pre_get_random(self, **kwargs):
        """
        Set the current commit; use random if none given.
        """
        commit_name = kwargs.get("commit_name", None)
        if commit_name is None:
            kwargs['commit_name'] = self.get_random_commit()
        self._pre_get_file(**kwargs)

    def _traverse_file_tree(self) -> List[CoqDocument]:
        """
        Traverse the file tree and return a full list of file objects.
        """
        commit = self.commit(self.current_commit_name)
        files = [f for f in commit.tree.traverse() if f.abspath.endswith(".v")]
        return [
            CoqDocument(
                f.path,
                project_path=self.path,
                source_code=f.data_stream.read()) for f in files
        ]

    def get_file_list(self, commit_name: Optional[str] = None) -> List[str]:
        """
        Return a list of all Coq files associated with this project.

        Parameters
        ----------
        commit_name : str or None, optional
            A commit hash, branch name, or tag name from which to get
            the file list. This is HEAD by default.

        Returns
        -------
        List[str]
            The list of absolute paths to all Coq files in the project
        """
        commit = self.commit(commit_name)
        files = [
            str(f.abspath)
            for f in commit.tree.traverse()
            if f.abspath.endswith(".v")
        ]
        return sorted(files)

    def get_random_commit(self) -> Commit:
        """
        Return a random `Commit` object from the project repo.

        Returns
        -------
        Commit
            A random `Commit` object from the project repo
        """

        def _get_hash(commit: Commit) -> str:
            return commit.hexsha

        commit_hashes = list(map(_get_hash, self.iter_commits('--all')))
        chosen_hash = random.choice(commit_hashes)
        result = self.commit(chosen_hash)
        return result

    def get_random_file(self, commit_name: Optional[str] = None) -> CoqDocument:
        """
        Return a random Coq source file from the repo.

        The commit may be specified or left to be chosen at radnom.

        Parameters
        ----------
        commit_name : str or None
            A commit hash, branch name, or tag name indicating where
            the file should be selected from. If None, commit is chosen
            at random.

        Returns
        -------
        CoqDocument
            A random Coq source file in the form of a CoqDocument
        """
        return super().get_random_file(commit_name=commit_name)

    def get_random_sentence(
            self,
            filename: Optional[str] = None,
            glom_proofs: bool = True,
            commit_name: Optional[str] = None) -> str:
        """
        Return a random sentence from the project.

        Filename and commit are random unless they are provided.

        Parameters
        ----------
        filename : Optional[str], optional
            Absolute path to file to load sentence from, by default None
        glom_proofs : bool, optional
            Boolean flag indicating whether proofs should form their own
            pseudo-sentences, by default True
        commit_name : Optional[str], optional
            Commit name (hash, branch name, tag name) to load sentence
            from, by default None

        Returns
        -------
        str
            A random sentence from the project
        """
        return super().get_random_sentence(
            filename,
            glom_proofs,
            commit_name=commit_name)

    def get_random_sentence_pair_adjacent(
            self,
            filename: Optional[str] = None,
            glom_proofs: bool = True,
            commit_name: Optional[str] = None) -> List[str]:
        """
        Return a random adjacent sentence pair from the project.

        Filename and commit are random unless they are provided.

        Parameters
        ----------
        filename : Optional[str], optional
            Absolute path to file to load sentences from, by default
            None
        glom_proofs : bool, optional
            Boolean flag indicating whether proofs should form their own
            pseudo-sentences, by default True
        commit_name : Optional[str], optional
            Commit name (hash, branch name, tag name) to load sentences
            from, by default None

        Returns
        -------
        List of str
            A list of two adjacent sentences from the project, with the
            first sentence chosen at random
        """
        return super().get_random_sentence_pair_adjacent(
            filename,
            glom_proofs,
            commit_name=commit_name)


class ProjectDir(ProjectBase):
    """
    Class for representing a Coq project.

    This class makes no assumptions about whether the project directory
    is a git repository or not.
    """

    def __init__(self, dir_abspath: str, *args, **kwargs):
        """
        Initialize Project object.
        """
        self.working_dir = dir_abspath
        super().__init__(dir_abspath, *args, **kwargs)
        if not self._traverse_file_tree():
            raise DirHasNoCoqFiles(f"{dir_abspath} has no Coq files.")

    @property
    def path(self) -> str:  # noqa: D102
        return self.working_dir

    def _get_file(self, filename: str, *args, **kwargs) -> CoqDocument:
        """
        Get specific Coq file and return the corresponding CoqDocument.

        Parameters
        ----------
        filename : str
            The absolute path to the file

        Returns
        -------
        CoqDocument
            The corresponding CoqDocument

        Raises
        ------
        ValueError
            If given `filename` does not end in ".v"

        Warns
        -----
        UserWarning
            If either of `args` or `kwargs` is nonempty.
        """
        if args or kwargs:
            warnings.warn(
                f"Unexpected additional arguments to Project[{self.name}]._get_file.\n"
                f"    args: {args}\n"
                f"    kwargs: {kwargs}")
        return CoqDocument(
            pathlib.Path(filename).relative_to(self.path),
            project_path=self.path,
            source_code=CoqParser.parse_source(filename))

    def _pre_get_file(self, **kwargs):
        """
        Do nothing.
        """
        pass

    def _pre_get_random(self, **kwargs):
        """
        Do nothing.
        """
        pass

    def _traverse_file_tree(self) -> List[CoqDocument]:
        """
        Traverse the file tree and return a list of Coq file objects.
        """
        files = pathlib.Path(self.working_dir).rglob("*.v")
        out_files = []
        for file in files:
            out_files.append(
                CoqDocument(
                    file.relative_to(self.path),
                    project_path=self.path,
                    source_code=CoqParser.parse_source(file)))
        return out_files

    def get_file_list(self, **kwargs) -> List[str]:
        """
        Return a list of all Coq files associated with this project.

        Returns
        -------
        List[str]
            The list of absolute paths to all Coq files in the project
        """
        files = [
            str(i.resolve())
            for i in pathlib.Path(self.working_dir).rglob("*.v")
        ]
        return sorted(files)
