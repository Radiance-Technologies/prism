"""
Data utilities related to Coq identifiers.
"""
import enum
import re
from functools import partial
from typing import Dict, List, NamedTuple, Optional, Sequence, Set, Union

from prism.interface.coq.serapi import SerAPI
from prism.util.identity import identity
from prism.util.iterable import CallableIterator
from prism.util.re import regex_from_options
from prism.util.string import quote_escape, unquote


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
    rf"\(\s*DirPath\s*\((?P<DirPath>(?:\s*{id_re(None).pattern})*)\)\s*\)")
_serqualid_contexts = [
    r"(?P<CPatAtom>\(\s*CPatAtom\s*\(\s*\(\s*\(\s*v\s*)",
    r"(?P<CRef>\(\s*CRef\s*\(\s*\(\s*v\s*)"
]
_serqualid_contexts = regex_from_options(_serqualid_contexts, False, False)
serqualid_re = re.compile(
    rf"{_serqualid_contexts.pattern}?\(\s*Ser_Qualid\s*{dirpath_re.pattern}\s*"
    rf"{id_re('str_of_qualid').pattern}\s*\)")
loc_re = re.compile(
    r"\(\s*loc\s*\(\(\(\s*fname\s+ToplevelInput\)\s*\(\s*line_nb\s+\d+\)\s*"
    r"\(\s*bol_pos\s+\d+\)\s*\(\s*line_nb_last\s+\d+\)\s*\(\s*bol_pos_last\s+\d+\)\s*"
    r"\(\s*bp\s+\d+\)\s*\(\s*ep\s+\d+\)\)\)\)")
lident_re = re.compile(
    rf"\(\s*v\s*{id_re('str_of_lident').pattern}\s*\)\s*"
    rf"(?={loc_re.pattern})")
lname_re = re.compile(
    rf"\(\s*v\s*\(\s*Name\s*{id_re('str_of_lname').pattern}\s*\)\s*\)\s*"
    rf"(?={loc_re.pattern})")
ident_re = regex_from_options(
    [serqualid_re.pattern,
     lident_re.pattern,
     lname_re.pattern],
    False,
    False)


class IdentType(enum.Enum):
    """
    Enumerate different types of identifiers depending upon context.

    Notes
    -----
    The names of these enumerated values correspond to kernel type and
    variant constructor names in the Coq source code.
    """

    # place all variants of Ser_Qualid before Ser_Qualid so that a
    # simple <= operator can be used to detect any variant
    CPatAtom = enum.auto()
    """
    A qualified ID appearing in a pattern match, e.g., ``p`` in ``S p``,
    where ``S`` is the natural number successor constructor.
    A `Ser_Qualid` with additional context.
    This may reference a global ID or bind a new name.
    """
    CRef = enum.auto()
    """
    A reference to a qualified ID appearing, for example, in local
    binders as the name of the bound type.
    A `Ser_Qualid` with additional context.
    """
    Ser_Qualid = enum.auto()
    """
    A qualified id, which may appear in the bodies of many commands.

    Notes
    -----
    Curiously, this also appears in the ASTs of ``Require`` commands but
    never matches the name of the required library (instead matching
    ``"object"`` in all observations).
    """
    lident = enum.auto()
    """
    A located ID, which may appear in theorem statements or other
    contexts.

    This ID cannot be qualified.
    """
    lname = enum.auto()
    """
    A located name, which may appear in ``Definition``s, local binders,
    or more contexts.

    This name cannot be qualified.
    """


class Identifier(NamedTuple):
    """
    A scoped identifier that can be referenced within Coq commands.
    """

    type: IdentType
    """
    The type of the identifier.
    """
    string: str
    """
    The identifier itself.
    """


def ident_of_match(ident: re.Match) -> Identifier:
    """
    Convert a matched identifier pattern to a dot-delimited path.

    Parameters
    ----------
    ident : re.Match
        A match obtained from `ident_re`.

    Returns
    -------
    Identifier
        A dot-delimited representation of the given implicit qualified
        ID as it would appear in code.
    """
    serqualid = ident['str_of_qualid']
    lident = ident['str_of_lident']
    lname = ident['str_of_lname']
    if serqualid is not None:
        dirpath = [
            unquote(d['id'])
            for d in re.finditer(id_re('id'),
                                 ident['DirPath'])
        ]
        dirpath.append(unquote(serqualid))
        ident_str = ".".join(dirpath)
        if ident['CPatAtom'] is not None:
            ident_type = IdentType.CPatAtom
        elif ident['CRef'] is not None:
            ident_type = IdentType.CRef
        else:
            ident_type = IdentType.Ser_Qualid
    elif lident is not None:
        ident_str = unquote(lident)
        ident_type = IdentType.lident
    else:
        assert lname is not None
        ident_str = unquote(lname)
        ident_type = IdentType.lname
    return Identifier(ident_type, ident_str)


def id_of_str(txt: str) -> str:
    """
    Embed a string into a serialized ``Id`` s-expression.
    """
    return f"(Id {quote_escape(txt, quotes_only=True)})"


def sexp_str_of_ident(ident: Identifier) -> str:
    """
    Convert a qualified identifier into a serialized s-expression.

    The s-expression is based on how the identifier would be
    represented in an AST using Coq kernel types.

    Parameters
    ----------
    ident_str : Identifier
        A qualified identifier.

    Returns
    -------
    str
        The s-expression representation of the given identifier.
    """
    ident_type = ident.type
    if ident_type <= IdentType.Ser_Qualid:
        parts = ident.string.split(".")
        ident = id_of_str(parts[-1])
        dirpath = ["(DirPath("]
        dirpath.extend([id_of_str(d) for d in parts[0 :-1]])
        dirpath.append("))")
        dirpath = "".join(dirpath)
        sexp = f"(Ser_Qualid{dirpath}{ident})"
        if ident_type == IdentType.CPatAtom:
            sexp = f"(CPatAtom(((v{sexp}"
        elif ident_type == IdentType.CRef:
            sexp = f"(CRef((v{sexp}"
    else:
        ident_str = id_of_str(ident.string)
        if ident_type == IdentType.lident:
            sexp = f"(v{ident_str})"
        else:
            assert ident_type == IdentType.lname
            sexp = f"(v(Name{ident_str}))"
    return sexp


def qualify_ident(
        serapi: SerAPI,
        global_id_cache: Dict[str,
                              str],
        local_id_cache: Set[str],
        ident: Identifier,
        modpath: str) -> Identifier:
    """
    Fully qualify the given identifier.

    Parameters
    ----------
    ident : Identifier
        An identifier as it appears in the AST.
    global_id_cache : Dict[str, str]
        A map from unqualified or partially qualified IDs to fully
        qualified variants, which will be modified in-place.
    local_id_cache : Set[str]
        A set of locally defined IDs that shadow global definitions,
        which will be modified in-place.
    modpath : str
        The module path to use in place of ``"SerTop."`` for locally
        defined identifiers or to prepend for appropriate
        unqualified identifiers.

    Returns
    -------
    str
        The fully qualified identifier.
    """
    # make identity unambiguous when the AST is used later in
    # a non-interactive context
    ident_str = ident.string
    ident_type = ident.type
    if ident_type == IdentType.lident or ident_type == IdentType.lname:
        # a new local identifier is being introduced and will shadow
        # previous equivalent names for the rest of the AST
        local_id_cache.add(ident_str)
    if (ident_str in local_id_cache and ident_type != IdentType.CPatAtom):
        # a locally introduced identifier
        fully_qualified = '.'.join([modpath, ident_str])
    else:
        # probably a global identifier
        try:
            fully_qualified = global_id_cache[ident_str]
        except KeyError:
            fully_qualified = serapi.query_full_qualid(ident_str)
            if fully_qualified is None:
                fully_qualified = ident_str
            if ident_type == IdentType.CPatAtom and '.' not in fully_qualified:
                # This identifier does not exist in the
                # global environment.
                # Mark it as locally defined.
                local_id_cache.add(fully_qualified)
                fully_qualified = '.'.join([modpath, fully_qualified])
            else:
                if fully_qualified.startswith("SerTop."):
                    fully_qualified = modpath + fully_qualified[6 :]
                global_id_cache[ident_str] = fully_qualified
    return Identifier(ident_type, fully_qualified)


def _get_all_idents(
    ast: str,
    ordered: bool = False,
    qualify: bool = False,
    serapi: Optional[SerAPI] = None,
    modpath: str = "SerTop",
    global_id_cache: Optional[Dict[str,
                                   str]] = None
) -> Union[List[Identifier],
           Set[Identifier]]:
    """
    Get all of the identifiers referenced in the given serialized AST.

    Parameters
    ----------
    ast : str
        A serialized AST.
    ordered : bool, optional
        Whether to return identifiers in the order in which they appear
        in the `ast` or to return an unordered set of all identifiers in
        `ast`, by default False.
    qualify : bool, optional
        Whether to fully qualify all encountered identifiers in the
        `ast` in the returned list or set, by default False.
    serapi : Optional[SerAPI], optional
        An interactive session from which fully qualified identifiers
        can be obtained, by default None.
    modpath : str, optional
        The logical library path one would use if the contents of the
        `serapi` session were dumped to file and imported or required in
        another, by default ``"SerTop"``.
    global_id_cache : Optional[Dict[str, str]], optional
        A map from unqualified or partially qualified IDs to fully
        qualified variants, which will be modified in-place.
        By default None.

    Returns
    -------
    Union[List[Identifier], Set[Identifier]]
        An `ordered` list or set of all identifiers contained in the
        AST.

    Raises
    ------
    ValueError
        If `qualify` is True and `serapi` is None.
    """
    if qualify and serapi is None:
        raise ValueError("Cannot qualify identifiers without a SerAPI session.")
    elif qualify:
        if global_id_cache is not None:
            global_id_cache = {}
        local_id_cache = set()
        qualify = partial(
            qualify_ident,
            serapi,
            global_id_cache,
            local_id_cache,
            modpath=modpath)
    else:
        qualify = identity
    matches = re.finditer(ident_re, ast)
    if ordered:
        container = list
    else:
        container = set
    return container(qualify(ident_of_match(m)) for m in matches)


get_all_idents = partial(
    _get_all_idents,
    qualify=False,
    serapi=None,
    modpath="",
    id_cache=None)
"""
Get all of the identifiers referenced in the given serialized AST.

Parameters
----------
ast : str
    A serialized AST.
ordered : bool, optional
    Whether to return identifiers in the order in which they appear
    in the `ast` or to return an unordered set of all identifiers in
    `ast`, by default False.

Returns
-------
Union[List[Identifier], Set[Identifier]]
    An `ordered` list or set of all identifiers contained in the
    AST.
"""


def get_all_qualified_idents(
    serapi: SerAPI,
    modpath: str,
    ast: str,
    ordered: bool = False,
    id_cache: Optional[Dict[str,
                            str]] = None
) -> Union[List[Identifier],
           Set[Identifier]]:
    """
    Fully qualify all identifiers appearing in the given serialized AST.

    Parameters
    ----------
    serapi : SerAPI
        An interactive session from which fully qualified identifiers
        can be obtained.
    modpath : str
        The logical library path one would use if the contents of the
        `serapi` session were dumped to file and imported or required in
        another.
    ast : str
        A serialized AST.
    ordered : bool, optional
        Whether to return identifiers in the order in which they appear
        in the `ast` or to return an unordered set of all identifiers in
        `ast`, by default False.
    id_cache : Optional[Dict[str, str]], optional
        A map from unqualified or partially qualified IDs to fully
        qualified variants, which will be modified in-place.
        By default None.

    Returns
    -------
    Union[List[Identifier], Set[Identifier]]
        An `ordered` list or set of all identifiers contained in the
        AST.
    """
    return _get_all_idents(ast, ordered, True, serapi, modpath, id_cache)


def replace_idents(sexp: str, replacements: Sequence[Identifier]) -> str:
    """
    Perform a one-to-one replacement of identifiers in the given AST.

    Parameters
    ----------
    sexp : str
        A serialized AST.
    replacements : Sequence[Identifier]
        A sequence of new identifiers to be substituted into each match
        of `ident_re` in `sexp` in the order of iteration.

    Returns
    -------
    str
        The given serialized AST albeit with replaced identifiers.
    """
    repl_it = CallableIterator(replacements)
    return re.sub(ident_re, repl_it, sexp)


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
        qualified variants, which will be modified in-place.
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
    identifiers = get_all_qualified_idents(
        serapi,
        modpath,
        sexp,
        ordered=True,
        id_cache=id_cache)
    replacements = [sexp_str_of_ident(ident) for ident in identifiers]
    return replace_idents(sexp, replacements)
