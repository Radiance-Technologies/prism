"""
Module supporting extraction of command arguments using strace.

Adapted from IBM's pycoq: https://github.com/IBM/pycoq
"""
import argparse
import ast
import logging
import os
import pathlib
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

import lark
from strace_parser.parser import get_parser

from prism.util.path import get_relative_path

_EXECUTABLE = 'coqc'
_REGEX = r'.*\.v$'


@dataclass
class ProcContext:
    """
    Process context data class.
    """

    executable: str = ''
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)


@dataclass
class IQR:
    """
    Dataclass for storing IQR arguments.

    See https://coq.inria.fr/refman/practical-tools/coq-commands.html
    for more information.
    """

    I: Set[str]  # noqa: E741
    Q: Set[Tuple[str, str]]  # set of pairs of str
    R: Set[Tuple[str, str]]  # set of pairs of str
    pwd: os.PathLike = ""
    """
    The working directory to which all of the options are assumed to be
    relative.
    """
    delim: str = ","
    """
    The delimiter used between relative and logical paths, by default a
    comma for compatibility with SerAPI.
    A space should be used for compatibility with Coq.
    """

    def __or__(self, other: 'IQR') -> 'IQR':  # noqa: D105
        if not isinstance(other, IQR):
            return NotImplemented
        self_pwd = pathlib.Path(self.pwd).absolute()
        other_pwd = pathlib.Path(other.pwd).absolute()
        if self_pwd != other_pwd:
            pwd = os.path.commonpath([self_pwd, other_pwd])
            return self.relocate(pwd) | other.relocate(pwd)
        else:
            return IQR(
                self.I | other.I,
                self.Q | other.Q,
                self.R | other.R,
                self.pwd,
                self.delim)

    def __str__(self) -> str:
        """
        Get the options as they would appear on the command line.
        """
        options = [f"-I {i}" for i in self.I]
        options.extend([f"-Q {p}{self.delim}{q}" for p, q in self.Q])
        options.extend([f"-R {p}{self.delim}{r}" for p, r in self.R])
        return " ".join(options)

    def union(self, other: 'IQR') -> 'IQR':
        """
        Compute the union of two IQR configurations.

        If the configurations do not share the same working directory,
        then the working directory of their union will be the longest
        common path shared between their working directories.
        """
        return self | other

    def relocate(self, pwd: os.PathLike) -> 'IQR':
        """
        Reinterpret the IQR arguments relative to another path.

        Parameters
        ----------
        pwd : os.PathLike, optional
            The path relative to which the IQR options should be
            reinterpreted, by default "".

        Returns
        -------
        str
            The reinterpreted arguments.
        """
        prefix = get_relative_path(self.pwd, pwd)
        return IQR(
            {str(prefix / i) for i in self.I},
            {(str(prefix / p),
              q) for p,
             q in self.Q},
            {(str(prefix / p),
              r) for p,
             r in self.R},
            pwd,
            self.delim)

    @classmethod
    def extract_iqr(cls, args: List[str], pwd: os.PathLike = "") -> 'IQR':
        """
        Extract IQR args from command args; return as IQR dataclass.

        Parameters
        ----------
        args : List[str]
            A list of string arguments associated with a command.
        pwd : os.PathLike, optional
            The directory in which the command was executed, by default
            an empty string.

        Returns
        -------
        IQR
            Args processed into IQR dataclass
        """
        parser = argparse.ArgumentParser()
        parser.add_argument(
            '-I',
            metavar=('dir'),
            nargs=1,
            action='append',
            default=[],
            help='append filesystem to ML load path')

        parser.add_argument(
            '-Q',
            metavar=('dir',
                     'coqdir'),
            nargs=2,
            action='append',
            default=[],
            help='append filesystem dir mapped to coqdir to coq load path')

        parser.add_argument(
            '-R',
            metavar=('dir',
                     'coqdir'),
            nargs=2,
            action='append',
            default=[],
            help='recursively append filesystem dir mapped '
            'to coqdir to coq load path')
        args, _ = parser.parse_known_args(args)

        return cls(
            I=set(args.I),
            Q={tuple(i) for i in args.Q},
            R={tuple(i) for i in args.R},
            pwd=pwd)


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
    iqr: IQR = field(init=False)
    """
    The IQR options contained in the given `args`.
    """

    def __post_init__(self):
        """
        Grab the internal IQR args, if any.
        """
        self.iqr = IQR.extract_iqr(self.args, self.pwd)

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
                    regex: str,
                    source='') -> List[CoqContext]:
    """
    Write a CoqContext record for each executable arg matching regex.

    Creates and writes to a file a pycoq_context record for each
    argument matching regex in a call of executable.
    """
    record = _parse_strace_line(parser, line)
    p_context = ProcContext(
        executable=record[0],
        args=record[1],
        env=_dict_of_list(record[2]))
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
        try:
            temp = 'b' + s
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
        return [_dehex(e) for e in d]
    elif isinstance(d, dict):
        return {k: _dehex(v) for k,
                v in d.items()}


def _parse_strace_line(parser: lark.Lark, line: str) -> str:
    """
    Parse a line of the strace output.
    """

    def _conv(a):
        if isinstance(a, lark.tree.Tree) and a.data == 'other':
            return _conv(a.children[0])
        elif isinstance(a, lark.tree.Tree) and a.data == 'bracketed':
            return [_conv(c) for c in a.children[0].children]
        elif isinstance(a, lark.tree.Tree) and a.data == 'args':
            return [_conv(c) for c in a.children]
        elif isinstance(a, lark.lexer.Token):
            return str(_dehex(a))
        else:
            raise ValueError(f"'can't parse lark object {a}")

    p = parser.parse(line)
    if (p.data == 'start' and len(p.children) == 1
            and p.children[0].data == 'line'):
        _, body = p.children[0].children
        if (len(body.children) == 1 and body.children[0].data == 'syscall'):
            syscall = body.children[0]
            name, args, _ = syscall.children
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
                    res += _record_context(line, parser, regex, log_file)
    return res


def strace_build(
        command: str,
        executable: str = _EXECUTABLE,
        regex: str = _REGEX,
        workdir: Optional[str] = None,
        strace_logdir: Optional[str] = None,
        **kwargs) -> List[CoqContext]:
    """
    Trace calls of executable using regex.

    Trace calls of executable during access to files that match regex in
    workdir while executing the command and returns the list CoqContext
    objects.

    Parameters
    ----------
    command : str
        The command to run using ``strace``.
    executable : str
        The executable to watch for while `command` is running.
    regex : str
        The pattern to search for while `command` is running that
        identifies the target of the executable.
    workdir : Optional[str]
        The cwd to execute the `command` in, by default None.
    strace_logdir : Optional[str]
        The directory in which to store the temporary strace logs.
    kwargs : Dict[str, Any]
        Additional keyword arguments to `subprocess.run`.

    Returns
    -------
    List[CoqContext]
        These `CoqContext` objects contain the information gleaned from
        strace. If there are any IQR args present, they will be within
        these objects.
    """

    def _strace_build(
            executable: str,
            regex: str,
            workdir: str,
            command: str,
            logdir: str):
        logfname = os.path.join(logdir, 'strace.log')
        logging.info(
            f"pycoq: tracing {executable} accessing {regex} while "
            f"executing {command} from {workdir} with "
            f"curdir {os.getcwd()}")
        strace_cmd = (
            'strace -e trace=execve -v -ff -s 100000000 -xx -ttt -o'
            f' {logfname} {command}')
        r = subprocess.run(strace_cmd, cwd=workdir, shell=True, **kwargs)
        if r.stdout is not None:
            for line in iter(str(r.stdout).splitlines, ''):
                logging.debug(f"strace stdout: {line}")
        logging.info('strace finished')
        return _parse_strace_logdir(logdir, executable, regex)

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
