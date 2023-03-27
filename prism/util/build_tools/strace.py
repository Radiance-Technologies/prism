"""
Module supporting extraction of command arguments using strace.

Adapted from IBM's pycoq: https://github.com/IBM/pycoq
"""
import ast
import logging
import os
import pathlib
import re
import shutil
import stat
import tempfile
import typing
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import lark
from strace_parser.parser import get_parser

from prism.interface.coq.options import SerAPIOptions
from prism.util.bash import escape
from prism.util.opam.switch import OpamSwitch
from prism.util.radpytools import PathLike

_EXECUTABLE = 'coqc'
_REGEX = r'.*\.v$'

_DUMMY_COQC_PARENT_PATH = tempfile.TemporaryDirectory()
_DUMMY_COQC_PATH = pathlib.Path(_DUMMY_COQC_PARENT_PATH.name) / "coqc"
_DUMMY_COQC_SH_PATH = pathlib.Path(__file__).parent / "dummy_coqc.sh"

shutil.copy(_DUMMY_COQC_SH_PATH, _DUMMY_COQC_PATH)

os.chmod(_DUMMY_COQC_PATH, stat.S_IRWXO | stat.S_IRWXG | stat.S_IRWXU)

RecursiveStrList = Union[str, List['RecursiveStrList']]


@dataclass
class ProcContext:
    """
    Process context data class.
    """

    executable: str = ''
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)


@dataclass
class CoqContext:
    """
    A class that captures the context of a Coq executable invocation.
    """

    pwd: str
    """
    The working directory at the time of the invocation.
    """
    executable: str
    """
    The name of the Coq executable.
    """
    target: str
    """
    A target of the Coq executable, e.g., a Coq source file.
    """
    args: List[str] = field(default_factory=list)
    """
    The arguments of the executable (which implicitly includes the
    target).
    """
    env: Dict[str, str] = field(default_factory=dict)
    """
    The environment variables at the time of the invocation (which
    implicitly contains the working directory).
    """
    serapi_options: SerAPIOptions = field(init=False)
    """
    The Coq compiler options contained in the given `args`.
    """

    def __post_init__(self):
        """
        Grab the internal Coq compiler args, if any.
        """
        self.serapi_options = SerAPIOptions.parse_args(self.args, self.pwd)

    def __str__(self) -> str:
        """
        Return a string representation of the original command.
        """
        args = [f'{nm}={val}' for nm, val in self.env.items()]
        args.append(self.executable)
        args.extend(self.args)
        return " ".join(args)

    @classmethod
    def empty_context(cls) -> 'CoqContext':
        """
        Return an empty `CoqContext`.
        """
        return cls("", "", "", [])


def _dict_of_list(el: Sequence[str], split: str = '=') -> Dict[str, str]:
    """
    Transform a list of strings to dict.

    The split string delineates which part of the string should be the
    key and which should be the value.

    Parameters
    ----------
    el : Sequence of str
        Input sequence of the form ["foo1=bar", "foo2=baz"]
    split : str, optional
        Character to split on, by default '='

    Returns
    -------
    Dict[str, str]
        Dictionary of the form {"foo1": "bar", "foo2": "baz"}
    """
    d = {}
    for e in el:
        assert isinstance(e, str)
        pos = e.find(split)
        assert pos > 0
        d[e[: pos]] = e[pos + 1 :]
    return d


def _record_context(line: str,
                    parser: lark.Lark,
                    regex: str) -> List[CoqContext]:
    """
    Write a CoqContext record for each executable arg matching regex.

    Creates and writes to a file a pycoq_context record for each
    argument matching regex in a call of executable.
    """
    record = typing.cast(
        List[RecursiveStrList],
        _parse_strace_line(parser,
                           line))
    executable = record[0]
    args = record[1]
    env = record[2]
    assert isinstance(executable, str)
    assert isinstance(args, list)
    assert isinstance(env, list)
    p_context = ProcContext(
        executable=executable,
        args=typing.cast(List[str],
                         args),
        env=_dict_of_list(typing.cast(List[str],
                                      env)))
    res = []
    for target in p_context.args:
        if re.compile(regex).fullmatch(target):
            pwd = p_context.env['PWD']
            coq_context = CoqContext(
                pwd=pwd,
                executable=p_context.executable,
                target=target,
                args=p_context.args,
                env=p_context.env)
            res.append(coq_context)
    return res


def _hex_rep(b: str) -> str:
    """
    Return a hex representation of the given string.

    Parameters
    ----------
    b : str
        String to represent in hex

    Returns
    -------
    str
        Hex representation of input string

    Raises
    ------
    ValueError
        If input is not string
    """
    if isinstance(b, str):
        return "".join(['\\' + hex(c)[1 :] for c in b.encode('utf8')])
    else:
        raise ValueError('in hex_rep on ' + str(b))


def _dehex_str(s: str) -> str:
    """
    Decode hex represnetation of string into the original string.

    Parameters
    ----------
    s : str
        Hex representation of string

    Returns
    -------
    str
        Original string
    """
    if len(s) > 2 and s[0] == '"' and s[-1] == '"':
        temp = 'b' + s
        try:
            return ast.literal_eval(temp).decode('utf8')
        except Exception as exc:
            print("pycoq: ERROR DECODING", temp)
            raise exc
    else:
        return s


def _dehex(
    d: Union[str,
             List[str],
             Dict[Any,
                  str]]
) -> Union[str,
           List[str],
           Dict[Any,
                str]]:
    """
    Undo hex representation for str, list of str, or dict of str.

    Parameters
    ----------
    d : Union[str, List[str], Dict[Any, str]]
        Input, hexified string (or collection thereof)

    Returns
    -------
    Union[str, List[str], Dict[Any, str]]
        Output dehexified string (or collection thereof)
    """
    if isinstance(d, str):
        return _dehex_str(d)
    elif isinstance(d, list):
        return [typing.cast(str, _dehex(e)) for e in d]
    elif isinstance(d, dict):
        return {k: typing.cast(str,
                               _dehex(v)) for k,
                v in d.items()}


def _parse_strace_line(parser: lark.Lark, line: str) -> RecursiveStrList:
    """
    Parse a line of the strace output.
    """

    def _conv(a: Union[str, lark.Tree, lark.Token]) -> RecursiveStrList:
        if isinstance(a, lark.tree.Tree) and a.data == 'other':
            return _conv(a.children[0])
        elif isinstance(a, lark.tree.Tree) and a.data == 'bracketed':
            child = a.children[0]
            assert isinstance(child, lark.Tree)
            return [_conv(c) for c in child.children]
        elif isinstance(a, lark.tree.Tree) and a.data == 'args':
            return [_conv(c) for c in a.children]
        elif isinstance(a, lark.lexer.Token):
            return str(_dehex(a))
        else:
            raise ValueError(f"'can't parse lark object {a}")

    p = parser.parse(line)
    if (p.data == 'start' and len(p.children) == 1 and isinstance(p.children[0],
                                                                  lark.Tree)
            and p.children[0].data == 'line'):
        _, body = p.children[0].children
        if (isinstance(body, lark.Tree) and len(body.children) == 1):
            syscall = body.children[0]
            if (isinstance(syscall, lark.Tree) and syscall.data == 'syscall'):
                name, args, _ = syscall.children
                if isinstance(name, lark.Tree):
                    name = str(name.children[0])
                    return _conv(args)

    raise ValueError(f"can't parse lark object {p}")


def _parse_strace_logdir(logdir: str,
                         executable: str,
                         regex: str) -> List[CoqContext]:
    """
    Parse the strace log directory.

    For each strace log file in logdir, for each strace record in log
    file, parse the record matching to executable calling regex and save
    the call information _pycoq_context
    """
    logging.info(
        f"pycoq: parsing strace log "
        f"execve({executable}) and recording "
        f"arguments that match {regex} in cwd {os.getcwd()}")
    parser = get_parser()
    res = []
    for logfname_pid in os.listdir(logdir):
        with open(os.path.join(logdir, logfname_pid), 'r') as log_file:
            for line in iter(log_file.readline, ''):
                if line.find(_hex_rep(executable)) != -1:
                    logging.info(f"from {logdir} from {log_file} parsing..")
                    res += _record_context(line, parser, regex)
    return res


def strace_build(
        opam_switch: OpamSwitch,
        command: str,
        executable: str = _EXECUTABLE,
        regex: str = _REGEX,
        workdir: Optional[PathLike] = None,
        strace_logdir: Optional[PathLike] = None,
        use_dummy_coqc: Optional[bool] = False,
        **kwargs) -> Tuple[List[CoqContext],
                           int,
                           str,
                           str]:
    """
    Trace calls of executable using regex.

    Trace calls of executable during access to files that match regex in
    workdir while executing the command and returns the list CoqContext
    objects.

    Parameters
    ----------
    opam_switch : OpamSwitch
        The switch in which to execute the build process.
    command : str
        The command to run using ``strace``.
    executable : str, optional
        The executable to watch for while `command` is running.
    regex : str, optional
        The pattern to search for while `command` is running that
        identifies the target of the executable.
    workdir : Optional[PathLike], optional
        The cwd to execute the `command` in, by default None.
    strace_logdir : Optional[PathLike], optional
        The directory in which to store the temporary strace logs.
    use_dummy_coqc : Optional[bool]
        Attempt to use a stub coqc that doesn't actually
        build anything.
    kwargs : Dict[str, Any]
        Additional keyword arguments to `OpamSwitch.run`.

    Returns
    -------
    List[CoqContext]
        These `CoqContext` objects contain the information gleaned from
        strace. If there are any Coq args present, they will be within
        these objects.
    int
        The return code of the strace command
    str
        The stdout of the strace command
    str
        The stderr of the strace command
    """

    def _strace_build(
            executable: str,
            regex: str,
            workdir: Optional[PathLike],
            command: str,
            logdir: str) -> Tuple[List[CoqContext],
                                  int,
                                  str,
                                  str]:
        logfname = os.path.join(logdir, 'strace.log')
        logging.info(
            f"pycoq: tracing {executable} accessing {regex} while "
            f"executing '{command}' from {workdir} with "
            f"curdir {os.getcwd()}")
        command = escape(command)
        strace_cmd = (
            'strace -e trace=execve -v -ff -s 100000000 -xx -ttt -o'
            f' {logfname} bash -c "{command}"')

        if use_dummy_coqc:
            strace_cmd = (
                f'(\n export PATH={_DUMMY_COQC_PARENT_PATH.name}:$PATH; '
                + strace_cmd + "\n)")

        r = opam_switch.run(strace_cmd, cwd=workdir, **kwargs)
        if r.stdout is not None:
            for line in r.stdout.splitlines():
                logging.debug(f"strace stdout: {line}")
        logging.info('strace finished')
        return (
            _parse_strace_logdir(logdir,
                                 executable,
                                 regex),
            r.returncode,
            str(r.stdout),
            str(r.stderr))

    if strace_logdir is None:
        with tempfile.TemporaryDirectory() as _logdir:
            return _strace_build(executable, regex, workdir, command, _logdir)
    else:
        os.makedirs(strace_logdir, exist_ok=True)
        strace_logdir_cur = tempfile.mkdtemp(dir=strace_logdir)
        return _strace_build(
            executable,
            regex,
            workdir,
            command,
            strace_logdir_cur)
