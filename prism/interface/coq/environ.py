"""
Abstractions of Coq contexts and global environments.
"""

import typing
from dataclasses import dataclass
from itertools import chain
from typing import Dict, List, Optional, Tuple, Union

from prism.interface.coq.names import interpolate_names
from prism.util.radpytools import PathLike


@dataclass
class Constant:
    """
    A constant definition.

    Notes
    -----
    This class loosely corresponds to the ``constant_body`` type defined
    in ``coq/kernel/declarations.ml``.
    """

    physical_path: PathLike
    """
    The physical path to the file in which the constant is defined.
    """
    short_id: str
    """
    The minimally qualified name of the constant within the current
    context.
    """
    full_id: str
    """
    The fully qualified name of the constant.
    """
    term: Optional[str]
    """
    The value assigned to the constant.
    """
    type: str
    """
    The type of the constant.
    """
    sort: str
    """
    The sort of the constant's type.
    """
    opaque: Optional[bool]
    """
    Whether the definition is opaque (True), transparent (False), or
    simply declared / a primitive (None).
    """
    sexp: str
    """
    The s-expression of the constant's type (i.e., of its
    ``(Constant, constant_body)`` kernel representation).
    """


@dataclass
class OneInductive:
    """
    A single inductive type of a block of mutually inductive types.

    Notes
    -----
    This class loosely corresponds to the ``one_inductive_body`` type
    in ``coq/kernel/declarations.ml``.
    """

    short_id: str
    """
    The minimally qualified name of the inductive type.
    """
    full_id: str
    """
    The fully qualified name of the inductive type.
    """
    constructors: List[Tuple[str, str]]
    """
    A list of tuples pairing constructor names and types.
    """


@dataclass
class MutualInductive:
    """
    A (mutually) inductive type declaration.

    Note that a single inductive type is considered a special case in
    the sense that it is mutually inductive with itself.

    See https://coq.inria.fr/refman/language/core/inductive.html#inductive-types
    for more information about inductive type declarations.

    Notes
    -----
    This class loosely corresponds to the ``mutual_inductive_body`` type
    in ``coq/kernel/declarations.ml``.
    """  # noqa: W505

    physical_path: PathLike
    """
    The physical path to the file in which the mutually inductive type
    is defined.
    """
    short_id: str
    """
    The minimally qualified name of the main (top-level) type in the
    inductive declaration (i.e., the one following the ``Inductive``
    Vernacular command).
    """
    full_id: str
    """
    The fully qualified version of `short_ident`.
    """
    blocks: List[OneInductive]
    """
    A sequence of mutually inductive blocks that together define the
    inductive type.
    """
    is_record: bool
    """
    Whether this is a record type or not.

    See https://coq.inria.fr/refman/language/core/records.html for more
    information about records.
    """
    sexp: str
    """
    The s-expression of the mutually inductive type (i.e., of its
    ``(MutInd, mutual_inductive_body)`` kernel representation).
    """


@dataclass
class Environment:
    """
    A global environment that gives the context for an implicit state.

    The environment only considers declarations made within the current
    file and ``Require``d libraries.

    Notes
    -----
    This class loosely corresponds to the ``env_globals`` field of the
    ``coq/kernel/environ.mli:env`` record type.
    """

    constants: List[Constant]
    """
    A list of constants (definitions, lemmas) in the global environment.
    """
    inductives: List[MutualInductive]
    """
    A list of inductive types in the global environment.
    """

    def asdict(self) -> Dict[str, Union[Constant, MutualInductive]]:
        """
        Represent the environment as a map from names to definitions.

        Returns
        -------
        Dict[str, Union[Constant, MutualInductive]]
            A dictionary mapping qualified names to their corresponding
            `Constant` or `MutualInductive` definitions.
        """
        env = {}
        for decl in chain(self.constants, self.inductives):
            decl = typing.cast(Union[Constant, MutualInductive], decl)
            for qualid in interpolate_names(decl.short_id, decl.full_id):
                env[qualid] = decl
        return env
