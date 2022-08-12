"""
Provides methods for extracting Gallina terms from parsed s-expressions.

Adapted from `roosterize.parser.SexpAnalyzer`
at https://github.com/EngineeringSoftware/roosterize/.
"""
from __future__ import annotations

import collections
import functools
import logging
import re
from dataclasses import asdict, dataclass
from typing import (
    Any,
    Callable,
    Counter,
    Iterable,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

from deprecated.sphinx import deprecated

from prism.language.gallina.util import ParserUtils
from prism.language.sexp import IllegalSexpOperationException, SexpNode
from prism.language.sexp.list import SexpList
from prism.language.sexp.string import SexpString
from prism.language.token import TokenConsts
from prism.util.radpytools.dataclasses import default_field, immutable_dataclass

from .exception import SexpAnalyzingException


class SexpInfo:
    """
    Defines varies structs that may be results of SexpAnalyzer.
    """

    @dataclass
    class Vernac:
        """
        A vernacular command.
        """

        vernac_type: str = ""
        extend_type: str = ""
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

    @immutable_dataclass
    class Loc:
        """
        A location within a file.
        """

        filename: str
        lineno: int
        bol_pos: int
        lineno_last: int
        bol_pos_last: int
        beg_charno: int
        end_charno: int

        def __contains__(self, other: Union[SexpInfo.Loc, int, float]) -> bool:
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
                return NotImplemented

        def __lt__(self, other: Union[SexpInfo.Loc, int, float]) -> bool:
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

        def __gt__(self, other: Union[SexpInfo.Loc, int, float]) -> bool:
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
            other: SexpInfo.Loc,
        ) -> SexpInfo.Loc:
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

        def shift(self, offset: int) -> SexpInfo.Loc:
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

        def union(self, *others: Tuple[SexpInfo.Loc, ...]) -> SexpInfo.Loc:
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
                loc: SexpInfo.Loc,
                *others: Tuple[SexpInfo.Loc,
                               ...]) -> SexpInfo.Loc:
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

    @classmethod
    def analyze_vernac(cls, sexp: SexpNode) -> SexpInfo.Vernac:
        """
        Analyze an s-expression representing a Vernacular command.

        Analyzes an s-expression and parses it as a Vernac expression,
        getting the type of the expression and its source code location.

        Parameters
        ----------
        sexp : SexpNode
            A parsed s-expression node representing a Vernacular command
            term.
            The structure should conform to the following format:
            <sexp_vernac> = ( ( v (VernacExpr (...) ( <TYPE>  ... )) )
                                ^----------vernac_sexp-----------^
                            <sexp_loc> )

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
            if len(sexp) != 2:
                raise SexpAnalyzingException(sexp)

            v_child = sexp[0]
            loc_child = sexp[1]

            loc = cls.analyze_loc(loc_child)

            extend_type = ""

            if v_child[0].content == "v" and v_child[1][
                    0].content == "VernacExpr":
                # ( v (VernacExpr()  (   <TYPE>  ... )) )
                #   0 1  1,0     1,1 1,2 1,2,0
                # ( v (VernacExpr()  <TYPE> ) )
                #                    1,2
                if v_child[1][2].is_list():
                    vernac_type = v_child[1][2][0].content
                    if vernac_type == SexpInfo.VernacConsts.type_extend:
                        # ( v (
                        #    VernacExpr() (
                        #      VernacExtend  (
                        #        <EXTEND_TYPE> ... ) ...
                        extend_type = v_child[1][2][1][0].content
                    # end if
                else:
                    vernac_type = v_child[1][2].content
                # end if
            elif v_child[0].content == "v" and v_child[1][
                    0].content == "VernacFail":
                # v_child
                # ( v (VernacFail ( ( v (VernacExpr () ( ...
                #   0 1  1,0
                vernac_type = "VernacFail"
            else:
                raise SexpAnalyzingException(sexp)
            # end if

            return SexpInfo.Vernac(
                vernac_type=vernac_type,
                extend_type=extend_type,
                vernac_sexp=v_child[1],
                loc=loc)
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
                             Any] = int,
            indices: Iterable[int] = (1,
                                      )
        ) -> str:
            if child[0].content != expected:
                raise SexpAnalyzingException(sexp)
            for index in indices:
                child = child[index]
            return parser(child.content)

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
                        indices=(1,
                                 1),
                        parser=str),
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
        except IllegalSexpOperationException:
            raise SexpAnalyzingException(sexp)

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
    @deprecated(reason="This is not used anywhere.", version="0.1.0")
    def find_i_pat_ids(cls, sexp: SexpNode) -> Counter[str]:
        """
        Do something TBD. TODO.

        _extended_summary_

        Parameters
        ----------
        sexp : SexpNode
            _description_

        Returns
        -------
        Counter[str]
            _description_

        Raises
        ------
        SexpAnalyzingException
            _description_
        """
        try:
            i_pat_ids: Counter[str] = collections.Counter()

            def match_i_pad_id_recur(
                    sexp_part: SexpNode) -> SexpNode.RecurAction:
                nonlocal i_pat_ids
                try:
                    # ( IPatId ( Id <pat_id> ))
                    #   0      1 10 11
                    if sexp_part[0].content == "IPatId" and sexp_part[1][
                            0].content == "Id":
                        i_pat_ids[sexp_part[1][1].content] += 1
                        return SexpNode.RecurAction.StopRecursion
                    else:
                        return SexpNode.RecurAction.ContinueRecursion
                    # end if
                except (IllegalSexpOperationException, SexpAnalyzingException):
                    return SexpNode.RecurAction.ContinueRecursion
                # end try

            # end def

            sexp.apply_recur(match_i_pad_id_recur)

            return i_pat_ids
        except IllegalSexpOperationException:
            raise SexpAnalyzingException(sexp)

    @classmethod
    @deprecated(reason="This is not used anywhere.", version="0.1.0")
    def cut_lemma_backend_sexp(cls, sexp: SexpNode) -> SexpNode:
        """
        Do something TBD. TODO.

        _extended_summary_

        Parameters
        ----------
        sexp : SexpNode
            _description_

        Returns
        -------
        SexpNode
            _description_
        """

        def pre_children_modify(
            current: SexpNode) -> Tuple[Optional[SexpNode],
                                        SexpNode.RecurAction]:
            while True:
                no_change = True

                # TODO: Different Coq.Init names, experiment removing
                # them at later phases.

                # ( ( v <X> ) ( loc () ) ) -> <X>
                if (current.is_list() and len(current) == 2
                        and current[0].is_list() and len(current[0]) == 2
                        and current[0][0].is_string()
                        and current[0][0].content == "v"
                        and current[1].is_list() and len(current[1]) == 2
                        and current[1][0].is_string()
                        and current[1][0].content == "loc"
                        and current[1][1].is_list()
                        and len(current[1][1]) == 0):
                    # then
                    current = current[0][1]
                    no_change = False
                # end if

                # ( <A> <X> ) -> <X>,
                # where <A> in [Id, ConstRef, Name, GVar]
                if (current.is_list() and len(current) == 2
                        and current[0].is_string()
                        and current[0].content in ["Id",
                                                   "ConstRef",
                                                   "Name",
                                                   "GVar"]):
                    # then
                    current = current[1]
                    no_change = False
                # end if

                # # ( <A> ( <Xs> ) <Ys> ) -> ( <Ys> ),
                # # where <A> in [MPfile]
                # if (current.is_list() and len(current) >= 2
                #         and current[0].is_string()
                #         and current[0].content in ["MPfile"]
                #         and current[1].is_list()):
                #     # then
                #     del current.get_children()[0 : 2]
                #     no_change = False
                # # end if

                # # ( <A> ( <Xs> ) <Ys> ) -> ( <Xs> <Ys> ),
                # # where <A> in [MPdot, DirPath, Constant, MulInd]
                # if (current.is_list() and len(current) >= 2
                #         and current[0].is_string()
                #         and current[0].content in ["MPdot",
                #                                    "DirPath",
                #                                    "Constant",
                #                                    "MutInd"]
                #         and current[1].is_list()):
                #     # then
                #     current[1].get_children().extend(current[2 :])
                #     current = current[1]
                #     no_change = False
                # # end if

                # ( <A> ( <Xs> ) <Ys> )
                #     -> <Ys[-1]>, or ( <A> ( <Xs> ) ) -> <Xs[-1]>,
                # where <A> in
                # [MPdot, DirPath, Constant, MulInd, MPfile]
                if (current.is_list() and len(current) >= 2
                        and current[0].is_string()
                        and current[0].content in ["MPdot",
                                                   "DirPath",
                                                   "Constant",
                                                   "MutInd",
                                                   "MPfile"]
                        and current[1].is_list() and len(current[1]) > 0):
                    # then
                    if len(current) == 2:
                        current = current[1][-1]
                    else:
                        current = current[-1]
                    # end if
                    no_change = False
                # end if

                # ( <A> <X> ()) -> <X>, where <A> in [GRef]
                if (current.is_list() and len(current) == 3
                        and current[0].is_string()
                        and current[0].content in ["GRef"]
                        and current[2].is_list() and len(current[2]) == 0):
                    # then
                    current = current[1]
                    no_change = False
                # end if

                # # ( <A> <X> ( <Ys> ) ) -> ( <X> <Ys> ),
                # # where <A> in [GApp]
                # if (current.is_list() and len(current) == 3
                #         and current[0].is_string()
                #         and current[0].content in ["GApp"]
                #         and current[2].is_list()):
                #     # then
                #     current = (SexpList([current[1]]
                #                + current[2].get_children()))
                #     no_change = False
                # # end if

                # ( IndRef ( ( <Xs> ) <n> ) ) -> <Xs[-1]>
                if (current.is_list() and len(current) == 2
                        and current[0].is_string()
                        and current[0].content == "IndRef"
                        and current[1].is_list() and len(current[1]) == 2
                        and current[1][0].is_list() and len(current[1][0]) > 0):
                    # then
                    current = current[1][0][-1]
                    no_change = False
                # end if

                # ( ConstructRef ( ( ( <Xs> ) <n> ) <m> ) ) -> <Xs[-1]>
                if (current.is_list() and len(current) == 2
                        and current[0].is_string()
                        and current[0].content == "ConstructRef"
                        and current[1].is_list() and len(current[1]) == 2
                        and current[1][0].is_list() and len(current[1][0]) == 2
                        and current[1][0][0].is_list()
                        and len(current[1][0][0]) > 0):
                    # then
                    current = current[1][0][0][-1]
                    no_change = False
                # end if

                if no_change:
                    break
            # end while

            # ( GProd . <X> ... ) -> ( GProd . ... )
            if (current.is_list() and len(current) >= 3
                    and current[0].is_string()
                    and current[0].content == "GProd"):
                # then
                del current.get_children()[2]
            # end if

            return current, SexpNode.RecurAction.ContinueRecursion

        # end def

        sexp = sexp.modify_recur(pre_children_modify)

        return sexp

    @classmethod
    @deprecated(reason="This is not used anywhere.", version="0.1.0")
    def split_lemma_backend_sexp(cls,
                                 sexp: SexpNode) -> Tuple[Optional[SexpNode],
                                                          SexpNode]:
        """
        Do something TBD. TODO.

        _extended_summary_

        Parameters
        ----------
        sexp : SexpNode
            _description_

        Returns
        -------
        Tuple[Optional[SexpNode], SexpNode]
            _description_
        """
        last_gprod_node: Optional[SexpNode] = None
        first_non_gprod_node: SexpNode = None

        def find_first_non_gprod(sexp: SexpNode):
            nonlocal last_gprod_node, first_non_gprod_node
            if (sexp.is_list() and len(sexp) >= 2 and sexp[0].is_string()
                    and sexp[0].content == "GProd"):
                # then
                last_gprod_node = sexp
                find_first_non_gprod(sexp[-1])
            else:
                first_non_gprod_node = sexp
                return
            # end if

        # end def

        find_first_non_gprod(sexp)

        # TODO: return a list of the GProds instead of tree, currently
        # set to None
        return None, first_non_gprod_node
