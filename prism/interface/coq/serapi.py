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
from dataclasses import InitVar, dataclass, field
from itertools import chain
from typing import Dict, Iterable, List, Optional, Tuple, Union

import pexpect
from pexpect.popen_spawn import PopenSpawn

from prism.interface.coq.exception import CoqExn, CoqTimeout
from prism.interface.coq.re_patterns import ADDED_STATE_PATTERN
from prism.interface.coq.util import normalize_spaces
from prism.language.sexp import SexpNode
from prism.language.sexp.list import SexpList
from prism.language.sexp.parser import SexpParser
from prism.language.sexp.string import SexpString
from prism.util.logging import default_log_level
from prism.util.radpytools.dataclasses import default_field

logger = logging.Logger(__file__, default_log_level())


def escape(vernac_cmd: str) -> str:
    """
    Sanitize the given command by escaping special characters.

    Parameters
    ----------
    vernac_cmd : str
        A command to be sent to SerAPI.

    Returns
    -------
    str
        The sanitized command.
    """
    return vernac_cmd.replace("\\", "\\\\").replace('"', '\\"')


def print_mod_path(modpath: SexpNode) -> str:
    if modpath[0] == SexpString("MPdot"):
        return print_mod_path(modpath[1]) + "." + str(modpath[2][1])
    elif modpath[0] == SexpString("MPfile"):
        return ".".join([str(x[1]) for x in modpath[1][1]][::-1])
    else:
        assert modpath[0] == SexpString("MPbound")
        return ".".join(
            [str(x[1])
             for x in modpath[1][2][1]][::-1] + [str(modpath[1][1][1])])


def mod_path_file(modpath: SexpNode) -> str:
    if modpath[0] == SexpString("MPdot"):
        return mod_path_file(modpath[1])
    elif modpath[0] == SexpString("MPfile"):
        return ".".join([str(x[1]) for x in modpath[1][1]][::-1])
    else:
        assert modpath[0] == SexpString("MPbound")
        return ""


AbstractSyntaxTree = SexpNode


@dataclass
class Constant:
    physical_path: os.PathLike
    short_ident: str
    qualid: str
    term: Optional[str]
    type: str
    sort: Optional[str]
    opaque: Optional[bool]
    sexp: str


@dataclass
class Block:
    short_ident: str
    qualid: str
    constructors: List[Tuple[str, str]]


@dataclass
class Inductive:
    physical_path: os.PathLike
    blocks: List[Block]
    is_record: bool
    sexp: str


@dataclass
class Hypothesis:
    idents: List[str]
    term: List[Optional[str]]
    type: str
    sexp: str


@dataclass
class Goal:
    id: int
    type: str
    sexp: str
    hypotheses: List[Hypothesis]


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

    timeout_: InitVar[int] = 30
    """
    The timeout for responses from the spawned SerAPI process.
    """
    frame_stack: List[List[int]] = default_field([])
    """
    A stack of frames capturing restorable checkpoints in execution.
    """
    ast_cache: Dict[str,
                    AbstractSyntaxTree] = default_field({})
    """
    A cache of retrieved ASTs that avoids repeated `sertop` queries.
    """
    constr_cache: Dict[str,
                       str] = default_field({})
    """
    A cache of TBD that avoids repeated `sertop` queries.
    """
    _dead: bool = field(default=False, init=False)
    """
    The status of the connection to the `sertop` child process.
    """
    _proc: PopenSpawn = field(init=False)

    def __post_init__(self, timeout: int):
        """
        Initialize the SerAPI subprocess.
        """
        try:
            self._proc = PopenSpawn(
                "sertop --implicit --print0",
                encoding="utf-8",
                timeout=timeout,
                maxread=10000000,
            )
        except FileNotFoundError:
            logger.log(
                logging.ERROR,
                'Please make sure the "sertop" program is in the PATH.\n'
                'You may have to run "eval $(opam env)".')
            sys.exit(1)
        self._proc.expect_exact(
            "(Feedback((doc_id 0)(span_id 1)(route 0)(contents Processed)))\0")
        self.send("Noop")

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

        # initialize the stack
        self.push()

    def __enter__(self) -> 'SerAPI':
        """
        Initialize a context encompassing a SerAPI session.

        Returns
        -------
        _type_
            _description_
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
        Return whether the interpreter is in proof model.

        Property alias for `has_open_goals`.
        """
        if self.is_dead:
            return False
        else:
            return self.has_open_goals()

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

    def cancel(self, states: Iterable[int]) -> None:
        """
        Cancel the indicated commands.

        Parameters
        ----------
        states : Iterable[int]
            The IDs of previously submitted commands.
        """
        self.send(f"(Cancel ({' '.join([str(s) for s in states])}))")

    def execute(
        self,
        cmd: str,
        return_ast: bool = False
    ) -> Union[List[SexpNode],
               Tuple[List[SexpNode],
                     List[str],
                     Optional[str]]]:
        """
        Execute a command.

        Parameters
        ----------
        cmd : str
            A command (i.e., a sentence).
        return_ast : bool, optional
            Whether to return the AST of the command or not, by default
            False.

        Returns
        -------
        responses : List[SexpNode]
            The response from SerAPI after execution of the command.
        feedback : List[str]
            Feedback from the Coq Proof Assistant to the executed
            command.
        ast : str, optional
            If `return_ast` is True, then the AST of `cmd` is also
            returned.
        """
        state_id, ast = self.send_add(cmd, return_ast)
        responses, feedback, _ = self.send(f"(Exec {state_id})")
        if return_ast:
            return responses, feedback, ast.pretty_format() if ast is not None else ast
        else:
            return responses, feedback

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
        popped_frames = []
        for _ in range(n):
            popped_frames.append(self.frame_stack[-1].pop())
        self.cancel(popped_frames)
        if not self.frame_stack:
            # re-initialize the stack
            self.push()

    def print_constr(self, sexp_str: str) -> str:
        """
        _summary_

        _extended_summary_

        Parameters
        ----------
        sexp_str : str
            _description_

        Returns
        -------
        str
            _description_

        Raises
        ------
        CoqExn
            _description_
        TypeError
            _description_
        """
        if sexp_str not in self.constr_cache:
            try:
                responses, _, _ = self.send(
                    f"(Print ((pp_format PpStr)) (CoqConstr {sexp_str}))"
                )
                self.constr_cache[sexp_str] = normalize_spaces(
                    str(responses[1][2][1][0][1]))
            except CoqExn as ex:
                if ex.err_msg == "Not_found":
                    return None
                else:
                    raise ex
            except TypeError:
                self.constr_cache[sexp_str] = normalize_spaces(
                    str(responses[0][2][1][0][1]))
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

    def query_ast(self, cmd: str) -> AbstractSyntaxTree:
        """
        Query the AST of the given Vernacular command.

        Parameters
        ----------
        cmd : str
            A Vernacular command.

        Returns
        -------
        AbstractSyntaxTree
            The AST for the given command.
        """
        responses, _, _ = self.send(f'(Parse () "{escape(cmd)}")')
        ast = responses[1][2][1][0]
        assert ast[0] == SexpString("CoqAst")
        return ast

    def query_env(
            self,
            current_file: os.PathLike) -> Tuple[List[Constant],
                                                List[Inductive]]:
        """
        Query the global environment.
        """
        responses, _, _ = self.send("(Query () Env)")
        env = responses[1][2][1][0]

        # store the constants
        constants = []
        for const in env[1][0][1][0][1]:
            # identifier
            qualid = (
                print_mod_path(const[0][1]) + "." + ".".join(
                    [str(x[1])
                     for x in const[0][2][1][::-1]] + [str(const[0][3][1])]))
            if qualid.startswith("SerTop."):
                logical_path = "SerTop"
                physical_path = current_file
            else:
                logical_path = mod_path_file(const[0][1])
                assert qualid.startswith(logical_path)
                physical_path = os.path.relpath(
                    self.query_library(logical_path))
            physical_path += ":" + qualid[len(logical_path) + 1 :]
            short_ident = self.query_qualid(qualid)
            # term
            assert const[1][0][1][0] == SexpString("const_body")
            if const[1][0][1][1][0] == SexpString("Undef"):  # delaration
                opaque = None
                term = None
            elif const[1][0][1][1][0] == SexpString(
                    "Def"):  # transparent definition
                opaque = False
                term = None
            else:
                assert const[1][0][1][1][0] == SexpString(
                    "OpaqueDef")  # opaque definition
                opaque = True
                term = None
            # type
            assert const[1][0][2][0] == SexpString("const_type")
            type_sexp = const[1][0][2][1].pretty_format()
            type = self.print_constr(type_sexp)
            sort = self.query_type(type_sexp, return_str=True)
            constants.append(
                Constant(
                    physical_path=physical_path,
                    short_ident=short_ident,
                    qualid=qualid,
                    term=term,
                    type=type,
                    sort=sort,
                    opaque=opaque,
                    sexp=const[1][0][2][1].pretty_format(),
                ))

        # store the inductives
        inductives = []
        for induct in env[1][0][1][1][1]:
            # identifier
            qualid = (
                print_mod_path(induct[0][1]) + "." + ".".join(
                    [str(x[1])
                     for x in induct[0][2][1][::-1]] + [str(induct[0][3][1])]))
            short_ident = self.query_qualid(qualid)
            if qualid.startswith("SerTop."):
                logical_path = "SerTop"
                physical_path = current_file
            else:
                logical_path = mod_path_file(induct[0][1])
                physical_path = os.path.relpath(
                    self.query_library(logical_path))
            assert qualid.startswith(logical_path)
            physical_path += ":" + qualid[len(logical_path) + 1 :]
            # blocks
            blocks = []
            for blk in induct[1][0][0][1]:
                blk_qualid = ".".join(
                    qualid.split(".")[:-1] + [str(blk[0][1][1])])
                blk_short_ident = self.query_qualid(blk_qualid)
                # constructors
                constructors = []
                for c_name, c_type in zip(blk[3][1], blk[4][1]):
                    c_name = str(c_name[1])
                    c_type = self.print_constr(c_type.pretty_format())
                    # if c_type is not None:
                    #    c_type = UNBOUND_REL_PATTERN.sub(short_ident, c_type)
                    constructors.append((c_name, c_type))
                blocks.append(
                    Block(
                        short_ident=blk_short_ident,
                        qualid=blk_qualid,
                        constructors=constructors,
                    ))
            inductives.append(
                Inductive(
                    physical_path=physical_path,
                    blocks=blocks,
                    is_record=induct[1][0][1][1] != SexpString("NotRecord"),
                    sexp=induct.pretty_format(),
                ))

        return constants, inductives

    def query_goals(
            self) -> Tuple[List[Goal],
                           List[Goal],
                           List[Goal],
                           List[Goal]]:
        """
        Retrieve a list of open goals.

        Returns
        -------
        fg_goals : List[Goal]
            A list of foreground goals.
        bg_goals : List[Goal]
            A list of background goals.
        shelved_goals : List[Goal]
            A list of shelved goals.
        abandoned_goals : List[Goal]
            A list of abandoned goals.
        """
        responses, _, _ = self.send("(Query () Goals)")
        assert responses[1][2][0] == SexpString("ObjList")
        if responses[1][2][1] == []:  # no goals
            return [], [], [], []
        else:
            assert len(responses[1][2][1]) == 1

            def store_goals(goals_sexp: SexpNode) -> List[Goal]:
                goals = []
                for g in goals_sexp:
                    hypotheses = []
                    for h in g[2][1]:
                        h_sexp = h[2].pretty_format()
                        hypotheses.append(
                            Hypothesis(
                                idents=[str(ident[1]) for ident in h[0][::-1]],
                                term=[
                                    None if t == [] else self.print_constr(
                                        t.pretty_format()) for t in h[1]
                                ],
                                type=self.print_constr(h_sexp),
                                sexp=h_sexp,
                            ))

                    type_sexp = g[1][1].pretty_format()
                    goals.append(
                        Goal(
                            id=int(g[0][1]),
                            type=self.print_constr(type_sexp),
                            sexp=type_sexp,
                            hypotheses=hypotheses[::-1],
                        ))
                return goals

            fg_goals = store_goals(responses[1][2][1][0][1][0][1])
            bg_goals = store_goals(
                list(
                    chain.from_iterable(
                        chain.from_iterable(responses[1][2][1][0][1][1][1]))))
            shelved_goals = store_goals(responses[1][2][1][0][1][2][1])
            abandoned_goals = store_goals(responses[1][2][1][0][1][3][1])
            return fg_goals, bg_goals, shelved_goals, abandoned_goals

    def query_library(self, lib: str) -> str:
        """
        Retrieve the physical path of a specified library.

        Parameters
        ----------
        lib : str
            The logical name of a library.

        Returns
        -------
        str
            The physical path bound to `lib`.
        """
        responses, _, _ = self.send(f'(Query () (LocateLibrary "{lib}"))')
        physical_path = str(responses[1][2][1][0][3])
        return physical_path

    def query_qualid(self, qualid: str) -> str:
        """
        _summary_

        _extended_summary_

        Parameters
        ----------
        qualid : str
            _description_

        Returns
        -------
        str
            _description_
        """
        responses, _, _ = self.send(f'(Query () (Locate "{qualid}"))')
        if responses[1][2][1] == [] and qualid.startswith("SerTop."):
            qualid = qualid[len("SerTop."):]
            responses, _, _ = self.send(f'(Query () (Locate "{qualid}"))')
        assert len(responses[1][2][1]) == 1
        short_responses = responses[1][2][1][0][1][0][1]
        assert short_responses[1][0] == SexpString("DirPath")
        short_ident = ".".join(
            [str(x[1]) for x in short_responses[1][1][::-1]]
            + [str(short_responses[2][1])])
        return short_ident

    def query_type(self,
                   term_sexp: str,
                   return_str: bool = False) -> Optional[Union[str,
                                                               SexpNode]]:
        """
        Get the type of the given expression.

        Parameters
        ----------
        term_sexp : str
            A serialized Coq expression.
        return_str : bool, optional
            Whether to return the type as a str, by default False

        Returns
        -------
        Optional[Union[str, SexpNode]]
            The type of the given term or None if the term has no type.

        Raises
        ------
        CoqExn
            If an error is encountered when evaluating the given term.
        """
        try:
            responses, _, _ = self.send(f"(Query () (Type {term_sexp}))")
        except CoqExn as ex:
            if ex.err_msg == "Not_found":
                return None
            else:
                raise ex
        assert responses[1][2][1][0][0] == SexpString("CoqConstr")
        type_sexp = responses[1][2][1][0][1]
        if return_str:
            return self.print_constr(type_sexp.pretty_format())
        else:
            return type_sexp

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
            A Coq command.

        Returns
        -------
        _type_
            _description_

        Raises
        ------
        CoqTimeout
            _description_
        CoqExn
            _description_
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
                ])
        except pexpect.TIMEOUT:
            print(self._proc.before)
            raise CoqTimeout
        raw_responses = self._proc.after
        ack_num = int(
            re.search(r"^\(Answer (?P<num>\d+)",
                      raw_responses)["num"])
        for num in re.findall(r"(?<=\(Answer) \d+", raw_responses):
            assert int(num) == ack_num
        responses = []
        feedback = []
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
                assert parsed_item[2][0] == SexpString("CoqExn")
                raise CoqExn(
                    parsed_item[2][1][5][1].pretty_format(),
                    str(parsed_item[2]))
            if item.startswith("(Feedback"):
                try:
                    msg = parsed_item[1][3][1]
                    if (msg.is_list() and msg != []
                            and msg[0] == SexpString("Message")):
                        assert msg[4][1].is_string()
                        feedback.append(msg[4][1].get_content())
                except IndexError:
                    pass
                continue
            responses.append(parsed_item)
        return responses, feedback, raw_responses

    def send_add(self,
                 cmd: str,
                 return_ast: bool) -> Tuple[int,
                                            Optional[AbstractSyntaxTree]]:
        """
        Add a command to the SerAPI buffer and optionally get its AST.

        Parameters
        ----------
        cmd : str
            A command (i.e., a sentence).
        return_ast : bool
            Whether to return the AST or not.

        Returns
        -------
        state_id : int
            The ID of the added command.
        ast : Optional[AbstractSyntaxTree]
            The AST of the added command or None if `return_ast` is
            False.
        """
        _, _, raw_responses = self.send(f'(Add () "{escape(cmd)}")')
        state_ids = [
            int(sid) for sid in ADDED_STATE_PATTERN.findall(raw_responses)
        ]
        state_id = state_ids[-1]
        if self.frame_stack != []:
            self.frame_stack[-1].append(state_id)
        if return_ast:
            if cmd not in self.ast_cache:
                self.ast_cache[cmd] = self.query_ast(cmd)
            ast = self.ast_cache[cmd]
        else:
            ast = None
        return state_id, ast

    def shutdown(self) -> None:
        """
        Terminate the interactive session.

        This cannot be undone.
        """
        self._proc.sendeof()
        # pexpect doesn't close everything it should
        self._proc.proc.stdout.close()
        try:
            self._proc.kill(signal.SIGKILL)
        except ProcessLookupError:
            pass
        self._proc.wait()
        self._dead = True
        self._dead = True
