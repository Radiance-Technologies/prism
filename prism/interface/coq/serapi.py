"""
Defines class for line-by-line interaction with SerAPI.

Adapted from CoqGym's SerAPI module at
https://github.com/princeton-vl/CoqGym/blob/master/serapi.py.
"""
import logging
import os
import re
import signal
import sys
import typing
from contextlib import contextmanager
from dataclasses import InitVar, dataclass, field
from functools import cached_property
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    Iterable,
    List,
    NoReturn,
    Optional,
    Tuple,
    TypeAlias,
    Union,
)

import pexpect
from pexpect.popen_spawn import PopenSpawn

from prism.interface.coq.environ import (
    Constant,
    Environment,
    MutualInductive,
    OneInductive,
)
from prism.interface.coq.exception import CoqExn, CoqTimeout
from prism.interface.coq.goals import Goal, Goals, Hypothesis
from prism.interface.coq.names import mod_path_file, print_ker_name
from prism.interface.coq.options import CoqSetting, SerAPIOptions
from prism.interface.coq.re_patterns import (
    ADDED_STATE_PATTERN,
    NAMED_DEF_ASSUM_PATTERN,
    NEW_IDENT_PATTERN,
    PRINT_ALL_IDENT_PATTERN,
)
from prism.language.sexp import SexpNode
from prism.language.sexp.exception import IllegalSexpOperationException
from prism.language.sexp.list import SexpList
from prism.language.sexp.parser import SexpParser
from prism.language.sexp.string import SexpString
from prism.util.iterable import CallableIterator, uniquify
from prism.util.logging import default_log_level
from prism.util.opam import OpamSwitch
from prism.util.opam.version import OpamVersion, Version
from prism.util.radpytools import PathLike
from prism.util.radpytools.dataclasses import default_field
from prism.util.string import escape, normalize_spaces, unquote

logger = logging.getLogger(__file__)
logger.setLevel(default_log_level())

AbstractSyntaxTree: TypeAlias = SexpNode


@dataclass
class SerAPI:
    """
    An interactive Coq session facilitated by SerAPI (namely `sertop`).

    Examples
    --------
    >>> with SerAPI() as serapi:
    ...     serapi.execute("Require Import Coq.Program.Basics.")
    ...     serapi.execute('Locate "_ ∘ _".')
    """

    sertop_options: InitVar[SerAPIOptions] = SerAPIOptions.empty()
    """
    Optional command-line options to `sertop`, especially IQR flags for
    linking logical and physical library paths.
    """
    opam_switch: InitVar[Optional[OpamSwitch]] = None
    """
    The switch in which to invoke `sertop`, which implicitly controls
    the version of Coq and SerAPI that are used.
    By default, the global "default" switch is selected.
    """
    omit_loc: InitVar[bool] = False
    """
    Whether to shorten and replace locations with a filler token or to
    yield full location information, by default False.
    """
    max_wait_time: InitVar[int] = 30
    """
    The timeout for responses from the spawned SerAPI process.
    """
    cwd: InitVar[Optional[str]] = None
    """
    The working directory in which to invoke `sertop`, which implicitly
    affects the physical and logical library path bindings.
    By default, the current working directory of the parent process is
    used.
    """
    frame_stack: List[List[int]] = default_field([])
    """
    A stack of frames capturing restorable checkpoints in execution.
    """
    ast_cache: Dict[str,
                    AbstractSyntaxTree] = default_field({})
    """
    A cache of retrieved ASTs that avoids repeated `sertop` queries.
    The cache maps human-readable commands to their corresponding ASTs.
    """
    constr_cache: Dict[str,
                       str] = default_field({})
    """
    A cache of retrieved kernel terms that avoids repeated `sertop`
    queries.
    The cache maps s-expressions of type
    ``coq/kernel/constr.mli:constr`` to human-readable representations.
    """
    _dead: bool = field(default=False, init=False)
    """
    The status of the connection to the `sertop` child process.
    """
    _proc: PopenSpawn = field(init=False)
    """
    The `sertop` child process.
    """
    _switch: OpamSwitch = field(init=False)
    """
    The switch in which `sertop` is being executed.
    """
    _allow_sprop: bool = True
    """
    Whether this session allows use of the `SProp` sort.
    """

    def __post_init__(
            self,
            sertop_options: SerAPIOptions,
            opam_switch: Optional[OpamSwitch],
            omit_loc: bool,
            timeout: int,
            cwd: Optional[str]):
        """
        Initialize the SerAPI subprocess.
        """
        if opam_switch is None:
            opam_switch = OpamSwitch()
        if cwd is None:
            cwd = os.getcwd()
        self._switch = opam_switch
        self._cwd = cwd
        sertop_args = sertop_options.as_serapi_args(self.serapi_version)
        if sertop_options.disallow_sprop:
            self._allow_sprop = False
        try:
            cmd = f"sertop --implicit --print0 {sertop_args}"
            if omit_loc:
                cmd = cmd + " --omit_loc"
            if opam_switch.is_clone:
                cmd, _, _ = opam_switch.as_clone_command(cmd)
            self._proc = PopenSpawn(
                cmd,
                encoding="utf-8",
                codec_errors='surrogateescape',
                timeout=timeout,
                maxread=10000000,
                env=opam_switch.environ,
                cwd=cwd)
        except FileNotFoundError:
            logger.log(
                logging.ERROR,
                'Please make sure the "sertop" program is in the PATH.\n'
                'You may have to run "eval $(opam env)".')
            sys.exit(1)
        try:
            self._proc.expect_exact(
                "(Feedback((doc_id 0)(span_id 1)(route 0)(contents Processed)))\0"
            )
        except pexpect.EOF as e:
            logger.log(
                logging.ERROR,
                f"Unexpected EOF. Debug information: {self.debug_information()}"
            )
            raise RuntimeError(
                f"Unexpected EOF with switch={self._switch} "
                f"and SerAPI version {self.serapi_version}.\n"
                f"Debug information: {self.debug_information()}") from e
        self.send("Noop")

        # reflect the rest of the arguments
        for (do_send,
             command) in sertop_options.get_sertop_commands(
                 self.serapi_version):
            if do_send:
                self.send(command)
            else:
                self.execute(command, verbose=False)

        # global printing options
        self.execute("Unset Printing Notations.")
        self.execute("Unset Printing Wildcard.")
        self.execute("Set Printing Coercions.")
        self.execute("Unset Printing Allow Match Default Clause.")
        self.execute("Unset Printing Factorizable Match Patterns.")
        self.execute("Unset Printing Compact Contexts.")
        self.execute("Set Printing Implicit.")
        self.execute("Set Printing Depth 999999.")
        self.execute("Unset Printing Records.")
        if (not OpamVersion.less_than(self.serapi_version,
                                      '8.10.0') and self._allow_sprop):
            # required for query_env to get the types/sorts of all
            # constants
            self.execute("Set Allow StrictProp.")

        # initialize the stack
        self.push()

    def __enter__(self) -> 'SerAPI':
        """
        Initialize a context encompassing a SerAPI session.
        """
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Conclude a context for a SerAPI session.
        """
        self.shutdown()

    @property
    def is_alive(self) -> bool:
        """
        Return whether the session is active or not.
        """
        return not self.is_dead

    @property
    def is_dead(self) -> bool:
        """
        Return whether the session has been terminated or not.
        """
        return self._dead

    @property
    def is_in_proof_mode(self) -> bool:
        """
        Return whether the interpreter is in proof mode.

        Property alias for `has_open_goals`.
        """
        if self.is_dead:
            return False
        else:
            return self.has_open_goals()

    @cached_property
    def serapi_version(self) -> Version:
        """
        Get the version of SerAPI for this session.
        """
        version = self.switch.get_installed_version("coq-serapi")
        assert version is not None
        return Version.parse(version)

    @property
    def switch(self) -> OpamSwitch:
        """
        Get the switch in which this SerAPI session is being executed.
        """
        return self._switch

    @property
    def timeout(self) -> int:
        """
        Get the timeout for responses from the SerAPI process.
        """
        return self._proc.timeout

    @timeout.setter
    def timeout(self, timeout: int):
        """
        Set the timeout for responses from the SerAPI process.
        """
        self._proc.timeout = timeout

    @property
    def working_directory(self) -> str:
        """
        Get the directory in which the SerAPI process is being executed.
        """
        return self._cwd

    def _handle_identifier_reserved_coqexn(
            self,
            exc: CoqExn,
            f: Callable[[Any],
                        Any],
            *args,
            **kwargs) -> Any:
        """
        Handle ``"The identifier <ident> is reserved."`` exceptions.

        Certain reserved identifiers may appear when ssreflect is
        required, and they raise an error when parsed.
        Temporarily lower the error to a warning and try again.
        See `coq/plugins/ssrparser.mlg` for more information.

        This function attempts to recompute the given function, which is
        presumed to have raised the above error, within a temporary,
        safe context where the error is reduced to a warning.

        Parameters
        ----------
        exc : CoqExn
            A Coq exception.
        f : Callable[..., Any]
            The function that originally raised the exception.
        args
            The original positional arguments to `f`.
        kwargs
            The original keyword arguments to `f`.

        Returns
        -------
        Any
            The desired result of `f`.

        Raises
        ------
        CoqExn
            If `exc` is not an instance of the above exception.
        """
        if exc.msg.endswith("is reserved."):
            self.execute("Unset SsrIdents.")
            result = f(*args, **kwargs)
            self.execute("Set SsrIdents.")
            return result
        else:
            raise exc

    def _process_coq_exn(self, exception: SexpNode) -> NoReturn:
        """
        Process and raise a `CoqExn`.

        Parameters
        ----------
        exception : SexpNode
            A serialized `CoqExn` object.

        Raises
        ------
        CoqExn
            An exception conveying the message of the given serialized
            exception.
        """
        coq_exn = exception[2]
        assert coq_exn[0] == SexpString("CoqExn")
        if OpamVersion.less_than(self.serapi_version, "8.10"):
            # Multiple exception types may appear here, each
            # with their own structure.
            # Instead of trying to anticipate every potential
            # exception, just grab all of the strings (expected
            # to be messages) and concatenate them.
            msg = '; '.join(
                [
                    unquote(s.get_content())
                    for s in coq_exn[4][1].flatten()
                    if isinstance(s,
                                  SexpString) and unquote(s.get_content())
                ])
        else:
            msg = coq_exn[1][5][1]
            assert isinstance(msg, SexpString)
            msg = unquote(msg.get_content())
        raise CoqExn(msg, str(coq_exn))

    def _process_feedback(self, feedback: SexpNode) -> Optional[str]:
        """
        Process and return a serialized feedback message.

        Parameters
        ----------
        feedback : SexpNode
            A serialized message containing user feedback.

        Returns
        -------
        Optional[str]
            The message contained in the `feedback` or None if
            `feedback` does not match the expected structure.
        """
        msg = feedback[1][3][1]
        if (msg.is_list() and msg != [] and msg[0] == SexpString("Message")):
            if OpamVersion.less_than(self.serapi_version, "8.10"):
                (msg,
                 _,
                 _
                 ) = self.send(f"(Print ((pp_format PpStr)) (CoqPp {msg[3]}))")
                msg = msg[1][2][1][0][1]
            else:
                msg = msg[4][1]
            assert msg.is_string()
            msg = msg.get_content()
            assert msg is not None
            return unquote(msg)
        else:
            return None

    def _query_type(self, term: str, mod: int = 0) -> str:
        """
        Get the type of the given expression.

        Notes
        -----
        This method serves as a more robust fallback to the default
        TypeOf query, which only works for known identifiers.
        As a workaround for handling arbitrary expressions, a temporary
        definition is assigned the value of the expression and queried
        against instead.
        """
        tmpid = 'temp_term_' + str(mod)
        self.push()
        try:
            self.execute(f"Definition {tmpid} := {term}.")
        except CoqExn as e:
            self.pop()
            if e.msg.endswith("already exists."):
                return self._query_type(term, mod + 1)
            else:
                raise e
        else:
            result = self.query_type(tmpid)
            self.pop()
        return result

    def cancel(self, states: Iterable[int]) -> None:
        """
        Cancel the indicated commands.

        Parameters
        ----------
        states : Iterable[int]
            The IDs of previously submitted commands.
        """
        self.send(f"(Cancel ({' '.join([str(s) for s in states])}))")

    def debug_information(self, last_str_chars: int = 100) -> str:
        """
        Get a string containing useful debug information.

        Parameters
        ----------
        last_str_chars : int, optional
            The number of characters to print from the child process
            buffer, by default 100.

        Returns
        -------
        str1
            Debug information for the child process.
        """
        # adapted from `pexpect.spawn.__str__`
        s = []
        s.append(repr(self._proc))
        s.append('command: ' + str(self._proc.proc.args))
        buffer = self._proc.buffer[-last_str_chars :]
        s.append(f'buffer (last {last_str_chars} chars): {buffer}')
        before = self._proc.before[
            -last_str_chars :] if self._proc.before else ""
        s.append(f'before (last {last_str_chars} chars): {before}')
        s.append(f'after: {self._proc.after}')
        s.append(f'match: {self._proc.match}')
        s.append('match_index: ' + str(self._proc.match_index))
        s.append('exitstatus: ' + str(self._proc.exitstatus))
        if hasattr(self._proc, 'ptyproc'):
            s.append('flag_eof: ' + str(self._proc.flag_eof))
        s.append('pid: ' + str(self._proc.pid))
        s.append('child_fd: ' + str(self._proc.child_fd))
        s.append('closed: ' + str(self._proc.closed))
        s.append('timeout: ' + str(self.timeout))
        s.append('delimiter: ' + str(self._proc.delimiter))
        s.append('logfile: ' + str(self._proc.logfile))
        s.append('logfile_read: ' + str(self._proc.logfile_read))
        s.append('logfile_send: ' + str(self._proc.logfile_send))
        s.append('maxread: ' + str(self._proc.maxread))
        s.append('ignorecase: ' + str(self._proc.ignorecase))
        s.append('searchwindowsize: ' + str(self._proc.searchwindowsize))
        s.append('delaybeforesend: ' + str(self._proc.delaybeforesend))
        s.append('delayafterread: ' + str(self._proc.delayafterread))
        s.append('delayafterclose: ' + str(self._proc.delayafterclose))
        s.append('delayafterterminate: ' + str(self._proc.delayafterterminate))
        return '\n'.join(s)

    def execute(
        self,
        cmd: str,
        return_ast: bool = False,
        verbose: bool = True
    ) -> Union[Tuple[List[SexpNode],
                     List[str]],
               Tuple[List[SexpNode],
                     List[str],
                     AbstractSyntaxTree]]:
        """
        Execute a command.

        Parameters
        ----------
        cmd : str
            A command (i.e., a sentence).
        return_ast : bool, optional
            Whether to return the AST of the command or not, by default
            False.
        verbose : bool, optional
            Whether to return verbose feedback for the command.
            For example, verbose feedback may indicate the names of
            newly introduced constants.

        Returns
        -------
        responses : List[SexpNode]
            The response from SerAPI after execution of the command.
        feedback : List[str]
            Feedback from the Coq Proof Assistant to the executed
            command.
        ast : AbstractSyntaxTree, optional
            If `return_ast` is True, then the AST of `cmd` is also
            returned.
        """
        state_id, ast, feedback = self.send_add(cmd, return_ast, verbose)
        responses, exec_feedback, _ = self.send(f"(Exec {state_id})")
        feedback.extend(exec_feedback)
        if return_ast:
            assert ast is not None
            return responses, feedback, ast
        else:
            return responses, feedback

    def get_local_ids(self) -> List[str]:
        """
        Get all the in-scope identifiers defined in the current session.

        Returns
        -------
        List[str]
            A list of the in-scope identifiers introduced in this
            interactive session in the order of their definition.

        Raises
        ------
        CoqExn
            In certain situations where ``Print All.`` may refuse to
            print due to Coq internal state (such as an opaque proof).

        Notes
        -----
        The list of identifiers returned should match that yielded from
        the ``Print All.`` Vernacular command.
        """
        print_all_message = self.query_vernac("Print All.")
        print_all_message_str = '\n'.join(print_all_message)
        idents: List[str] = []
        # replace each span covered by a named def or assumption
        # by a constant-parseable equivalent
        print_all_message_str = NAMED_DEF_ASSUM_PATTERN.sub(
            CallableIterator(
                f"{m} : " for m in NAMED_DEF_ASSUM_PATTERN.findall(
                    print_all_message_str)),
            print_all_message_str)
        for match in PRINT_ALL_IDENT_PATTERN.finditer(print_all_message_str):
            idents.extend(
                v for v in match.groupdict().values() if v is not None)
        return idents

    def get_conjecture_id(self) -> Optional[str]:
        """
        Get the name of the conjecture currently being proved.

        Returns
        -------
        Optional[str]
            The name of the current conjecture or None if no proof is
            active.
        """
        try:
            ids = self.query_vernac("Show Conjectures.")
        except CoqExn:
            return None
        ids_str = '\n'.join(ids)
        try:
            return ids_str.split()[0]
        except IndexError:
            return None

    def has_open_goals(self) -> bool:
        """
        Return whether there are any open goals for the current state.

        If there are open goals, then the Coq interpreter is in proof
        mode.
        """
        responses, _, _ = self.send("(Query () Goals)")
        assert responses[1][2][0] == SexpString("ObjList")
        return responses[1][2][1] != SexpList()

    def pop(self) -> None:
        """
        Pop the current frame and rollback to the previous checkpoint.

        See Also
        --------
        push
        pop_n
        """
        self.pop_n(1)

    def pop_n(self, n: int) -> None:
        """
        Pop the top `n` frames and rollback to a previous checkpoint.

        Parameters
        ----------
        n : int
            The number of frames to pop.

        Raises
        ------
        IndexError
            If `n` exceeds the size of the frame stack.

        See Also
        --------
        push
        pop
        """
        if n > len(self.frame_stack):
            raise IndexError(f"Cannot pop {n} frames; exceeds stack size")
        popped_states = []
        for _ in range(n):
            popped_frame = self.frame_stack.pop()
            popped_states.extend(popped_frame)
        self.cancel(popped_states)
        if not self.frame_stack:
            # re-initialize the stack
            self.push()

    def print_constr(self, sexp_str: str) -> Optional[str]:
        """
        Print a Coq kernel term in a human-readable format.

        Parameters
        ----------
        sexp_str : str
            A serialized internal representation of a Coq kernel term.

        Returns
        -------
        str | None
            A human-readable representation of the kernel term.

        Raises
        ------
        CoqExn
            If an error is encountered when interpreting the command to
            print the term, e.g., if `sexp_str` does not represent a
            Coq kernel term.
        """
        if sexp_str not in self.constr_cache:
            if OpamVersion.less_than(self.serapi_version, "8.10.0"):
                pp_opts = "((pp_format PpStr))"
            else:
                pp_opts = "((pp ((pp_format PpStr))))"
            try:
                responses, _, _ = self.send(
                    f"(Print {pp_opts} (CoqConstr {sexp_str}))"
                )
            except CoqExn as ex:
                if ex.msg == "Not_found":
                    return None
                else:
                    raise ex
            try:
                constr = responses[1][2][1][0][1]
            except IllegalSexpOperationException:
                constr = responses[0][2][1][0][1]
            assert isinstance(constr, SexpString)
            self.constr_cache[sexp_str] = normalize_spaces(
                unquote(constr.get_content()))
        return self.constr_cache[sexp_str]

    def pull(self, index: int = -1) -> int:
        """
        Remove a frame created by `push`.

        The associated checkpoint can no longer be restored, but the
        current state is unaffected.

        Returns
        -------
        int
            The size of the pulled frame.
        """
        num_frames = len(self.frame_stack)
        if index >= num_frames or index < -num_frames:
            raise IndexError(
                f"Frame {index} is out of bounds [{-num_frames}, {num_frames-1}]"
            )
        if index >= 0:
            index = index - len(self.frame_stack)
        states = self.frame_stack.pop(index)
        self.frame_stack[index].extend(states)
        return len(states)

    def push(self) -> None:
        """
        Push a new frame onto the state stack (make a checkpoint).

        Pushing the frame onto the stack allows one to rollback to the
        current state.

        See Also
        --------
        pop
        pop_n
        """
        self.frame_stack.append([])

    def query_ast(
            self,
            cmd: str,
            is_escaped: bool = False) -> AbstractSyntaxTree:
        """
        Query the AST of the given Vernacular command.

        Parameters
        ----------
        cmd : str
            A Vernacular command.
        is_escaped : bool, optional
            Whether special characters in the given command are already
            escaped (True) or need to be escaped within this function
            (False).

        Returns
        -------
        AbstractSyntaxTree
            The AST for the given command.
        """
        try:
            ast = self.ast_cache[cmd]
        except KeyError:
            try:
                (responses,
                 _,
                 _) = self.send(
                     f'(Parse () "{cmd if is_escaped else escape(cmd)}")')
            except CoqExn as e:
                ast = self._handle_identifier_reserved_coqexn(
                    e,
                    self.query_ast,
                    cmd)
            else:
                ast = responses[1][2][1][0]
                assert ast[0] == SexpString("CoqAst")
                if OpamVersion.less_than("8.10.2", self.serapi_version):
                    # vernac_control data structure changed in Coq 8.11
                    ast = ast[1][0][1]
                else:
                    ast = ast[1][1]
                self.ast_cache[cmd] = ast
        return ast

    def _query_env(
            self,
            current_file: Optional[PathLike] = None) -> Environment:
        """
        Query the global environment.

        Parameters
        ----------
        current_file : Optional[PathLike], optional
            The file from which commands for the current SerAPI session
            are drawn, by default None.

        Returns
        -------
        Environment
            The global environment.

        Raises
        ------
        RuntimeError
            If this operation is not supported by the current session's
            version of SerAPI.
        """
        if OpamVersion.less_than(self.serapi_version, "8.9.0"):
            raise RuntimeError(
                "Querying the environment is not supported in SerAPI "
                f"version {self.serapi_version}.")
        if current_file is None:
            current_file = "<interactive>"
        responses, _, _ = self.send("(Query () Env)")
        # Refer to coq/kernel/environ.mli
        env = responses[1][2][1][0][1]
        env_globals = env[0][1]
        env_constants = env_globals[0][1]
        env_inductives = env_globals[1][1]

        # store the constants
        constants = []
        for const in env_constants:
            ker_name = const[0]
            (qualid,
             modpath) = print_ker_name(
                 ker_name,
                 self.serapi_version,
                 return_modpath=True)
            assert isinstance(modpath, SexpNode)
            if qualid.startswith("SerTop."):
                logical_path = "SerTop"
                physical_path = str(current_file)
            else:
                logical_path = mod_path_file(modpath)
                assert qualid.startswith(logical_path)
                physical_path = os.path.relpath(
                    self.query_library(logical_path))
            physical_path += ":" + qualid[len(logical_path) + 1 :]
            short_ident = self.query_qualid(qualid)
            assert short_ident is not None
            # type
            assert const[1][0][2][0].get_content() == "const_type"
            type_sexp = str(const[1][0][2][1])
            type = self.print_constr(type_sexp)
            assert type is not None
            sort = self.query_type(type)
            # term
            assert const[1][0][1][0] == SexpString("const_body")
            const_body = const[1][0][1][1]
            constant_def_variant = const_body[0].get_content()
            term = None
            if constant_def_variant == "Undef":  # declaration
                opaque = None
            elif constant_def_variant == "Def":  # transparent definition
                opaque = False
                if sort != "Prop" and sort != "SProp":
                    if OpamVersion.less_than(self.serapi_version, "8.14"):
                        const_body = const_body[1][0][1]
                    else:
                        # NOTE: coq/kernel/declarations.ml was modified
                        # in coq 8.14 such that the Constr.t in the
                        # const_body field of a constant_body is no
                        # longer wrapped in a Mod_subst.substituted
                        const_body = const_body[1]
                    term = self.print_constr(str(const_body))
            elif constant_def_variant == "OpaqueDef":  # opaque definition
                opaque = True
            else:
                # Primitive variant added in Coq 8.10.0
                assert constant_def_variant == "Primitive"
                opaque = None
            constants.append(
                Constant(
                    physical_path=physical_path,
                    short_id=short_ident,
                    full_id=qualid,
                    term=term,
                    type=type,
                    sort=sort,
                    opaque=opaque,
                    sexp=str(const),
                ))

        # store the inductives
        inductives = []
        for induct in env_inductives:
            ker_name = induct[0]
            (qualid,
             modpath) = print_ker_name(
                 ker_name,
                 self.serapi_version,
                 return_modpath=True)
            assert isinstance(modpath, SexpNode)
            short_ident = self.query_qualid(qualid)
            assert short_ident is not None
            if qualid.startswith("SerTop."):
                logical_path = "SerTop"
                physical_path = str(current_file)
            else:
                logical_path = mod_path_file(modpath)
                physical_path = os.path.relpath(
                    self.query_library(logical_path))
            assert qualid.startswith(logical_path)
            physical_path += ":" + qualid[len(logical_path) + 1 :]
            # blocks
            mutual_inductive_body = induct[1][0]
            mind_packets = mutual_inductive_body[0][1]
            blocks = []
            for blk in mind_packets:
                mind_typename = blk[0][1]
                mind_consnames = blk[3][1]
                mind_user_lc = blk[4][1]
                blk_qualid = ".".join([logical_path, str(mind_typename[1])])
                blk_short_ident = self.query_qualid(blk_qualid)
                assert blk_short_ident is not None
                # constructors
                constructors = []
                assert len(mind_consnames) == len(mind_user_lc)
                for c_name, c_type in zip(mind_consnames, mind_user_lc):
                    c_name = str(c_name[1])
                    # c_type = self.print_constr(str(c_type))
                    # if c_type is not None:
                    #     c_type = UNBOUND_REL_PATTERN.sub(blk_short_ident,  # noqa: W505, B950
                    #                                      c_type)
                    # NOTE (AG): The above is commented from the
                    # original CoqGym implementation.
                    # I cannot find an accurate way to undo
                    # the de Bruijn index substitution and retrieve
                    # the mutually inductive type names in place of
                    # the unbound rels.
                    # However, we do have the constructor name, so we
                    # can fall back on a query and let Coq figure it out
                    # for us.
                    c_type = self.query_type(".".join([logical_path, c_name]))
                    constructors.append((c_name, c_type))
                blocks.append(
                    OneInductive(
                        short_id=blk_short_ident,
                        full_id=blk_qualid,
                        constructors=constructors,
                    ))
            mind_record = mutual_inductive_body[1][1]
            inductives.append(
                MutualInductive(
                    physical_path=physical_path,
                    short_id=short_ident,
                    full_id=qualid,
                    blocks=blocks,
                    is_record=mind_record.get_content() != "NotRecord",
                    sexp=str(induct),
                ))

        return Environment(constants, inductives)

    def query_env(self, current_file: Optional[PathLike] = None) -> Environment:
        """
        Query the global environment.

        Parameters
        ----------
        current_file : Optional[PathLike], optional
            The file from which commands for the current SerAPI session
            are drawn, by default None.

        Returns
        -------
        Environment
            The global environment.

        Raises
        ------
        RuntimeError
            If this operation is not supported by the current session's
            version of SerAPI.
        """
        if not self._allow_sprop:
            with self.settings([CoqSetting(True, "Allow StrictProp")]):
                env = self._query_env(current_file)
        else:
            env = self._query_env(current_file)
        return env

    def query_full_qualid(self, qualid: str) -> Optional[str]:
        """
        Get the fully qualified version of the given identifier.

        The fully qualified version uniquely identifies the object
        without any ambiguity and regardless of scope.

        Parameters
        ----------
        qualid : str
            An identifier, which may already be partially or fully
            qualified.

        Returns
        -------
        Optional[str]
            The fully qualified identifier or None if `qualid` is not
            valid in the current context.
        """
        qualids = self.query_full_qualids(qualid)
        return qualids[0] if qualids else None

    def query_full_qualids(self, qualid: str) -> List[str]:
        """
        Get possible fully qualified IDs for the given identifier.

        Similar to `query_qualids` but ensures that the returned IDs are
        unambiguous regardless of context.

        Parameters
        ----------
        qualid : str
            An identifier, which may already be partially or fully
            qualified.

        Returns
        -------
        List[str]
            A list of fully qualified identifiers consistent with the
            one given.

        Examples
        --------
        >>> with SerAPI() as serapi:
        ...     serapi.execute("Inductive nat : Type := "
        ...                    "  O : nat "
        ...                    "| S (n : nat) : nat.")
        ...     serapi.query_full_qualids("nat")
        ['SerTop.nat', 'Coq.Init.Datatypes.nat']
        """
        if qualid.startswith('"') or qualid.endswith('"'):
            raise ValueError(f"Cannot qualify notation {qualid}.")
        try:
            feedback_list = self.query_vernac(f"Locate {qualid}.")
        except CoqExn as e:
            try:
                qualids = self._handle_identifier_reserved_coqexn(
                    e,
                    self.query_full_qualids,
                    qualid)
            except CoqExn:
                qualids = []
        else:
            assert feedback_list
            feedback = feedback_list[0]
            if feedback.startswith("No object of basename"):
                return []
            qualids = []
            for line in feedback.splitlines():
                line = line.strip()
                if not line.startswith("("):
                    qualids.append(line.split()[1])
        return qualids

    def query_goals(self) -> Optional[Goals]:
        """
        Retrieve a list of open goals.

        Returns
        -------
        Goals | None
            A collection of open goals or None if there are no open
            goals.
        """
        responses, _, _ = self.send("(Query () Goals)")
        assert responses[1][2][0] == SexpString("ObjList")
        if responses[1][2][1] == SexpList():  # no goals
            goals = None
        else:
            assert len(responses[1][2][1]) == 1

            def deserialize_goals(goals_sexp: SexpNode) -> List[Goal]:
                """
                Deserialize each goal in a list into a Python object.
                """
                goals = []
                for g in goals_sexp:
                    hypotheses = []
                    for h in g[2][1]:
                        hypothesis_kernel_sexp = str(h[2])
                        assert len(h[1]) < 2
                        if len(h[1]) == 0:
                            term = None
                        else:
                            t = h[1][0]
                            if t == SexpList():
                                term = None
                            else:
                                term = self.print_constr(str(t))
                        hypothesis_type = self.print_constr(
                            hypothesis_kernel_sexp)
                        assert hypothesis_type is not None
                        type_sexp = self.query_ast(
                            f"Check {hypothesis_type}.",
                            is_escaped=True)
                        hypothesis_term_sexp = None
                        if term is not None:
                            term_sexp = self.query_ast(
                                f"Check {term}.",
                                is_escaped=True)
                            hypothesis_term_sexp = str(term_sexp)
                        hypothesis = Hypothesis(
                            idents=[str(ident[1]) for ident in h[0][::-1]],
                            term=term,
                            type=hypothesis_type,
                            kernel_sexp=hypothesis_kernel_sexp,
                            term_sexp=hypothesis_term_sexp,
                            type_sexp=str(type_sexp),
                        )
                        hypotheses.append(hypothesis)

                    type_sexp = str(g[1][1])

                    if OpamVersion.less_than(self.serapi_version, "8.10.0"):
                        # access value of name field, which is simply
                        # the uid of an Evar.t
                        # Evar.t defined in coq/kernel/evar.mli
                        evar = int(str(g[0][1]))
                    else:
                        # name replaced with info field containing
                        # unprocessed Evar.t
                        evar = int(str(g[0][1][0][1][1]))
                    goal = Goal(
                        id=evar,
                        type=typing.cast(str,
                                         self.print_constr(type_sexp)),
                        type_sexp=type_sexp,
                        hypotheses=hypotheses[::-1],
                    )
                    sexp = self.query_ast(
                        f"Check {goal.type}.",
                        is_escaped=True)
                    goal.sexp = str(sexp)
                    goals.append(goal)
                return goals

            ser_goals = responses[1][2][1][0][1]

            stack = ser_goals[1][1]
            if OpamVersion.less_than(self.serapi_version, "8.10.0"):
                # ser_goals type does not exist
                # but nearly equivalent pre_goals type does, which hails
                # from coq/proofs/proof.mli
                shelved_goals = ser_goals[2][1]
                abandoned_goals = ser_goals[3][1]
            elif OpamVersion.less_than(self.serapi_version, "8.13.0"):
                # pre_goals replaced by ser_goals
                # bullets field introduced
                shelved_goals = ser_goals[2][1]
                abandoned_goals = ser_goals[3][1]
            else:
                # bullets field moved
                shelved_goals = ser_goals[3][1]
                abandoned_goals = ser_goals[4][1]
            fg_goals = deserialize_goals(ser_goals[0][1])
            bg_goals = []
            for frame in stack:
                assert len(frame) == 2
                bg_goals.append(
                    (deserialize_goals(frame[0]),
                     deserialize_goals(frame[1])))
            shelved_goals = deserialize_goals(shelved_goals)
            abandoned_goals = deserialize_goals(abandoned_goals)
            goals = Goals(fg_goals, bg_goals, shelved_goals, abandoned_goals)
            if goals.is_empty:
                goals = None
        return goals

    def query_library(self, lib: str) -> Path:
        """
        Retrieve the physical path of a specified library.

        Parameters
        ----------
        lib : str
            The logical name of a library.

        Returns
        -------
        physical_path : Path
            The physical path bound to `lib`.

        Raises
        ------
        CoqExn
            If `lib` is not the logical name of any library in the
            current context.
        """
        # SerAPI surprisingly does not appear to have a means to query
        # the physical path of a library, and the CoqGym LocateLibrary
        # query is not present.
        feedback_list = self.query_vernac(f"Locate Library {lib}.")
        assert feedback_list
        feedback = feedback_list[0]
        # The following two branches
        try:
            physical_path = feedback.split("has been loaded from file")[-1]
        except IndexError:
            physical_path = feedback.split("is bound to file")[-1]
        return Path(physical_path.strip())

    def query_qualid(self, qualid: str) -> Optional[str]:
        """
        Get the shortest version of the given identifier.

        The shortest version of the given identifier is the minimally
        qualified identifier that unambiguously refers to the same
        object.

        Parameters
        ----------
        qualid : str
            An identifier, which may already be partially or fully
            qualified.

        Returns
        -------
        Optional[str]
            The minimally qualified identifier or None if `qualid` is
            not a valid identifier in the current context.
        """
        qualids = self.query_qualids(qualid)
        return qualids[0] if qualids else None

    def query_qualids(self, qualid: str) -> List[str]:
        """
        Get possible in-scope qualified IDs for the given identifier.

        Parameters
        ----------
        qualid : str
            An identifier, which may already be partially or fully
            qualified.

        Returns
        -------
        List[str]
            A list of minimally qualified identifiers consistent with
            the one given.

        Examples
        --------
        >>> with SerAPI() as serapi:
        ...     serapi.execute("Inductive nat : Type := "
        ...                    "  O : nat "
        ...                    "| S (n : nat) : nat.")
        ...     serapi.query_qualids("nat")
        ['nat', 'Datatypes.nat']
        """
        responses, _, _ = self.send(f'(Query () (Locate "{qualid}"))')
        if responses[1][2][1] == SexpList() and qualid.startswith("SerTop."):
            qualid = qualid[len("SerTop."):]
            responses, _, _ = self.send(f'(Query () (Locate "{qualid}"))')
        qualids = []
        for qid in responses[1][2][1]:
            # strip coq_object (CoqQualId) and location (v)
            qid = qid[1][0][1]
            assert qid[1][0] == SexpString("DirPath")
            short_ident = ".".join(
                [str(x[1]) for x in qid[1][1][::-1]] + [str(qid[2][1])])
            qualids.append(short_ident)
        return qualids

    def query_type(self, term: str) -> str:
        """
        Get the type of the given expression.

        Parameters
        ----------
        term_sexp : str
            A Coq identifier or Gallina expression.

        Returns
        -------
        str
            The type of the given term/expression.

        Raises
        ------
        CoqExn
            If an error is encountered when evaluating the given term.
        """
        try:
            responses, _, _ = self.send(f'(Query () (TypeOf {term}))')
        except (RuntimeError, CoqTimeout):
            result = self._query_type(term)
        except CoqExn as e:
            if e.msg.startswith("Invalid character"):
                result = self._query_type(term)
            else:
                raise e
        else:
            obj_list = responses[1][2][1]
            if obj_list:
                obj = obj_list[0]
                assert obj[0].get_content() == "CoqConstr"
                type_sexp = obj[1]
                result = typing.cast(str, self.print_constr(str(type_sexp)))
            else:
                # fall back to vernacular query
                try:
                    # About query is easier to parse
                    result_list = self.query_vernac(f"About {term}.")
                except CoqExn as e:
                    smart_global_msg = "[smart_global]"
                    if not OpamVersion.less_than(self.serapi_version, "8.10"):
                        smart_global_msg = f"Syntax error: {smart_global_msg}"
                    if e.msg.startswith(smart_global_msg):
                        result_list = self.query_vernac(f"Check {term}.")
                    else:
                        raise e
                assert len(result_list) == 1
                result = result_list[0].split("\n\n")[0]
                pattern = f"({term}" + r"\s+:)"
                match = re.match(pattern, result)
                assert match is not None
                result = normalize_spaces(result[match.end():])
        return result

    def query_vernac(self, cmd: str) -> List[str]:
        """
        Execute a vernacular command and retrieve the result.

        In other words, execute a vernacular query command such as
        ``Print`` or ``Check``.
        A vernacular command such as ``Inductive`` is expected to yield
        an empty list.

        Parameters
        ----------
        cmd : str
            A Coq command.

        Returns
        -------
        feedback : List[str]
            A list of non-fatal errors, warnings, debug statements, or
            other output yielded from Coq in response to executing
            `cmd`.

        Examples
        --------
        >>> with SerAPI() as serapi:
        ...     _ = serapi.execute("Inductive enum := C | D.")
        ...     serapi.query_vernac("Print enum.")
        ['Inductive enum : Set :=  C : enum | D : enum']
        """
        _, feedback, _ = self.send(f'(Query () (Vernac "{escape(cmd)}"))')
        return feedback

    def send(self, cmd: str) -> Tuple[List[SexpNode], List[str], str]:
        """
        Send a command to SerAPI and retrieve the responses.

        Parameters
        ----------
        cmd : str
            A command complying with the SerAPI protocol.

        Returns
        -------
        List[SexpNode]
            A list of responses containing the output of the SerAPI
            command.
        List[str]
            A list of messages obtained from Coq as feedback to the
            command (such as might be observed in an IDE panel).
        str
            The raw uninterpreted response from `sertop`.

        Raises
        ------
        CoqTimeout
            If the time to retrieve the result of the command exceeds
            the configured `timeout`.
        CoqExn
            If the command resulted in an error within Coq.
        """
        if self.is_dead:
            raise RuntimeError("This SerAPI session has been terminated.")
        assert "\n" not in cmd
        self._proc.sendline(cmd)
        try:
            self._proc.expect(
                [
                    r"\(Answer \d+ Ack\)\x00.*\(Answer \d+ Completed\)\x00",
                    r"\(Answer \d+ Ack\)\x00.*\(Answer \d+\(CoqExn.*\)\x00",
                    r"\(Of_sexp_error.*\)\x00"
                ])
        except pexpect.TIMEOUT:
            assert self._proc.before is not None, \
                "A pending response should have been received from sertop"
            print(
                self._proc.before[: 500]
                + "..." if len(self._proc.before) > 500 else "")
            raise CoqTimeout
        assert self._proc.after is not None, \
            "A complete response should have been received from sertop"
        raw_responses: str = self._proc.after
        ack_num_match = re.search(r"^\(Answer (?P<num>\d+)", raw_responses)
        if ack_num_match is not None:
            ack_num = int(ack_num_match["num"])
        else:
            assert raw_responses.startswith("(Of_sexp_error")
            raise RuntimeError(f"Invalid command: {cmd}\n{raw_responses}")
        for num in re.findall(r"(?<=\(Answer) \d+", raw_responses):
            assert int(num) == ack_num
        responses: List[SexpNode] = []
        feedback: List[str] = []
        for item in raw_responses.split("\x00"):
            item = item.strip()
            if item == "":
                continue
            if (not item.startswith("(Feedback")
                    and not item.startswith("(Answer")):
                m = re.search(r"\(Feedback|\(Answer", item)
                if m is None:
                    continue
                item = item[m.span()[0]:]
                assert item.endswith(")")
            parsed_item = SexpParser.parse(item)
            if "CoqExn" in item:  # an error occured in Coq
                self._process_coq_exn(parsed_item)
            if item.startswith("(Feedback"):
                msg = self._process_feedback(parsed_item)
                if msg is not None:
                    feedback.append(msg)
                continue
            responses.append(parsed_item)
        return responses, feedback, raw_responses

    def send_add(
        self,
        cmd: str,
        return_ast: bool,
        verbose: bool = True
    ) -> Tuple[int,
               Optional[AbstractSyntaxTree],
               List[str]]:
        """
        Add a command to the SerAPI buffer and optionally get its AST.

        Parameters
        ----------
        cmd : str
            A command (i.e., a sentence).
        return_ast : bool
            Whether to return the AST or not.
        verbose : bool, optional
            Whether to provide verbose feedback for the added command
            when it is executed.

        Returns
        -------
        state_id : int
            The ID of the added command.
        ast : Optional[AbstractSyntaxTree]
            The AST of the added command or None if `return_ast` is
            False.
        feedback : List[str]
            Feedback from the added command.
        """
        verbose_opt = "(verb true)" if verbose else ""
        _, feedback, raw_responses = self.send(f'(Add ({verbose_opt}) "{escape(cmd)}")')
        state_ids = [
            int(sid) for sid in ADDED_STATE_PATTERN.findall(raw_responses)
        ]
        state_id = state_ids[-1]
        if self.frame_stack != []:
            self.frame_stack[-1].append(state_id)
        if return_ast:
            ast = self.query_ast(cmd)
        else:
            ast = None
        if not verbose:
            feedback = []
        return state_id, ast, feedback

    @contextmanager
    def settings(self,
                 flags: Iterable[CoqSetting]) -> Generator[None,
                                                           None,
                                                           None]:
        """
        Create a context in which given Coq flags are set/unset.
        """
        negated_flags = [CoqSetting(not f.is_set, f.name) for f in flags]
        try:
            for flag in flags:
                self.try_execute(flag.as_command())
            yield
        finally:
            for flag in negated_flags:
                self.try_execute(flag.as_command())

    def shutdown(self) -> None:
        """
        Terminate the interactive session.

        This cannot be undone.
        """
        self._proc.sendeof()
        # pexpect doesn't close everything it should
        if self._proc.proc.stdout is not None:
            self._proc.proc.stdout.close()
        try:
            self._proc.kill(signal.SIGKILL)
        except ProcessLookupError:
            pass
        self._proc.wait()
        self._dead = True

    def try_execute(
        self,
        cmd: str,
        return_ast: bool = False,
        verbose: bool = True
    ) -> Optional[Union[Tuple[List[SexpNode],
                              List[str]],
                        Tuple[List[SexpNode],
                              List[str],
                              AbstractSyntaxTree]]]:
        """
        Execute a command, returning ``None`` if an exception occurs.

        Parameters
        ----------
        cmd : str
            A command (i.e., a sentence).
        return_ast : bool, optional
            Whether to return the AST of the command or not, by default
            False.
        verbose : bool, optional
            Whether to return verbose feedback for the command.
            For example, verbose feedback may indicate the names of
            newly introduced constants.

        Returns
        -------
        responses : List[SexpNode], optional
            The response from SerAPI after execution of the command.
        feedback : List[str], optional
            Feedback from the Coq Proof Assistant to the executed
            command.
        ast : AbstractSyntaxTree, optional
            If `return_ast` is True, then the AST of `cmd` is also
            returned.
        """
        self.push()
        try:
            result = self.execute(cmd, return_ast, verbose)
        except CoqExn:
            self.pop()
            result = None
        else:
            self.pull()
        return result

    @classmethod
    def parse_new_identifiers(cls, feedback: List[str]) -> List[str]:
        """
        Get the identifiers, if any, introduced by the given feedback.

        Parameters
        ----------
        feedback : str
            A single feedback message from a Coq Vernacular command.

        Returns
        -------
        List[str]
            The identifiers introduced in the given feedback message.
        """
        idents = []
        for msg_info in feedback:
            match = NEW_IDENT_PATTERN.search(msg_info)
            if match is not None:
                idents.extend(
                    [m.strip() for m in match.groupdict()["idents"].split(",")])
        return uniquify(idents)
