"""
Data utilities related to Coq identifiers.
"""
import re
from typing import Dict, Optional

from prism.interface.coq.serapi import SerAPI
from prism.util.iterable import CallableIterator


def id_re(capture_name: Optional[str]) -> re.Pattern:
    """
    Make a regex that matches a Coq kernel ``Id`` type's s-expression.

    Parameters
    ----------
    capture_name : Optional[str]
        If not None, then capture the ID in a group with the name
        `capture_name`.

    Returns
    -------
    re.Pattern
        The compiled regex pattern.
    """
    if capture_name is not None:
        str_of_id = rf"(?P<{capture_name}>[^\)\s]+)"
    else:
        str_of_id = r"[^\)\s]+"
    return re.compile(rf"\(\s*Id\s+{str_of_id}\)")


dirpath_re = re.compile(
    rf"\(\s*DirPath\s*\((?P<dirpath>(?:\s*{id_re(None).pattern})*)\)\s*\)")
serqualid_re = re.compile(
    rf"\(\s*Ser_Qualid\s*{dirpath_re.pattern}\s*"
    rf"{id_re('str_of_qualid').pattern}\s*\)")


def qualid_str_of_serqualid_match(serqualid: re.Match) -> str:
    """
    Convert a matched ``Ser_Qualid`` pattern to a dot-delimited path.

    Parameters
    ----------
    serqualid : re.Match
        A match obtained from `serqualid_re`.

    Returns
    -------
    str
        A dot-delimited representation of the given implicit qualified
        ID as it would appear in code.
    """
    dirpath = [d['id'] for d in re.finditer(id_re('id'), serqualid['dirpath'])]
    dirpath.append(serqualid['str_of_qualid'])
    return ".".join(dirpath)


def id_of_str(txt: str) -> str:
    """
    Embed a string into a serialized ``Id`` s-expression.
    """
    return f"(Id {txt})"


def sexp_str_of_qualid(qualid_str: str, modpath: str) -> str:
    """
    Convert a qualified identifier into a serialized s-expression.

    The s-expression is based on how the identifier would be
    represented in an AST using Coq kernel types.

    Parameters
    ----------
    qualid_str : str
        A qualified identifier.
    modpath : str
        The module path to use in place of ``"SerTop."`` for locally
        defined identifiers.

    Returns
    -------
    str
        The s-expression representation of the given identifier.
    """
    parts = qualid_str.split(".")
    if parts[0] == "SerTop":
        # make identity unambiguous when the AST is used later in
        # a non-interactive context
        parts[0] = modpath
    ident = id_of_str(parts[-1])
    dirpath = ["(DirPath("]
    dirpath.extend([id_of_str(d) for d in parts[0 :-1]])
    dirpath.append("))")
    dirpath = "".join(dirpath)
    return f"(Ser_Qualid{dirpath}{ident})"


def expand_idents(
        serapi: SerAPI,
        id_cache: Dict[str,
                       str],
        sexp: str,
        modpath: str) -> str:
    """
    Fully qualify all identifiers in a given AST.

    Parameters
    ----------
    serapi : SerAPI
        An interactive `sertop` session.
    id_cache : Dict[str, str]
        A map from unqualified or partially qualified IDs to fully
        qualified variants.
    sexp : str
        A serialized s-expression representing the AST of some command
        executed in `serapi`.
    modpath : str
        The logical library path one would use if the contents of the
        `serapi` session were dumped to file and imported or required in
        another.

    Returns
    -------
    str
        The given serialized `sexp` with all identifiers replaced by
        their fully qualified versions.

    Notes
    -----
    Currently, only ``Ser_Qualid`` identifiers are expanded.
    """

    def qualify(qualid_str: str) -> str:
        """
        Fully qualify the given identifier.

        Parameters
        ----------
        qualid_str : str
            An identifier as it appears in the AST.

        Returns
        -------
        str
            The fully qualified identifier.
        """
        try:
            queried = id_cache[qualid_str]
        except KeyError:
            queried = serapi.query_full_qualid(qualid_str)
            id_cache[qualid_str] = queried
        return qualid_str if queried is None else queried

    matches = re.finditer(serqualid_re, sexp)
    replacements = [
        sexp_str_of_qualid(qualify(qualid_str_of_serqualid_match(m)),
                           modpath) for m in matches
    ]
    repl_it = CallableIterator(replacements)
    return re.sub(serqualid_re, repl_it, sexp)
