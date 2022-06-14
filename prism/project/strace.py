"""
Module supporting extraction of command arguments using strace.

Adapted from IBM's pycoq: https://github.com/IBM/pycoq
"""
import argparse
import ast
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Union

import lark
from dataclasses_json import dataclass_json
from strace_parser.parser import get_parser

CONTEXT_EXT = '._pycoq_context'


@dataclass
class ProcContext():
    """
    Process context data class.
    """

    executable: str = ''
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)


@dataclass
class IQR():
    """
    Dataclass for storing IQR arguments.
    """

    I = List[str]  # noqa: E741
    Q = List[List[str]]  # List of pairs of str
    R = List[List[str]]  # List of pairs of str


@dataclass_json
@dataclass
class CoqContext:
    """
    Coq context class.
    """

    pwd: str
    executable: str
    target: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)

    def IQR(self) -> IQR:
        """
        Process IQR command args and return in IQR dataclass form.

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
        args, _ = parser.parse_known_args(self.args)

        return IQR(I=args.I, Q=args.Q, R=args.R)


def dict_of_list(el: Sequence[str], split: str = '=') -> Dict[str, str]:
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


def context_fname(target_fname: str) -> str:
    """
    Return context filename with proper extension.

    Parameters
    ----------
    target_fname : str
        Target filename without the extension

    Returns
    -------
    str
        Target filename with extension
    """
    return target_fname + CONTEXT_EXT


def dump_context(fname: str, coq_context: CoqContext) -> str:
    """
    Return fname of dumped coq_context.
    """
    with open(fname, 'w') as fout:
        logging.info(f'dump_context: recording context to {fname}')
        fout.write(coq_context.to_json())
        return (fname)


def record_context(line: str, parser: lark.Lark, regex: str, source=''):
    """
    Write a CoqContext record for each executable arg matching regex.

    creates and writes to a file a pycoq_context record for each
    argument matching regex in a call of executable
    """
    record = parse_strace_line(parser, line)
    p_context = ProcContext(
        executable=record[0],
        args=record[1],
        env=dict_of_list(record[2]))
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
            target_fname = os.path.join(pwd, target)
            res.append(dump_context(context_fname(target_fname), coq_context))
            logging.info(
                f"from {source} recorded context to"
                f" {context_fname(target_fname)}")
    return res


def hex_rep(b: str) -> str:
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


def dehex_str(s: str) -> str:
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


def dehex(
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
        return dehex_str(d)
    elif isinstance(d, list):
        return [dehex(e) for e in d]
    elif isinstance(d, dict):
        return {k: dehex(v) for k,
                v in d.items()}


def parse_strace_line(parser: lark.Lark, line: str) -> str:
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
            return str(dehex(a))
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


def parse_strace_logdir(logdir: str, executable: str, regex: str) -> List[str]:
    """
    Parse the strace log directory.

    For each strace log file in logdir, for each strace record in log
    file, parse the record matching to executable calling regex and save
    the call information _pycoq_context
    """
    logging.info(
        f"pycoq: parsing strace log "
        f"execve({executable}) and recording"
        f"arguments that match {regex} in cwd {os.getcwd()}")
    parser = get_parser()
    res = []
    for logfname_pid in os.listdir(logdir):
        with open(os.path.join(logdir, logfname_pid), 'r') as log_file:
            for line in iter(log_file.readline, ''):
                if line.find(hex_rep(executable)) != -1:
                    logging.info(f"from {logdir} from {log_file} parsing..")
                    res += record_context(line, parser, regex, log_file)
    return res


def strace_build(
        executable: str,
        regex: str,
        workdir: Optional[str],
        command: List[str],
        strace_logdir=None) -> List[str]:
    """
    Trace calls of executable using regex.

    trace calls of executable during access to files that match regex in
    workdir while executing the command and returns the list of
    pycoq_context file names
    """

    def _strace_build(executable, regex, workdir, command, logdir):
        logfname = os.path.join(logdir, 'strace.log')
        logging.info(
            f"pycoq: tracing {executable} accesing {regex} while "
            f"executing {command} from {workdir} with "
            f"curdir {os.getcwd()}")
        with subprocess.Popen(['strace',
                               '-e',
                               'trace=execve',
                               '-v',
                               '-ff',
                               '-s',
                               '100000000',
                               '-xx',
                               '-ttt',
                               '-o',
                               logfname] + command,
                              cwd=workdir,
                              text=True,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE) as proc:
            for line in iter(proc.stdout.readline, ''):
                logging.debug(f"strace stdout: {line}")
            logging.info(
                f"strace stderr: {proc.stderr.read()}"
                "waiting strace to finish...")
            proc.wait()
        logging.info('strace finished')
        return parse_strace_logdir(logdir, executable, regex)

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
