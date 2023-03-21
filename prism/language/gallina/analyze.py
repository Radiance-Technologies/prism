"""
Provides methods for extracting Gallina terms from parsed s-expressions.

Adapted from `roosterize.parser.SexpAnalyzer`
at https://github.com/EngineeringSoftware/roosterize/.
"""

import enum
import functools
import logging
import re
from dataclasses import asdict, dataclass
from typing import Any, Callable, List, Optional, Set, Union

from prism.language.gallina.util import ParserUtils
from prism.language.sexp import (
    IllegalSexpOperationException,
    SexpNode,
    SexpParser,
)
from prism.language.sexp.list import SexpList
from prism.language.sexp.string import SexpString
from prism.language.token import TokenConsts
from prism.util.opam import Version
from prism.util.radpytools.dataclasses import default_field
from prism.util.re import regex_from_options

from .exception import SexpAnalyzingException

_vernac_change_version = Version.parse("8.10.2")
"""
The last Coq version before the `vernac_control` type changed.

See https://github.com/coq/coq/blob/master/vernac/vernacexpr.ml.
"""


class ControlFlag(enum.Enum):
    """
    Control flags that may be applied to a vernacular command.

    See https://coq.inria.fr/refman/proof-engine/vernacular-commands.html#quitting-and-debugging
    for more information.
    """  # noqa: W505, B950

    Time = enum.auto()
    """
    Executes a sentence and displays the time needed to execute it.
    """
    Redirect = enum.auto()
    """
    Executes sentence, redirecting its output to an indicated file.

    The name of the file is stored in the ``filename`` attribute.
    """
    Timeout = enum.auto()
    """
    Raise an error if the sentence does not finish in a given limit.

    The limit is stored in the ``limit`` attribute.
    """
    Fail = enum.auto()
    """
    Expects the sentence to fail and raise an error if it does not.

    The proof state is not altered.
    """
    Succeed = enum.auto()
    """
    Expects the sentence to succeed and raises an error if it does not.

    The proof state is not altered.
    """

    @property
    def is_batch_mode(self) -> bool:
        """
        Return whether the ``-time`` command-line flag was set.
        """
        if self == ControlFlag.Time:
            try:
                return self._is_batch_mode
            except AttributeError:
                pass
        return super().__getattribute__('is_batch_mode')

    @is_batch_mode.setter
    def is_batch_mode(self, value: bool) -> None:
        """
        Set whether the ``-time`` command-line flag is considered set.
        """
        if self == ControlFlag.Time:
            if not isinstance(value, bool):
                value = value == "true" or value == "True"
            self._is_batch_mode = value
        else:
            raise AttributeError("can't set attribute: is_batch_mode")

    @property
    def filename(self) -> str:
        """
        Get the filename to which a sentence's output is redirected.
        """
        if self == ControlFlag.Redirect:
            try:
                return self._filename
            except AttributeError:
                pass
        return super().__getattribute__('filename')

    @filename.setter
    def filename(self, value: str) -> None:
        """
        Set the output file for a `Redirect` control flag.
        """
        if self == ControlFlag.Redirect:
            self._filename = str(value)
        else:
            raise AttributeError("can't set attribute: filename")

    @property
    def limit(self) -> int:
        """
        Get the time limit for a timed command.
        """
        if self == ControlFlag.Timeout:
            try:
                return self._limit
            except AttributeError:
                pass
        return super().__getattribute__('limit')

    @limit.setter
    def limit(self, value: int) -> None:
        """
        Set the time limit for a `Timeout` control flag.
        """
        if self == ControlFlag.Timeout:
            self._limit = int(value)
        else:
            raise AttributeError("can't set attribute: filename")

    @classmethod
    def _missing_(cls, value: Any) -> 'ControlFlag':
        result = None
        if isinstance(value, str):
            if value == "ControlTime" or value == "VernacTime":
                result = ControlFlag.Time
            elif value == "ControlRedirect" or value == "VernacRedirect":
                result = ControlFlag.Redirect
            elif value == "ControlTimeout" or value == "VernacTimeout":
                result = ControlFlag.Timeout
            elif value == "ControlFail" or value == "VernacFail":
                result = ControlFlag.Fail
            elif value == "ControlSucceed":
                result = ControlFlag.Succeed
        if result is None:
            result = super()._missing_(value)
        return result


class SexpInfo:
    """
    Defines various structs that may be results of SexpAnalyzer methods.

    Note that many of the methods in this class have not been updated to
    be compatible with versions of Coq newer than 8.10.2.
    """

    @dataclass
    class Vernac:
        """
        A vernacular command.
        """

        vernac_type: str = ""
        extend_type: Optional[str] = None
        control_flags: List[ControlFlag] = default_field(list())
        """
        The control flags applied to the command.
        """
        attributes: List[str] = default_field(list())
        """
        The attributes applied to the command.

        The attributes are strings produced from an in-order walk of
        the `vernac_flags` tree defined in
        https://github.com/coq/coq/blob/master/vernac/attributes.mli.
        """
        vernac_sexp: Optional[SexpNode] = None
        loc: Optional["SexpInfo.Loc"] = None

    class VernacConsts:
        """
        Namsepace for vernacular grammar term constructors.
        """

        type_abort = "VernacAbort"
        type_add_option = "VernacAddOption"
        type_arguments = "VernacArguments"
        type_assumption = "VernacAssumption"
        type_begin_section = "VernacBeginSection"
        type_bullet = "VernacBullet"
        type_bind_scope = "VernacBindScope"
        type_canonical = "VernacCanonical"
        type_chdir = "VernacChdir"
        type_check_may_eval = "VernacCheckMayEval"
        type_coercion = "VernacCoercion"
        type_combined_scheme = "VernacCombinedScheme"
        type_context = "VernacContext"
        type_declare_module_type = "VernacDeclareModuleType"
        type_define_module = "VernacDefineModule"
        type_definition = "VernacDefinition"
        type_delimiters = "VernacDelimiters"
        type_end_proof = "VernacEndProof"
        type_end_segment = "VernacEndSegment"
        type_end_subproof = "VernacEndSubproof"
        type_exact_proof = "VernacExactProof"
        type_existing_instance = "VernacExistingInstance"
        type_extend = "VernacExtend"
        type_fail = "VernacFail"
        type_fixpoint = "VernacFixpoint"
        type_hints = "VernacHints"
        type_identify_coercion = "VernacIdentityCoercion"
        type_import = "VernacImport"
        type_include = "VernacInclude"
        type_inductive = "VernacInductive"
        type_infix = "VernacInfix"
        type_instance = "VernacInstance"
        type_notation = "VernacNotation"
        type_open_close_scope = "VernacOpenCloseScope"
        type_print = "VernacPrint"
        type_proof = "VernacProof"
        type_remove_hints = "VernacRemoveHints"
        type_require = "VernacRequire"
        type_reserve = "VernacReserve"
        type_scheme = "VernacScheme"
        type_set_opacity = "VernacSetOpacity"
        type_set_option = "VernacSetOption"
        type_start_theorem_proof = "VernacStartTheoremProof"
        type_subproof = "VernacSubproof"
        type_syntactic_definition = "VernacSyntacticDefinition"
        type_syntax_extension = "VernacSyntaxExtension"

        extend_type_obligations = "Obligations"

    @dataclass(frozen=True)
    class Loc:
        """
        A location within a file.
        """

        filename: str
        """
        The name (path) of the file containing this located object.
        """
        lineno: int
        """
        The line number of the first line of this located object.
        """
        bol_pos: int
        """
        The unencoded character count of the beginning position of the
        first line of this located object.
        """
        lineno_last: int
        """
        The line number of the last line of this located object.
        """
        bol_pos_last: int
        """
        The unencoded character count of the beginning position of the
        last line of this located object.
        """
        beg_charno: int
        """
        The beginning character offset from the start of the file.
        """
        end_charno: int
        """
        The ending character offset from the start of the file.
        """

        def __contains__(self, other: object) -> bool:
            """
            Return whether this location contains another.

            In other words, is the `other` location a point or
            subinterval of this location?
            """
            if isinstance(other, type(self)):
                return (
                    self.end_charno >= other.end_charno
                    and self.beg_charno <= other.beg_charno)
            elif isinstance(other, (int, float)):
                return self.beg_charno <= other and self.end_charno >= other
            else:
                raise TypeError(
                    "Loc.__contains__ supports only Loc, int, or float, "
                    f", but you passed {type(other)}")

        def __lt__(self, other: Union['SexpInfo.Loc', int, float]) -> bool:
            """
            Return whether this location is less than another.

            The last possible character within the location is used for
            the comparison.
            """
            if isinstance(other, type(self)):
                return self.end_charno <= other.beg_charno
            elif isinstance(other, (int, float)):
                return self.end_charno <= other
            else:
                return NotImplemented

        def __gt__(self, other: Union['SexpInfo.Loc', int, float]) -> bool:
            """
            Return whether this location is greater than another.

            The last possible character within the location is used for
            the comparison.
            """
            if isinstance(other, type(self)):
                return self.beg_charno >= other.end_charno
            elif isinstance(other, (int, float)):
                return self.beg_charno >= other
            else:
                return NotImplemented

        def __or__(
            self,
            other: 'SexpInfo.Loc',
        ) -> 'SexpInfo.Loc':
            """
            Generate a location containing union of two locs.

            Parameters
            ----------
            other: SexpInfo.Loc
                Another location from same file as instance Loc,
                that will be used to generate a new `SexpInfo.Loc`
                that is union of instance Loc and `other`.

            Returns
            -------
            SexpInfo.Loc
                A `Loc` object that spans both this instance
                and the other instance.
            """
            if self.filename != other.filename:
                raise ValueError(
                    "Cannot combine locations from different files.")
            if self.beg_charno <= other.beg_charno:
                kwargs = asdict(self)
                if self.end_charno < other.end_charno:
                    kwargs['lineno_last'] = other.lineno_last
                    kwargs['bol_pos_last'] = other.bol_pos_last
                    kwargs['end_charno'] = other.end_charno
                loc = SexpInfo.Loc(**kwargs)
            elif self.end_charno == other.end_charno:
                kwargs = asdict(other)
                loc = SexpInfo.Loc(**kwargs)
            else:
                loc = other | self
            return loc

        def contains_charno_range(
                self,
                beg_charno: int,
                end_charno: int) -> bool:
            """
            Return whether the given locations form a subinterval.

            Parameters
            ----------
            beg_charno : int
                The location from the start of the document of the first
                character in the hypothetical subinterval.
            end_charno : int
                The location from the start of the document of the last
                character in the hypothetical subinterval.

            Returns
            -------
            bool
                Whether the indicated range of characters are contained
                within the span of this location.
            """
            if self.beg_charno <= beg_charno and self.end_charno >= end_charno:
                return True
            else:
                return False

        def contains_lineno(self, lineno: int) -> bool:
            """
            Return whether a given line number is in this location.

            Parameters
            ----------
            lineno : int
                A line number.

            Returns
            -------
            bool
                Whether the given line number is in the range of lines
                spanned by this location.
            """
            line_range = range(self.lineno, self.lineno_last + 1)
            return lineno in line_range

        def offset_byte_to_char(
                self,
                unicode_offsets: List[int]) -> 'SexpInfo.Loc':
            """
            Offset byte-relative character indices to unicode indices..

            Parameters
            ----------
            unicode_offsets : List[int]
                Offsets of unicode (non-ASCII) characters from the start
                of the file.

            Returns
            -------
            SexpInfo.Loc
                The offset location.
            """
            kwargs = asdict(self)
            kwargs['beg_charno'] = ParserUtils.coq_charno_to_actual_charno(
                kwargs['beg_charno'],
                unicode_offsets)
            kwargs['end_charno'] = ParserUtils.coq_charno_to_actual_charno(
                kwargs['end_charno'],
                unicode_offsets)
            return SexpInfo.Loc(**kwargs)

        def offset_char_to_byte(
                self,
                unicode_offsets: List[int]) -> 'SexpInfo.Loc':
            """
            Offset byte-relative character indices to unicode indices..

            Parameters
            ----------
            unicode_offsets : List[int]
                Offsets of unicode (non-ASCII) characters from the start
                of the file.

            Returns
            -------
            SexpInfo.Loc
                The offset location.
            """
            kwargs = asdict(self)
            kwargs['beg_charno'] = ParserUtils.actual_charno_to_coq_charno_bp(
                kwargs['beg_charno'],
                unicode_offsets)
            kwargs['end_charno'] = ParserUtils.actual_charno_to_coq_charno_ep(
                kwargs['end_charno'],
                unicode_offsets)
            return SexpInfo.Loc(**kwargs)

        def rename(self, new_name: str) -> 'SexpInfo.Loc':
            """
            Change the filename of this location.

            Parameters
            ----------
            new_name : str
                The new filename for the location.

            Returns
            -------
            SexpInfo.Loc
                The location with the new filename.
            """
            return SexpInfo.Loc(
                new_name,
                self.lineno,
                self.bol_pos,
                self.lineno_last,
                self.bol_pos_last,
                self.beg_charno,
                self.end_charno)

        def shift(self, offset: int) -> 'SexpInfo.Loc':
            """
            Shift the character positions of this location.

            Parameters
            ----------
            offset : int
                The amount, positive or negative, by which this location
                should be shifted.

            Returns
            -------
            SexpInfo.Loc
                The shifted location.
            """
            return SexpInfo.Loc(
                self.filename,
                self.lineno,
                self.bol_pos,
                self.lineno_last,
                self.bol_pos_last,
                self.beg_charno + offset,
                self.end_charno + offset)

        def to_sexp(self) -> SexpList:
            """
            Convert this location back into an s-expression.

            Returns
            -------
            SexpList
                The corresponding ``loc``s-expression.
            """
            filename = SexpList(
                [
                    SexpString('fname'),
                    SexpList([SexpString("InFile"),
                              SexpString(self.filename)])
                ])
            lineno = SexpList(
                [SexpString("line_nb"),
                 SexpString(str(self.lineno))])
            bol_pos = SexpList(
                [SexpString("bol_pos"),
                 SexpString(str(self.bol_pos))])
            lineno_last = SexpList(
                [SexpString("line_nb_last"),
                 SexpString(str(self.lineno_last))])
            bol_pos_last = SexpList(
                [
                    SexpString("bol_pos_last"),
                    SexpString(str(self.bol_pos_last))
                ])
            bp = SexpList([SexpString("bp"), SexpString(str(self.beg_charno))])
            ep = SexpList([SexpString("ep"), SexpString(str(self.end_charno))])
            return SexpList(
                [
                    SexpString("loc"),
                    SexpList(
                        [
                            SexpList(
                                [
                                    filename,
                                    lineno,
                                    bol_pos,
                                    lineno_last,
                                    bol_pos_last,
                                    bp,
                                    ep
                                ])
                        ])
                ])

        def union(self, *others: 'SexpInfo.Loc') -> 'SexpInfo.Loc':
            """
            Get the union of this location and another.

            The union of two locations is defined as the minimal-span
            location that contains each of the two locations.

            Parameters
            ----------
            other: tuple of SexpInfo.Loc
                Other locations from the same file as this location.

            Returns
            -------
            SexpInfo.Loc
                A `Loc` object that spans both this instance and the
                other instances.

            Raises
            ------
            ValueError
                If any other location does not point to the same file as
                `self`.
            """
            return functools.reduce(lambda x, y: x | y, others, self)

        @classmethod
        def span(
                cls,
                loc: 'SexpInfo.Loc',
                *others: 'SexpInfo.Loc') -> 'SexpInfo.Loc':
            """
            Get the union of all given locations.

            Parameters
            ----------
            locs: tuple of SexpInfo.Loc
                A set of locations, each presumed to come from the same
                file.

            Raises
            ------
            ValueError
                If any two given locations point to different files.
            """
            # one required positional argument to let Python handle the
            # failure of trying to get the union of an empty list
            return loc.union(*others)

    @dataclass
    class SertokSentence:
        """
        A sequence of lexical tokens obtained via `sertok`.
        """

        tokens: List["SexpInfo.SertokToken"] = default_field([])

    @dataclass
    class SertokToken:
        """
        A lexical token obtained via `sertok`.
        """

        kind: str
        content: str
        loc: "SexpInfo.Loc"

    @dataclass
    class ConstrExprR:
        """
        A Gallina constructor expression term.
        """

        expr_type: str = ""
        expr_sexp: Optional[SexpNode] = None
        claimed_loc: Optional["SexpInfo.Loc"] = None
        loc: Optional["SexpInfo.Loc"] = None

        def __hash__(self) -> int:
            """
            Get the hash of the internal node and location.
            """
            return hash((self.expr_sexp, self.loc))

    class ConstrExprRConsts:
        """
        Namespace for Gallina term constructors.
        """

        type_c_ref = "CRef"
        type_c_fix = "CFix"
        type_c_co_fix = "CCoFix"
        type_c_prod_n = "CProdN"
        type_c_lambda_n = "CLambdaN"
        type_c_let_in = "CLetIn"
        type_c_app_expl = "CAppExpl"
        type_c_app = "CApp"
        type_c_record = "CRecord"
        type_c_cases = "CCases"
        type_c_let_tuple = "CLetTuple"
        type_c_if = "CIf"
        type_c_hole = "CHole"
        type_c_pat_var = "CPatVar"
        type_c_evar = "CEvar"
        type_c_sort = "CSort"
        type_c_cast = "CCast"
        type_c_notation = "CNotation"
        type_c_generalization = "CGeneralization"
        type_c_prim = "CPrim"
        type_c_delimiters = "CDelimiters"

        types = [
            type_c_ref,
            type_c_fix,
            type_c_co_fix,
            type_c_prod_n,
            type_c_lambda_n,
            type_c_let_in,
            type_c_app_expl,
            type_c_app,
            type_c_record,
            type_c_cases,
            type_c_let_tuple,
            type_c_if,
            type_c_hole,
            type_c_pat_var,
            type_c_evar,
            type_c_sort,
            type_c_cast,
            type_c_notation,
            type_c_generalization,
            type_c_prim,
            type_c_delimiters,
        ]

    @dataclass
    class CNotation:
        """
        A custom notation term.
        """

        notation_shape: str = ""
        expr_sexp: Optional[SexpNode] = None
        loc: Optional["SexpInfo.Loc"] = None
        args: Optional[List["SexpInfo.ConstrExprR"]] = None
        notation_symbols: Optional[List[str]] = None

    @dataclass
    class CLocalAssum:
        """
        A local assumption term.
        """

        sexp: Optional[SexpNode] = None
        loc: Optional["SexpInfo.Loc"] = None
        loc_part_1: Optional["SexpInfo.Loc"] = None
        constr_expr_r: Optional["SexpInfo.ConstrExprR"] = None
        is_one_token: Optional[bool] = False


class SexpAnalyzer:
    """
    Namespace providing methods for analyzing parsed s-expressions.

    The methods can be used to retrieve a variety of types of
    information from s-expressions
    """

    logger: logging.Logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    _vt_proof_regex: re.Pattern = re.compile(
        "|".join(
            [
                # VtStartProof
                "VernacProof",
                # VtProofMode
                "VernacProofMode",  # NOTE: not sure if this belongs
                # VtQed
                "VernacAbort",
                "VernacEndProof",
                "VernacEndSubproof",
                "VernacExactProof",
                # VtProofStep
                "VernacBullet",
                "VernacCheckGuard",
                "VernacFocus",
                "VernacShow",
                "VernacSubproof",
                "VernacUnfocus",
                "VernacUnfocused",
                # VtMeta
                "VernacAbortAll",
                "VernacRestart",
                "VernacUndo",
                "VernacUndoTo",
            ]))
    """
    A white-list of Vernacular commands that are part of a proof.

    These explicitly do not include commands that can strictly instigate
    proofs (e.g., Lemma, Theorem, Definition, Fixpoint, etc.).
    Derived from
    https://github.com/coq/coq/blob/master/vernac/vernac_classifier.ml
    as well as documentation at
    https://coq.inria.fr/refman/proofs/writing-proofs/proof-mode.html.
    """
    _vt_proof_extend_regex: re.Pattern = regex_from_options(
        [
            # from Ltac
            "Obligations",
            "OptimizeProof",
            # from Ltac: Questionable
            # "Admit_Obligations",
            # "Solve_Obligation",
            # "Solve_Obligations",
            # "Solve_All_Obligations",
            "Unshelve",
            "VernacSolve",
            "VernacSolveParallel",
            # from Ltac2
            "VernacLtac2",
            # from Mtac2
            "MProofInstr",
            "MProofCommand",
        ],
        False,
        False)
    """
    A white-list of VernacExtend commands that are part of a proof.

    Derived from ``.mlg`` files for plugins shipped with Coq as well as
    the list of plug-ins at
    https://github.com/coq-community/awesome-coq by looking for
    command definitions that classify as ``VtProofStep``.
    """
    _vernac_extend_regex: re.Pattern = re.compile("VernacExtend")

    @classmethod
    def analyze_vernac_flags(cls, sexp: SexpNode) -> List[str]:
        """
        Analyze the attribute flags of a Vernacular command.

        Parameters
        ----------
        sexp : SexpNode
            The s-expression of a `vernac_flags` object as defined in
            https://github.com/coq/coq/blob/master/vernac/attributes.ml.

        Returns
        -------
        List[str]
            The list of attributes or flags defined by the given
            s-expression.

        Raises
        ------
        SexpAnalyzingException
            If the s-expression does not conform to the expected
            structure of a `vernac_flags`.
        """
        attributes = []
        try:
            for vernac_flag in sexp:
                if (len(vernac_flag) == 2 and vernac_flag.head() == "v"
                        and vernac_flag[1].head() == "loc"
                        and vernac_flag[1][1].children):
                    # Coq 8.15 added locations to attributes
                    vernac_flag = vernac_flag[0][1]
                attribute = vernac_flag[0].content
                vernac_flag_value = vernac_flag[1]
                if vernac_flag_value.is_list():
                    # not VernacFlagEmpty
                    vernac_flag_type = vernac_flag_value[0].content
                    if vernac_flag_type == "VernacFlagLeaf":
                        vernac_flag_type = vernac_flag_value[1]
                        if vernac_flag_type.is_list():
                            # Coq version > 8.10.2
                            vernac_flag_type = vernac_flag_type[1]
                        attribute += f"={vernac_flag_type}"
                    elif vernac_flag_type == "VernacFlagList":
                        args = ",".join(
                            cls.analyze_vernac_flags(vernac_flag_value[1]))
                        attribute = f'{attribute} ({args})'
                attributes.append(attribute)
        except IllegalSexpOperationException as e:
            raise SexpAnalyzingException(sexp) from e
        return attributes

    @classmethod
    def _analyze_vernac_expr(cls, sexp: SexpNode) -> SexpInfo.Vernac:
        """
        Analyze an s-expression representing a Vernacular expression.
        """
        if sexp.is_list():
            vernac_expr = sexp[0].content
        else:
            vernac_expr = sexp.content
        return SexpInfo.Vernac(
            vernac_expr,
            sexp[1][0].content if vernac_expr == "VernacExtend" else None)

    @classmethod
    def analyze_vernac(  # noqa: C901
            cls,
            sexp: SexpNode,
            with_flags: bool = True) -> SexpInfo.Vernac:
        """
        Analyze an s-expression representing a Vernacular command.

        Analyzes an s-expression and parses it as a Vernac expression,
        getting the type of the expression and its source code location.

        Parameters
        ----------
        sexp : SexpNode
            A parsed s-expression node representing a Vernacular command
            term.
            The structure should conform to the following format in Coq
            8.10.2 and lower:
            <sexp_vernac> = ( ( v (VernacExpr (...) ( <TYPE>  ... )) )
                                ^----------vernac_sexp-----------^
                            <sexp_loc> )
            In Coq 8.11 and higher, the structure should be
            <sexp_vernac> = ( ( v ((control ...)
                                   (attrs ...)
                                   (expr (VernacExpr (...)
                                         ( <TYPE>  ... )) ))
                                ^----------vernac_sexp-----------^
                            <sexp_loc> )
        with_flags : bool, optional
            Whether to extract control and attribute flags in addition
            to the location and Vernacular type.

        Returns
        -------
        SexpInfo.Vernac
            The extracted Vernacular command.

        Raises
        ------
        SexpAnalyzingException
            If the sexp cannot be parsed that way, i.e., if it is
            malformed or not representative of a Vernacular command.
        """
        try:
            if (len(sexp) == 2 and sexp.head() == "v"
                    and sexp[1].head() == "loc" and sexp[1][1].children):
                v_child = sexp[0]
                loc_child = sexp[1]

                try:
                    loc = cls.analyze_loc(loc_child)
                except SexpAnalyzingException:
                    loc = None

                if v_child[0].content:
                    vernac_control = v_child[1]
                else:
                    vernac_control = v_child
            else:
                vernac_control = sexp
                loc = None
            if vernac_control.head() == "control":
                # Coq version > 8.10.2
                vernac = cls._analyze_vernac_expr(vernac_control[2][1])
                if with_flags:
                    attributes = cls.analyze_vernac_flags(vernac_control[1][1])
                    vernac.attributes = attributes
                    control = vernac_control[0][1]
                    control_flags = []
                    for c in control:
                        try:
                            control_flag = ControlFlag(c.head())
                        except ValueError as e:
                            raise SexpAnalyzingException(control) from e
                        if control_flag == ControlFlag.Redirect:
                            control_flag.filename = c[1].content
                        elif control_flag == ControlFlag.Timeout:
                            control_flag.limit = c[1].content
                        elif control_flag == ControlFlag.Time:
                            control_flag.is_batch_mode = c[1].content
                        control_flags.append(control_flag)
                    vernac.control_flags = control_flags
            elif vernac_control[0].content == "VernacExpr":
                # Coq version <= 8.10.2
                vernac = cls._analyze_vernac_expr(vernac_control[2])
                if with_flags:
                    attributes = cls.analyze_vernac_flags(vernac_control[1])
                    vernac.attributes = attributes
            else:
                # Coq version <= 8.10.2
                if with_flags:
                    try:
                        control_flag = ControlFlag(vernac_control[0].content)
                    except ValueError as e:
                        raise SexpAnalyzingException(sexp) from e
                    else:
                        if control_flag != ControlFlag.Fail:
                            if control_flag == ControlFlag.Redirect:
                                control_flag.filename = vernac_control[
                                    1].content
                            elif control_flag == ControlFlag.Timeout:
                                control_flag.limit = vernac_control[1].content
                            elif control_flag == ControlFlag.Time:
                                control_flag.is_batch_mode = vernac_control[
                                    1].content
                            sub_vernac_control = vernac_control[2]
                        else:
                            sub_vernac_control = vernac_control[1]
                        vernac = cls.analyze_vernac(sub_vernac_control)
                        vernac.control_flags.insert(0, control_flag)
                else:
                    vernac = cls.analyze_vernac(vernac_control[-1])

            vernac.loc = loc
            vernac.vernac_sexp = vernac_control
            return vernac
        except IllegalSexpOperationException:
            raise SexpAnalyzingException(sexp)

    @classmethod
    def analyze_constr_expr_r(
            cls,
            sexp: SexpNode,
            unicode_offsets: Optional[List[int]] = None
    ) -> SexpInfo.ConstrExprR:
        """
        Analyze a ConstrExprR s-expression.

        Analyzes an s-expression and parses it as a ConstrExprR
        expression, getting the type of the expression and its source
        code location.

        Parameters
        ----------
        sexp : SexpNode
            An s-expression representing a Gallina ConstrExprR term.
            The structure should conform to the following format:
            <ConstrExprR> = ( ( v  (  CXxx ... ) ) (  loc ... )
                                ^-expr_sexp-^   ^-expr_loc-^
                            0 00 01 010          1  10
        unicode_offsets : list of int | None, optional
            Offsets of unicode (non-ASCII) characters from the start of
            the file, by default None.

        Returns
        -------
        SexpInfo.ConstrExprR
            The extracted ConstrExprR expression.

        Raises
        ------
        SexpAnalyzingException
            If the s-expression does not conform to the expected
            structure of a ConstrExprR.
        """
        if sexp[0][0].content == "v" and sexp[0][1][
                0].content in SexpInfo.ConstrExprRConsts.types:
            loc_child = sexp[1]
            claimed_loc: SexpInfo.Loc = cls.analyze_loc(
                loc_child,
                unicode_offsets)
            expr_type = sexp[0][1][0].content
            expr_sexp = sexp

            if expr_type == SexpInfo.ConstrExprRConsts.type_c_cast:
                # Find all nested loc
                locs: List[SexpInfo.Loc] = list()

                def find_all_loc(sexp_part: SexpNode) -> SexpNode.RecurAction:
                    nonlocal locs
                    try:
                        locs.append(cls.analyze_loc(sexp_part, unicode_offsets))
                        return SexpNode.RecurAction.ContinueRecursion
                    except (IllegalSexpOperationException,
                            SexpAnalyzingException):
                        return SexpNode.RecurAction.ContinueRecursion

                sexp.apply_recur(find_all_loc)

                loc = SexpInfo.Loc(
                    filename=claimed_loc.filename,
                    lineno=claimed_loc.lineno,
                    bol_pos=claimed_loc.bol_pos,
                    lineno_last=claimed_loc.lineno_last,
                    bol_pos_last=claimed_loc.bol_pos_last,
                    beg_charno=min([loc.beg_charno for loc in locs]),
                    end_charno=max([loc.end_charno for loc in locs]),
                )
            else:
                loc = claimed_loc

            return SexpInfo.ConstrExprR(
                expr_type=expr_type,
                expr_sexp=expr_sexp,
                claimed_loc=claimed_loc,
                loc=loc)
        else:
            raise SexpAnalyzingException(sexp)

    @classmethod
    def analyze_c_local_assume(
            cls,
            sexp: SexpNode,
            unicode_offsets: Optional[List[int]] = None
    ) -> SexpInfo.CLocalAssum:
        """
        Analyzes a CLocalAssum sexp.

        Analyzes an s-expression and parses it as a CLocalAssum
        expression, getting the type of the expression and its source
        code location.

        Parameters
        ----------
        sexp : SexpNode
            An s-expression representing a Gallina CLocalAssum term.
            The structure should conform to the following format:
            <CLocalAssume> = ( CLocalAssum ((   (v ...) (loc ...) )) ...
                                                        ^-<loc_part_1>
                               0            10 100     101           1
                               ( (v (CXxx ...) ... ) (loc ...) ) )
                               ^---<ConstrExprR>---------------^
                               2
        unicode_offsets : list of int | None, optional
            Offsets of unicode (non-ASCII) characters from the start of
            the file, by default None.

        Returns
        -------
        SexpInfo.CLocalAssum
            The extracted CLocalAssum expression.

        Raises
        ------
        SexpAnalyzingException
            If the s-expression does not conform to the expected
            structure of a CLocalAssum.
        """
        if sexp[0].content == "CLocalAssum" and sexp[1][0][0][0].content == "v":
            loc_part_1 = cls.analyze_loc(sexp[1][0][1], unicode_offsets)
            constr_expr_r: SexpInfo.ConstrExprR = cls.analyze_constr_expr_r(
                sexp[2],
                unicode_offsets)
            is_one_token = (loc_part_1 == constr_expr_r.loc)
            loc = SexpInfo.Loc(
                filename=loc_part_1.filename,
                lineno=loc_part_1.lineno,
                bol_pos=loc_part_1.bol_pos,
                lineno_last=loc_part_1.lineno_last,
                bol_pos_last=loc_part_1.bol_pos_last,
                beg_charno=min(
                    [loc_part_1.beg_charno,
                     constr_expr_r.loc.beg_charno]),
                end_charno=max(
                    [loc_part_1.end_charno,
                     constr_expr_r.loc.end_charno]),
            )

            c_local_assume = SexpInfo.CLocalAssum(
                sexp=sexp,
                loc=loc,
                loc_part_1=loc_part_1,
                constr_expr_r=constr_expr_r,
                is_one_token=is_one_token)
            return c_local_assume
        else:
            raise SexpAnalyzingException(sexp)

    @classmethod
    def find_gallina_parts(
        cls,
        sexp: SexpNode,
        unicode_offsets: Optional[List[int]] = None
    ) -> List[Union[SexpInfo.ConstrExprR,
                    SexpInfo.CLocalAssum]]:
        """
        Extract all Gallina sub-terms from a given parsed s-expression.

        Namely, find all occurrences of ConstExprR or CLocalAssum.

        Parameters
        ----------
        sexp : SexpNode
            An s-expression representing a Vernacular or Ltac command.
        unicode_offsets : list of int | None, optional
            Offsets of unicode (non-ASCII) characters from the start of
            the file, by default None.

        Returns
        -------
        list of Union[SexpInfo.CLocalAssum, SexpInfo.CLocalAssum]
            The extracted Gallina expressions.

        Raises
        ------
        SexpAnalyzingException
            If the s-expression is malformed and cannot be analyzed.
        """
        try:
            cs_parts: List[Union[SexpInfo.ConstrExprR,
                                 SexpInfo.CLocalAssum]] = list()

            def find_cs_parts(sexp_part: SexpNode) -> SexpNode.RecurAction:
                nonlocal cs_parts
                try:
                    if sexp_part[0][0].content == "v" and sexp_part[0][1][
                            0].content in SexpInfo.ConstrExprRConsts.types:
                        # ( ( v  (  CXxx ... ) )  ....
                        cs_parts.append(
                            cls.analyze_constr_expr_r(
                                sexp_part,
                                unicode_offsets))
                        return SexpNode.RecurAction.StopRecursion
                    elif sexp_part[0].content == "CLocalAssum" and sexp_part[1][
                            0][0][0].content == "v":
                        # ( CLocalAssum (( (v ...) ....
                        cs_parts.append(
                            cls.analyze_c_local_assume(
                                sexp_part,
                                unicode_offsets))
                        return SexpNode.RecurAction.StopRecursion
                    else:
                        return SexpNode.RecurAction.ContinueRecursion
                except (IllegalSexpOperationException, SexpAnalyzingException):
                    return SexpNode.RecurAction.ContinueRecursion

            sexp.apply_recur(find_cs_parts)
            cs_parts.sort(key=lambda e: e.loc)

            return cs_parts
        except IllegalSexpOperationException:
            raise SexpAnalyzingException(sexp)

    RE_NOTATION_SHAPE = re.compile(r"(^|(?<= ))_(?=$| )")
    RE_NOTATION_REC = re.compile(
        r"(^|(?<= ))_ (?P<rec>(\S* )?)\.\. (?P=rec)_(?=$| )")

    @classmethod
    def find_c_notations(cls, sexp: SexpNode) -> List[SexpInfo.CNotation]:
        """
        Extract CNotations from a Gallina-only parsed s-expression.

        Parameters
        ----------
        sexp : SexpNode
            A parsed s-expression expected to contain only Gallina
            terms.

        Returns
        -------
        list of List[SexpInfo.CNotation]
            A list of all discovered CNotations.

        Raises
        ------
        SexpAnalyzingException
            If the s-expression is malformed or not a Gallina-only
            s-expression.
        """
        try:
            c_notations: List[SexpInfo.CNotation] = list()
            seen_locs: Set[SexpInfo.Loc] = set()

            def find_c_notation_parts(
                    sexp_part: SexpNode) -> SexpNode.RecurAction:
                nonlocal c_notations
                try:
                    # ( ( v  ( CNotation ... ) ) (  loc ... )
                    #        ^---expr_sexp---^   ^-expr_loc-^
                    #   0 00 01 010              1  10
                    if sexp_part[0][0].content == "v" and sexp_part[0][1][
                            0].content == SexpInfo.ConstrExprRConsts.type_c_notation:
                        loc_child = sexp_part[1]
                        loc = cls.analyze_loc(loc_child)

                        # Only parse unseen CNotations
                        if loc in seen_locs:
                            return SexpNode.RecurAction.StopRecursion
                        # end if
                        seen_locs.add(loc)

                        expr_sexp = sexp_part

                        # ... (  CNotation (   XLevel Shape ) (
                        #     01 010       011 0110   0111
                        #   ( A1 A2 .. ) ( .. ) ( .. ) ( .. ) )
                        # 012 0120         0121   0122   0123
                        notation_shape = expr_sexp[0][1][1][1].content
                        notation_symbols = list()
                        notation_recur_idx = -1
                        notation_recur_symbol = None
                        if notation_shape[0] == '"' and notation_shape[
                                -1] == '"':
                            # Notation with arguments
                            notation_shape = notation_shape[
                                1 :
                                -1]  # [1:-1] is to remove preceding and trailing "
                            rec_match = cls.RE_NOTATION_REC.search(
                                notation_shape)
                            if rec_match is None:
                                # Notation without recursive pattern
                                # [::2] is to remove the split points
                                # and only keep symbols
                                notation_symbols.extend(
                                    cls.RE_NOTATION_SHAPE.split(notation_shape)
                                    [:: 2])
                            else:
                                # Notation with recursive pattern: ".."
                                # and the separators are removed
                                notation_recur_symbol = rec_match.group("rec")
                                # [::2] is to remove the split points
                                # and only keep symbols
                                notation_symbols.extend(
                                    cls.RE_NOTATION_SHAPE.split(
                                        notation_shape[: rec_match.start()])
                                    [:: 2])
                                notation_recur_idx = len(notation_symbols)
                                # [::2] is to remove the split points
                                # and only keep symbols
                                notation_symbols.extend(
                                    cls.RE_NOTATION_SHAPE.split(
                                        notation_shape[rec_match.end():])[:: 2])
                            # end if
                            num_args = len(notation_symbols) - 1
                        else:
                            # Notation without argument
                            notation_symbols = [notation_shape]
                            num_args = 0

                        args_sexps: List[SexpNode] = list()
                        for i in range(4):
                            args_sexps.extend(
                                expr_sexp[0][1][2][i].get_children())
                        # end for
                        if notation_recur_idx == -1:
                            # No recursive pattern: try to match num_
                            # args with len(args_sexps)
                            if num_args != len(args_sexps):
                                cls.logger.warning(
                                    f"Notation: num of args doesnot match: {num_args} "
                                    f"(in {notation_symbols}) != {len(args_sexps)} "
                                    f"(in sexp {sexp_part.pretty_format()})")
                                raise SexpAnalyzingException(
                                    sexp,
                                    f"num of args doesnot match: {num_args} "
                                    f"(in {notation_symbols}) != {len(args_sexps)} "
                                    "(in sexp)")
                        else:
                            # Recursive pattern: use len(arg_sexps) to
                            # imply num_args
                            for _ in range(len(args_sexps) - num_args):
                                notation_symbols.insert(
                                    notation_recur_idx,
                                    notation_recur_symbol)
                            num_args = len(args_sexps)

                        args: List[SexpInfo.ConstrExprR] = [
                            cls.analyze_constr_expr_r(arg_sexp)
                            for arg_sexp in args_sexps
                        ]
                        args.sort(key=lambda a: a.loc)

                        c_notations.append(
                            SexpInfo.CNotation(
                                expr_sexp=expr_sexp,
                                loc=loc,
                                notation_shape=notation_shape,
                                args=args,
                                notation_symbols=notation_symbols))
                        return SexpNode.RecurAction.StopRecursion
                    else:
                        return SexpNode.RecurAction.ContinueRecursion
                except (IllegalSexpOperationException, SexpAnalyzingException):
                    return SexpNode.RecurAction.ContinueRecursion

            sexp.apply_recur(find_c_notation_parts)

            return c_notations
        except IllegalSexpOperationException:
            raise SexpAnalyzingException(sexp)

    @classmethod
    def analyze_loc(
            cls,
            sexp: SexpNode,
            unicode_offsets: Optional[List[int]] = None) -> SexpInfo.Loc:
        """
        Get source code location metadata from a ``loc`` s-expression.

        Analyzes an s-expression and parses it as a ``loc`` expression
        into an object abstracting a source code location.

        Parameters
        ----------
        sexp : SexpNode
            An s-expression representing a ``loc`` term.
            The structure should conform to the following format:
            <sexp_loc> = ( loc (( (fname(InFile <FILENAME>))
                                  (line_nb X)
                                  (bol_pos X)
                                  (line_nb_last <LINENO>)
                                  (bol_pos_last X)
                                  (bp <BEG_CHARNO>)
                                  (ep <END_CHARNO>) )) )
        unicode_offsets : list of int | None, optional
            Offsets of unicode (non-ASCII) characters from the start of
            the file, by default None.

        Returns
        -------
        SexpInfo.Loc
            The source code location metadata.

        Raises
        ------
        SexpAnalyzingException
            If the s-expression does not conform to the expected
            structure.
        """

        def check_and_parse(
                child: SexpNode,
                expected: str,
                parser: Callable[[str],
                                 Any] = int) -> str:
            if child[0].content != expected:
                raise SexpAnalyzingException(sexp)
            child = child[1]
            return parser(str(child))

        try:
            if len(sexp) != 2:
                raise SexpAnalyzingException(sexp)
            # end if

            if sexp[0].content != "loc":
                raise SexpAnalyzingException(sexp)
            # end if

            data_child = sexp[1][0]
            if len(data_child) != 7:
                raise SexpAnalyzingException(sexp)
            # end if

            kwargs = {
                "filename":
                    check_and_parse(
                        data_child[0],
                        'fname',
                        parser=lambda f: f
                        if not f.startswith("(InFile") else f[8 :-1]),
                "lineno":
                    check_and_parse(data_child[1],
                                    "line_nb"),
                "bol_pos":
                    check_and_parse(data_child[2],
                                    "bol_pos"),
                "lineno_last":
                    check_and_parse(data_child[3],
                                    "line_nb_last"),
                "bol_pos_last":
                    check_and_parse(data_child[4],
                                    "bol_pos_last"),
                "beg_charno":
                    check_and_parse(data_child[5],
                                    "bp"),
                "end_charno":
                    check_and_parse(data_child[6],
                                    "ep")
            }

            if unicode_offsets is not None:
                kwargs['beg_charno'] = ParserUtils.coq_charno_to_actual_charno(
                    kwargs['beg_charno'],
                    unicode_offsets)
                kwargs['end_charno'] = ParserUtils.coq_charno_to_actual_charno(
                    kwargs['end_charno'],
                    unicode_offsets)

            return SexpInfo.Loc(**kwargs)
        except IllegalSexpOperationException as e:
            raise SexpAnalyzingException(sexp) from e

    @classmethod
    def analyze_sertok_sentences(
        cls,
        tok_sexp_list: List[SexpNode],
        unicode_offsets: Optional[List[int]] = None
    ) -> List[SexpInfo.SertokSentence]:
        """
        Convert `sertok` output to object-oriented abstractions.

        Each token gets converts to an object as well as each sentence
        considered as a sequence of tokens.

        Parameters
        ----------
        tok_sexp_list : list of SexpNode
            A sequence of `SexpNode`s yielded from parsing `sertok`'s
            output with each item corresponding to a sentence.
        unicode_offsets : list of int | None, optional
            Offsets of unicode (non-ASCII) characters from the start of
            the file, by default None.

        Returns
        -------
        list of SexpInfo.SertokSentence
            The extracted sentences.

        Raises
        ------
        SexpAnalyzingException
            If the parsed s-expression is malformed or does not conform
            to the structure expected from `sertok` output.
        """
        sentences: List[SexpInfo.SertokSentence] = []

        for sertok_sentence_sexp in tok_sexp_list:
            # ( Sentence  ( tok ... ) )
            #   0         1
            try:
                if sertok_sentence_sexp[0].content != "Sentence":
                    raise SexpAnalyzingException(
                        sertok_sentence_sexp,
                        "Not a valid SertokSentence sexp")

                sentence = SexpInfo.SertokSentence()
                for sertok_token_sexp in sertok_sentence_sexp[1].get_children():
                    sentence.tokens.append(
                        cls.analyze_sertok_token(
                            sertok_token_sexp,
                            unicode_offsets))
                # end for

                sentences.append(sentence)
            except IllegalSexpOperationException:
                raise SexpAnalyzingException(sertok_sentence_sexp)
            # end try
        # end for

        return sentences

    SERTOK_TOKEN_KIND_MAPPING = {
        "BULLET": TokenConsts.KIND_SYMBOL,
        "IDENT": TokenConsts.KIND_ID,
        "KEYWORD": TokenConsts.KIND_KEYWORD,
        "LEFTQMARK": TokenConsts.KIND_SYMBOL,
        "NUMERAL": TokenConsts.KIND_NUMBER,
        "STRING": TokenConsts.KIND_STR,
    }

    @classmethod
    def analyze_sertok_numeral(cls, sexp: SexpNode) -> str:
        """
        Extract a number from a `sertok`-derived parsed s-expression.

        Parameters
        ----------
        sexp : SexpNode
            An s-expression presumed to correspond to a numeral lexical
            token.

        Returns
        -------
        str
            The extracted number as it was parsed.

        Raises
        ------
        SexpAnalyzingException
            If the s-expression does not match a known numeral type (one
            of int, frac, or exp).
        """
        # ( ( int ? ) (frac ? ) (exp ? ) )
        #   0         1         2
        if len(sexp[0][1].content) > 0:
            content = sexp[0][1].content
        elif len(sexp[1][1].content) > 0:
            content = sexp[1][1].content
        elif len(sexp[2][1].content) > 0:
            content = sexp[2][1].content
        else:
            raise SexpAnalyzingException(sexp, message="Unknown numeral")
        return content

    @classmethod
    def analyze_sertok_token(
            cls,
            sexp: SexpNode,
            unicode_offsets: Optional[List[int]] = None
    ) -> SexpInfo.SertokToken:
        """
        Convert a parsed `sertok` token s-expression into an object.

        Parameters
        ----------
        sexp : SexpNode
            An s-expression yielded from parsing `sertok`'s output and
            corresponding to a lexical token.
        unicode_offsets : list of int | None, optional
            Offsets of unicode (non-ASCII) characters from the start of
            the file, by default None.

        Returns
        -------
        SexpInfo.SertokToken
            The extracted token.

        Raises
        ------
        SexpAnalyzingException
            If the parsed s-expression is malformed or does not conform
            to the structure expected from `sertok` output.
        """
        # ( ( v  (  <KIND> <CONTENT> )) ( loc ... ) ) )
        #   0 00 01 010    011          1
        try:
            if sexp[0][0].content != "v":
                raise SexpAnalyzingException(sexp)

            # Kind and content
            if sexp[0][1].is_list():
                kind = sexp[0][1][0].content
                if kind == "NUMERAL":
                    content = cls.analyze_sertok_numeral(sexp[0][1][1])
                else:
                    content = sexp[0][1][1].content
            else:
                kind = sexp[0][1].content
                if kind == "LEFTQMARK":
                    content = "?"
                else:
                    raise SexpAnalyzingException(
                        sexp,
                        message="Unknown special token")

            # Normalize token kind
            if kind in cls.SERTOK_TOKEN_KIND_MAPPING:
                kind = cls.SERTOK_TOKEN_KIND_MAPPING[kind]

            # Loc
            loc = cls.analyze_loc(sexp[1], unicode_offsets)

            # It can never be empty string; if it is, it is '""'
            if len(content) == 0:
                content = '""'

            # Escape the " in coq style
            if (content[0] == '"' and content[-1] == '"'
                    and '"' in content[1 :-1]):
                content = '"' + content[1 :-1].replace('"', '""') + '"'

            # Adjust content to remove quotes, if necessary
            if (content[0] == '"' and content[-1] == '"'
                    and len(content) != loc.end_charno - loc.beg_charno):
                content = content[1 :-1]

            # Adjust content to add quotes, if necessary
            if (kind == TokenConsts.KIND_STR
                    and len(content) == loc.end_charno - loc.beg_charno - 2):
                content = '"' + content + '"'

            # Fix for charno mismatch
            # TODO: this should be eventually fixed in Coq
            if (loc.end_charno - loc.beg_charno < len(content)):
                loc = SexpInfo.Loc(
                    filename=loc.filename,
                    lineno=loc.lineno,
                    bol_pos=loc.bol_pos,
                    lineno_last=loc.lineno_last,
                    bol_pos_last=loc.bol_pos_last,
                    beg_charno=loc.beg_charno,
                    end_charno=len(content) + loc.beg_charno)

            return SexpInfo.SertokToken(kind, content, loc)
        except IllegalSexpOperationException:
            raise SexpAnalyzingException(sexp)

    @classmethod
    def get_locs(
            cls,
            sexp: SexpNode,
            unicode_offsets: Optional[List[int]] = None) -> List[SexpInfo.Loc]:
        """
        Get all of the locations in the given s-expression.

        Parameters
        ----------
        sexp : SexpNode
            An s-expression, presumed to be correspond to a valid AST.
        unicode_offsets : list of int | None, optional
            Offsets of unicode (non-ASCII) characters from the start of
            the file, by default None.

        Returns
        -------
        List[SexpInfo.Loc]
            A list of all of the locations encountered in the given
            s-expression.

        Raises
        ------
        SexpAnalyzingException
            If a malformed location is encountered.
        """
        locs = []
        if sexp.is_list():
            if sexp.head() == "loc" and sexp[1].children:
                locs.append(cls.analyze_loc(sexp, unicode_offsets))
            else:
                locs.extend(
                    sum(
                        [
                            cls.get_locs(c,
                                         unicode_offsets)
                            for c in sexp.get_children()
                        ],
                        start=[]))
        return locs

    @classmethod
    def is_ltac(cls, vernac: Union[str, SexpNode, SexpInfo.Vernac]) -> bool:
        """
        Determine whether the given sexp contains Ltac (see below).

        Parameters
        ----------
        vernac : str or SexpNode or SexpInfo.Vernac
            An s-expression, presumed to be correspond to a valid AST of
            a Vernacular command.
            If a string is given, then it is implicitly parsed to an
            s-expression.
            Alternatively, an analyzed Vernacular command may be
            provided (e.g., as obtained from `analyze_vernac`).

        Returns
        -------
        bool
            True if the input comprises Ltac, False otherwise.

        Raises
        ------
        IllegalSexpOperationException
            If `vernac` is a string and fails to parse to a `SexpNode`.
        SexpAnalyzingException
            If `vernac` is a string or `SexpNode` and does not conform
            to the expected structure of a Vernacular command.

        Notes
        -----
        This function does not simply detect Ltac in a strict sense but
        also determines whether the given input corresponds to a
        sentence that would occur only while in proof mode (such as
        ``Proof.``, ``Qed.``, or a brace/bullet).
        """  # noqa: B950
        # TODO: Rename function to be more accurate
        if not isinstance(vernac, SexpInfo.Vernac):
            if not isinstance(vernac, SexpNode):
                vernac = SexpParser.parse(vernac)
            vernac = cls.analyze_vernac(vernac, with_flags=False)
        if vernac.extend_type is not None:
            if cls._vt_proof_extend_regex.match(vernac.extend_type) is not None:
                # The sentence is part of a proof
                return True
            else:
                # The sentence is defining new tactics or otherwise not
                # part of a proof
                return False
        elif cls._vt_proof_regex.match(vernac.vernac_type) is not None:
            # The sentence is part of a proof
            return True
        else:
            # The sentence is not ltac-related and not part of a proof
            return False

    @classmethod
    def offset_locs(
            cls,
            sexp: SexpNode,
            unicode_offsets: List[int],
            byte_to_char: bool = True) -> SexpNode:
        """
        Offset the locations in an s-expression based on encoding.

        Locations are translated between indices of a bytestring and
        indices of UTF-8 characters in a Python `str`.

        Parameters
        ----------
        sexp : SexpNode
            An s-expression, presumed to be correspond to a valid AST
            with locations relative to either bytestring indices or
            UTF-8 characters as appropriate for the `byte_to_char`
        unicode_offsets : List[int]
            Offsets of unicode (non-ASCII) characters from the start of
            the file.
        byte_to_char : bool, optional
            The direction of the offset process, by default True.
            If True, then the locations are interpreted to contain the
            indices of bytes in a UTF-8-encoded bytestring and are to
            be converted to the indices of UTF-8 unicode characters in a
            string.
            If False, then the reverse interpretation and transformation
            is applied.

        Returns
        -------
        SexpNode
            The given `sexp` with locations offset according to the
            provided arguments.
        """
        if sexp.is_list():
            if sexp.head() == "loc" and sexp[1].children:
                if not byte_to_char:
                    unicode_offsets = None
                loc: SexpInfo.Loc = cls.analyze_loc(sexp, unicode_offsets)
                if not byte_to_char:
                    loc = loc.offset_char_to_byte(unicode_offsets)
                sexp = loc.to_sexp()
            else:
                sexp = SexpList(
                    [
                        cls.offset_locs(c,
                                        unicode_offsets,
                                        byte_to_char)
                        for c in sexp.get_children()
                    ])
        return sexp
