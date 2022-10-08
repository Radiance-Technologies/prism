"""
Abstractions of Coq goals and hypotheses.
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple

from prism.util.radpytools.dataclasses import default_field


@dataclass
class Hypothesis:
    """
    An hypothesis.

    Notes
    -----
    This class loosely corresponds to the ``hyp`` type defined in
    ``coq-serapi/serapi/serapi_goals.mli``.
    """

    idents: List[str]
    """
    Identifiers within the hypothesis.
    """
    term: Optional[str]
    """
    The value assigned to each identifier, if any.
    """
    # QUESTION (AG): Is there a one-to-one mapping between terms and
    # identifiers? I'm not sure how there can be multiple of these since
    # the field arises from an `option` in serapi_goals.mli.
    type: str
    """
    The type of each identifier.
    """
    sexp: str
    """
    The serialization of the identifier's Coq kernel type.
    """

    def __str__(self) -> str:
        """
        Pretty-print the hypothesis similar to its form in CoqIDE.
        """
        value = f':= {self.term}' if self.term is not None else ""
        return f"{','.join(self.idents)} {value} : {self.type}"


@dataclass
class Goal:
    """
    A goal of a proof.

    Notes
    -----
    This class loosely corresponds to the ``reified_goal`` type defined
    in ``coq-serapi/serapi/serapi_goals.mli``.
    """

    id: int
    """
    A unique identifier of the goal.
    """
    type: str
    """
    The type of the goal.

    In essence, a statement of the goal itself.
    """
    sexp: str
    """
    The serialization of the goal's Coq kernel type.
    """
    hypotheses: List[Hypothesis]
    """
    A list of hypotheses pertaining to this goal.
    """

    def __str__(self) -> str:
        """
        Pretty-print the goal similar to its form in CoqIDE.
        """
        hypotheses = '\n'.join([str(h) for h in self.hypotheses])
        return '\n'.join(
            [hypotheses,
             '______________________________________',
             self.type])


@dataclass
class Goals:
    """
    The collection of unfinished goals within the current context.

    Notes
    -----
    This class loosely corresponds to the ``ser_goals`` type defined in
    ``coq-serapi/serapi/serapi_goals.mli``.
    """

    foreground_goals: List[Goal] = default_field([])
    # TODO (AG): Figure out the meaning of the left versus right goals.
    background_goals: List[Tuple[List[Goal], List[Goal]]] = default_field([])
    shelved_goals: List[Goal] = default_field([])
    abandoned_goals: List[Goal] = default_field([])
