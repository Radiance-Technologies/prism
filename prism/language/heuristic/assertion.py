"""
Supplies heuristic utilities for parsing theorems and proofs.
"""
from dataclasses import dataclass
from typing import List, Optional
from warnings import warn

from radpytools.dataclasses import default_field

from .util import ParserUtils


@dataclass
class Assertion:
    """
    An abstraction of something that needs to be proved.
    """

    document_index: str
    """
    The document in which the assertion resides.
    """
    statement: Optional[str]  # None if a program
    """
    The statement that requires a proof.
    """
    is_program: bool
    """
    Whether this statement is a Program or not.

    A Program may require multiple proofs.
    """
    proofs: List[List[str]] = default_field([])  # or obligations
    """
    The proof(s) of the statement.

    Multiple proofs are only expected if the statement is a Program.
    """

    @property
    def defined(self) -> bool:
        """
        Return whether the assertion is defined.

        An assertion is defined when all of its proofs are concluded.
        """
        # do not use all or any to avoid unnecessary checks after first
        # incomplete proof
        for proof in self.proofs:
            if not proof or not ParserUtils.is_proof_ender(proof[-1], True):
                return False
        return len(self.proofs) > 0

    @property
    def in_proof(self) -> bool:
        """
        Return whether the assertion state is mid-proof.
        """
        return (
            self.proofs and self.proofs[-1]
            and not ParserUtils.is_proof_ender(self.proofs[-1][-1],
                                               True))

    @property
    def is_complete(self) -> bool:
        """
        Return whether the assertion is considered complete.

        An assertion is complete when all of its proofs are terminated
        or it has no proofs to begin with (as may be the case for
        certain conditional theorem starters like Definition or
        Example).
        """
        # do not use all or any to avoid unnecessary checks after first
        # incomplete proof
        for proof in self.proofs:
            if (proof and any(not ParserUtils.is_query(tac,
                                                       True) for tac in proof)
                    and not ParserUtils.is_proof_ender(proof[-1],
                                                       True)):
                return False
        return True

    def admit(self) -> None:
        """
        Admit the proof as is.

        Appends the ``Admitted.`` command to the end of each incomplete
        proof in the theorem.
        """
        for proof in self.proofs:
            if not proof or not ParserUtils.is_proof_ender(proof[-1], True):
                proof.append('Admitted.')

    def apply_tactic(self, tactic: str, braces_and_bullets: List[str]) -> None:
        """
        Apply a tactic to proving the statement.

        Parameters
        ----------
        tactic : str
            The tactic sentence.
        braces_and_bullets : List[str]
            Any preceding brace or bullet sentences.
        """
        if not self.proofs:
            self.start_proof(None, [])
        self.proofs[-1].extend(braces_and_bullets)
        self.proofs[-1].append(tactic)

    def start_proof(
            self,
            starter: Optional[str],
            braces_and_bullets: Optional[List[str]] = None) -> None:
        """
        Start a new proof.

        Parameters
        ----------
        starter : str
            The sentence starting the proof, e.g., ``"Proof."``.
        braces_and_bullets : List[str] | None
            Any preceding brace or bullet sentences, asserted to be
            empty.
        """
        # assert there is either
        # * a theorem statement without proof, or
        # * a program with zero or more proofs
        assert self.is_program or (
            not self.is_program and len(self.proofs) <= 1)
        assert braces_and_bullets is None or not braces_and_bullets or (
            braces_and_bullets and ParserUtils.is_proof_ender(starter,
                                                              True))
        if self.in_proof:
            assert starter is not None
            self.proofs[-1].append(starter)
        else:
            self.proofs.append([] if starter is None else [starter])

    def end_proof(self, ender: str, braces_and_bullets: List[str]) -> None:
        """
        Conclude a proof.

        Parameters
        ----------
        starter : str
            The sentence ending the proof, e.g., ``"Qed."``.
        braces_and_bullets : List[str]
            Any preceding brace or bullet sentences.
        """
        # assert we are in a proof
        if not (self.proofs and self.proofs[-1]):
            warn(
                "Possible syntax error: proof termination without proof start "
                f"in {self.document_index}")
            if not self.proofs:
                self.proofs.append([])
        self.proofs[-1].extend(braces_and_bullets)
        self.proofs[-1].append(ender)

    @classmethod
    def discharge(
            cls,
            document_index: str,
            theorem: 'Assertion',
            result: List[str],
            glom_proofs: bool,
            defined_only: bool = False) -> None:
        """
        Discharge an assertion's sentences to the end of a list.

        Parameters
        ----------
        document_index : str
            A unique identifier of the theorem's corresponding document.
        theorem : Assertion
            The assertion.
        result : List[str]
            A list of sentences in order of their appearance in the
            document identified by `document_index`.
        glom_proofs : bool
            Whether to join the sentences of each proof together
            (resulting in a single "sentence" per proof) or not.
        defined_only : bool, optional
            Whether to discharge only defined assertions or not.
        """
        if theorem.statement is not None and not theorem.is_program:
            result.append(theorem.statement)
        if not theorem.is_complete:
            if not defined_only:
                warn(
                    "Found an unterminated proof environment in "
                    f"{document_index}. "
                    "Admitting proof and continuing.")
                theorem.admit()
        proofs = theorem.proofs
        accum = result.extend
        if glom_proofs:
            proofs = [" ".join(proof) for proof in proofs]
            accum = result.append
        for proof in proofs:
            accum(proof)

    @classmethod
    def discharge_all(
            cls,
            document_index: str,
            assertions: List['Assertion'],
            result: List[str],
            glom_proofs: bool,
            defined_only: bool = False) -> None:
        """
        Discharge a stack of assertions sequentially.

        Parameters
        ----------
        document_index : str
            _description_
        assertions : List[Assertion]
            A stack of assertions, presumably nested and in order of
            increasing depth.
            Assertions are discharged in reverse order by popping the
            deepest theorem off of the stack one after another.
        result : List[str]
            A list of sentences in order of their appearance in the
            document identified by `document_index`.
        glom_proofs : bool
            Whether to join the sentences of each proof together
            (resulting in a single "sentence" per proof) or not.
        defined_only : bool, optional
            Whether to discharge only defined assertions or not.
        """
        while assertions:
            assertion = assertions.pop()
            num_results = len(result)
            glom_proofs = cls.discharge(
                document_index,
                assertion,
                result,
                glom_proofs,
                defined_only)
            if defined_only and len(result) == num_results:
                # We reached an unfinished assertion.
                # Restore popped assertion and stop discharging.
                assertions.append(assertion)
