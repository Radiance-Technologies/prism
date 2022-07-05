"""
Provides an object-oriented abstraction of OPAM switches.
"""
import logging
import re
from dataclasses import dataclass
from os import PathLike
from typing import ClassVar, Optional

from .version import OCamlVersion, Version

logger = logging.getLogger(__file__)
logger.setLevel(logging.DEBUG)


@dataclass(frozen=True)
class OpamSwitch:
    """
    An OPAM switch.

    Note that OPAM must be installed to use all of the features of this
    class.

    .. warning::
        This class does not yet fully support the full expressivity of
        OPAM dependencies as documented at
        https://opam.ocaml.org/blog/opam-extended-dependencies/.
    """

    _whitespace_regex: ClassVar[re.Pattern] = re.compile(r"\s+")
    _newline_regex: ClassVar[re.Pattern] = re.compile("\n")
    name: Optional[str] = None
    coq_version: Optional[Version] = None
    ocaml_version: Optional[OCamlVersion] = None
    """
    The name of the switch, by default None.

    If None, then this implies usage of the default switch.
    Equivalent to setting ``$OPAMSWITCH`` to `name`.
    """
    root: Optional[PathLike] = None
    """
    The current root path, by default None.

    If None, then this implies usage of the default root.
    Equivalent to setting ``$OPAMROOT`` to `root`.
    """
