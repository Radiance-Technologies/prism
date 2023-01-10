"""
Potentially useful regular expressions for parsing SerAPI input/output.

Adapted from
https://github.com/princeton-vl/CoqGym/blob/master/re_patterns.py
"""

import re

from prism.interface.coq.unicode import IDENTPART, IDENTSEP, LETTER
from prism.util.re import regex_from_options

PWD_PATTERN = re.compile(r"\(\*\*PWD\*\* (?P<pwd>.*?) \*\*\)")

ML_PATHS_PATTERN = re.compile(
    r"\(\*\*ML_PATH\*\* (?P<ml_paths>.*?) \*\*\)",
    flags=re.DOTALL)

ML_PATH_PATTERN = re.compile(r"(\/[0-9A-Za-z_-]+)+")

LOAD_PATHS_PATTERN = re.compile(
    r"\(\*\*LOAD_PATH\*\* (?P<load_paths>.*?) \*\*\)",
    flags=re.DOTALL)

LOAD_PATH_PATTERN = re.compile(
    r"(?P<logical_path><>|([0-9A-Za-z_-]+(\.[0-9A-Za-z_-]+)*))\s+"
    r"(?P<physical_path>(\/[0-9A-Za-z_-]+)+)\s+"
    r"(?P<implicit>true|false)",
    re.DOTALL,
)

LOC_PATTERN = re.compile(r"\(\*\*LOC\*\* .+?(?=$|\(\*\*LOC)", flags=re.DOTALL)

PARSE_LOC_PATTERN = re.compile(r"Loc.bp = (?P<bp>\d+); Loc.ep = (?P<ep>\d+)")

TAG_PATTERN = re.compile(r"\(\*\*(?P<tag>[A-Z_]+)(\*\*)?(?P<content>.*?)\*\*\)")

UNBOUND_REL_PATTERN = re.compile(r"_UNBOUND_REL_\d+")

ADDED_STATE_PATTERN = re.compile(r"\(Added (?P<state_id>\d+)")

TYPE_PATTERN = re.compile(
    r'\(Pp_tag constr.type\(Pp_string (?P<type>"(?:\\"|[^"])*?"|[^\(\)\s"]*)\)\)'
)

_ident_init_pattern = f"(?:{LETTER.pattern}|{IDENTSEP.pattern})"
"""
A valid initial character for a Coq identifier.

An initial character can be any Unicode letter-like symbol (including
non-breaking space) that is not a digit or single quote.
See `is_valid_ident_initial` in
https://github.com/coq/coq/blob/master/clib/unicode.ml for more
information.
"""
_ident_trailing_pattern = f"(?:{_ident_init_pattern}|{IDENTPART.pattern})"
"""
A valid non-initial character for a Coq identifier.

See `is_valid_ident_trailing` in
https://github.com/coq/coq/blob/master/clib/unicode.ml for more
information.
"""
IDENT_PATTERN = re.compile(f"{_ident_init_pattern}{_ident_trailing_pattern}*")

_new_ident_prefixes = ["Module", "Module Type", "Interactive Module"]
_new_ident_prefixes = "|".join(_new_ident_prefixes)
_new_ident_prefixes = rf"(?:{_new_ident_prefixes}\s+)?"
"""
Optional prefixes that may qualify the type of the new identifier.
"""
_new_ident_canaries = [
    "is defined",
    "is declared",
    "are defined",
    "is recursively defined",
    "is corecursively defined",
    "are recursively defined",
    "are corecursively defined",
    "is redefined",
    "started",
    # "is now a coercion"
]
_new_ident_canaries = "|".join(_new_ident_canaries)
_new_ident_canaries = f"(?:{_new_ident_canaries})"
"""
The key phrases that signal the introduction of an identifier.

An identifier is introduced when a new constant/inductive is defined
(equivalently when a proof is completed).
In the case of Modules, an identifier is "introduced" when the Module
starts and when it ends.
"""
_new_idents = rf"(?:{IDENT_PATTERN.pattern},\s+)*\s*{IDENT_PATTERN.pattern}\s+"
"""
Comma-delimited identifiers.
"""
NEW_IDENT_PATTERN = re.compile(
    rf"{_new_ident_prefixes}(?P<idents>{_new_idents}){_new_ident_canaries}")

NAMED_DEF_ASSUM_PATTERN = re.compile(
    rf"\*\*\* \[\s*(?P<def_assum>{IDENT_PATTERN.pattern})\s.+\]")
"""
Match a named definition or assumption (e.g., a section variable or
admitted theorem) in the feedback of a ``Print All.`` command.
"""
_inductive = rf"[A-Z]\w*\s(?P<ind>{IDENT_PATTERN.pattern})\s+:"
"""
Match a defined type (e.g., an inductive type) structured as a
Vernacular statement.

NOTE: This may fail to detect exotic Vernacular extended types if
Unicode characters are allowed similar to idents.
"""
_mutual_inductive = rf"\s+with\s(?P<mind>{IDENT_PATTERN.pattern})\s+:"
"""
Match additional types in a mutually inductive body.
"""
_constant = rf"(?P<constant>{IDENT_PATTERN.pattern})\s+:\s"
"""
Match a constant.
"""
_libmodsec = rf" >>>>>>> \w+ (?P<libmodsec>{IDENT_PATTERN.pattern})"
"""
Match a library, module, or section.
"""

PRINT_ALL_IDENT_PATTERN = regex_from_options(
    [_inductive,
     _mutual_inductive,
     _constant,
     _libmodsec],
    True,
    False,
    compile=True)

OBLIGATION_ID_PATTERN = re.compile(
    rf"(?P<proof_id>{IDENT_PATTERN.pattern})_obligation_\d+")

SUBPROOF_ID_PATTERN = re.compile(
    rf"(?P<proof_id>{IDENT_PATTERN.pattern})_subproof\d*$")

ABORT_COMMAND_PATTERN = re.compile("VernacAbort(?:All)?")
