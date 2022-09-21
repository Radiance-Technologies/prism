"""
Potentially useful regular expressions for parsing SerAPI input/output.

Adapted from
https://github.com/princeton-vl/CoqGym/blob/master/re_patterns.py
"""

import re

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
NEW_IDENT_PATTERN = re.compile(
    rf"{_new_ident_prefixes}(?P<idents>(?:\w+,\s+)*\s*\w+\s+){_new_ident_canaries}"
)
