"""
Supplies heuristic utilities for parsing theorems and proofs.
"""
from dataclasses import dataclass
from typing import Generic, Iterable, List, Optional, Type, TypeVar
from warnings import warn

from radpytools.dataclasses import default_field

from .util import ParserUtils

T = TypeVar('T')


@dataclass
class Assertion(Generic[T]):
    """
    An abstraction of something that needs to be proved.
    """

    statement: Optional[T]  # None if a program
    """
    The statement that requires a proof.
    """
    is_program: bool
    """
    Whether this statement is a Program or not.

    A Program may require multiple proofs.
    """
    proofs: List[List[T]] = default_field([])  # or obligations
    """
    The proof(s) of the statement.

    Multiple proofs are only expected if the statement is a Program.
    """
    parser_utils_cls: Type[ParserUtils] = ParserUtils
    """
    The class to use that provides parser utilities.
    """

    @property
    def in_proof(self) -> bool:
        """
        Return whether the assertion state is mid-proof.
        """
        return (
            self.proofs and self.proofs[-1]
            and not self.parser_utils_cls.is_proof_ender(self.proofs[-1][-1]))

    def apply_tactic(self, tactic: T, braces_and_bullets: List[T]) -> None:
        """
        Apply a tactic to proving the statement.

        Parameters
        ----------
        tactic : T
            The tactic sentence.
        braces_and_bullets : List[T]
            Any preceding brace or bullet sentences.
        """
        if not self.proofs:
            self.start_proof(None, [])
        self.proofs[-1].extend(braces_and_bullets)
        self.proofs[-1].append(tactic)

    def start_proof(
            self,
            starter: Optional[T],
            braces_and_bullets: Optional[List[T]] = None) -> None:
        """
        Start a new proof.

        Parameters
        ----------
        starter : T
            The sentence starting the proof, e.g., ``"Proof."``.
        braces_and_bullets : List[T] | None
            Any preceding brace or bullet sentences, asserted to be
            empty.
        """
        # assert there is either
        # * a theorem statement without proof, or
        # * a program with zero or more proofs
        assert self.is_program or (
            not self.is_program and len(self.proofs) <= 1)
        assert braces_and_bullets is None or not braces_and_bullets
        if self.in_proof:
            assert starter is not None
            self.proofs[-1].append(starter)
        else:
            self.proofs.append([] if starter is None else [starter])

    def end_proof(self, ender: T, braces_and_bullets: List[T]) -> None:
        """
        Conclude a proof.

        Parameters
        ----------
        starter : T
            The sentence ending the proof, e.g., ``"Qed."``.
        braces_and_bullets : List[T]
            Any preceding brace or bullet sentences.
        """
        # assert we are in a proof
        assert self.proofs and self.proofs[-1]
        self.proofs[-1].extend(braces_and_bullets)
        self.proofs[-1].append(ender)

    @classmethod
    def discharge(
            cls,
            document_index: str,
            theorem: 'Assertion',
            result: List[str],
            glom_proofs: bool,
            parser_utils_cls: Type[ParserUtils] = ParserUtils) -> bool:
        """
        Discharge an assertion's sentences to the end of a list.

        Parameters
        ----------
        document_index : str
            A unique identifier of the theorem's corresponding document.
        theorem : Assertion
            The assertion.
        result : List[T]
            A list of sentences in order of their appearance in the
            document identified by `document_index`.
        glom_proofs : bool
            Whether to join the sentences of each proof together
            (resulting in a single "sentence" per proof) or not.
        parser_utils_cls : Type[ParserUtils], optional
            ParserUtils class to use, by default `ParserUtils`

        Returns
        -------
        bool
            Whether to continue glomming proofs together.
            If `glom_proofs` is False, then this returned value will be
            False.
            If `glom_proofs` is True, then the return value will be True
            unless an unterminated proof is encountered.
        """
        if theorem.statement is not None and not theorem.is_program:
            result.append(theorem.statement)
        proofs = theorem.proofs
        for proof in proofs:
            if not parser_utils_cls.is_proof_ender(proof[-1]):
                warn(
                    "Found an unterminated proof environment in "
                    f"{document_index}. "
                    "Abandoning proof glomming.")
                glom_proofs = False
        accum = result.extend

        def _join(join_char: str, x: Iterable) -> str:
            return join_char.join([str(i) for i in x])

        if glom_proofs:
            proofs = [_join(" ", proof) for proof in proofs]
            accum = result.append
        for proof in proofs:
            accum(proof)
        return glom_proofs

    @classmethod
    def discharge_all(
            cls,
            document_index: str,
            theorems: List['Assertion'],
            result: List[str],
            glom_proofs: bool,
            parser_utils_cls: Type[ParserUtils] = ParserUtils) -> bool:
        """
        Discharge a stack of theorems sequentially.

        Parameters
        ----------
        document_index : str
            _description_
        theorems : List[Assertion]
            A stack of theorems, presumably nested and in order of
            increasing depth.
            Theorems are discharged in reverse order by popping the
            deepest theorem off of the stack one after another.
        result : List[str]
            A list of sentences in order of their appearance in the
            document identified by `document_index`.
        glom_proofs : bool
            Whether to join the sentences of each proof together
            (resulting in a single "sentence" per proof) or not.
        parser_utils_cls : Type[ParserUtils], optional
            ParserUtils class to use, by default `ParserUtils`

        Returns
        -------
        bool
            Whether to continue glomming proofs together.
            If `glom_proofs` is False, then this returned value will be
            False.
            If `glom_proofs` is True, then the return value will be True
            unless an unterminated proof is encountered.
        """
        for theorem in reversed(theorems):
            glom_proofs = cls.discharge(
                document_index,
                theorem,
                result,
                glom_proofs,
                parser_utils_cls)
        return glom_proofs
