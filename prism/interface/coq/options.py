"""
Defines an abstraction of Coq compiler options that are used by SerAPI.
"""
import abc
import argparse
import glob
import itertools
import re
import shlex
import typing
from dataclasses import dataclass
from enum import Enum, auto
from functools import reduce
from pathlib import Path
from typing import (
    Any,
    ClassVar,
    Dict,
    Generic,
    Iterable,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from prism.interface.coq.iqr import IQR
from prism.util.opam import OpamVersion, Version
from prism.util.radpytools import PathLike
from prism.util.re import regex_from_options
from prism.util.string import unquote


class SerAPIOptionException(Exception):
    """
    Raised when an invalid option is given to SerAPI.
    """

    pass


class CoqWarningState(Enum):
    """
    Enumeration of possible warning states.
    """

    DISABLED = auto()
    """
    The warning is disabled.
    """
    ENABLED = auto()
    """
    The warning is enabled.
    """
    ELEVATED = auto()
    """
    The warning is enabled and elevated to an error.
    """

    @property
    def prefix(self) -> str:
        """
        Format the state as a prefix to an implicit warning option.
        """
        if self == CoqWarningState.DISABLED:
            return '-'
        elif self == CoqWarningState.ELEVATED:
            return '+'
        else:
            return ''

    @classmethod
    def parse_state(cls, warning: str) -> 'CoqWarningState':
        """
        Parse the state from a formatted warning.
        """
        if warning.startswith('-'):
            return CoqWarningState.DISABLED
        elif warning.startswith('+'):
            return CoqWarningState.ELEVATED
        else:
            return CoqWarningState.ENABLED


@dataclass
class CoqWarning:
    """
    A Coq warning.
    """

    state: CoqWarningState
    """
    The state of the warning.
    """
    name: str
    """
    The name of the warning, e.g., ``"deprecated"``.
    """

    def __str__(self) -> str:
        """
        Format the warning as it would appear as a command-line option.
        """
        return ''.join([self.state.prefix, self.name])

    def as_command(self) -> str:
        """
        Get a Vernacular command for setting this warning.
        """
        return f'Set Warnings "{self}".'

    def serialize(self) -> str:
        """
        Serialize the warning to a string.
        """
        return str(self)

    @classmethod
    def deserialize(cls, data: str) -> 'CoqWarning':
        """
        Parse the warning from a string.
        """
        data = data.strip()
        state = CoqWarningState.parse_state(data)
        name = data
        if state != CoqWarningState.ENABLED:
            name = data[1 :]
        return CoqWarning(state, name)

    parse = deserialize


_T = TypeVar('_T')
_C = TypeVar('_C', bound='CoqSetting')


@dataclass
class CoqSetting(Generic[_T], abc.ABC):
    """
    A Coq flag, option, or table.

    See https://coq.inria.fr/refman/language/core/basic.html#flags-options-and-tables
    for more information about the distinction between each kind of
    setting.
    See https://coq.inria.fr/refman/coq-optindex.html for a complete
    list of settings.
    """  # noqa: W505

    name: str
    """
    The name of the flag, option, or table.
    """
    value: _T
    """
    The value of the flag, option or table.
    """

    def __hash__(self) -> int:  # noqa: D105
        return hash((self.name, self.value))

    @abc.abstractmethod
    def __str__(self) -> str:
        """
        Format the setting as it would appear as a command-line option.
        """
        ...

    @property
    def args(self) -> Tuple[_T, ...]:
        """
        The arguments (sans `name`) used to construct this setting.
        """
        return (self.value,)

    @abc.abstractmethod
    def as_command(self) -> str:
        """
        Get a Vernacular command for setting this flag, option or table.
        """
        ...

    @classmethod
    @abc.abstractmethod
    def _parse_command(cls: _C, command: str) -> _C:  # type: ignore
        """
        Deserialize by parsing a Vernacular command.
        """
        ...

    @classmethod
    @abc.abstractmethod
    def _parse_print_table(
            cls,
            setting_name: str,
            feedback: str) -> 'CoqSetting':
        """
        Parse a setting's value from the output of ``Print Table ...``.
        """
        ...

    @classmethod
    def from_args(cls,
                  name: str,
                  args: Tuple[_T,
                              ...]) -> List['CoqSetting[_T]']:
        """
        Construct one or more settings from given arguments.

        The arguments are presumed to have been obtained from `args`.
        """
        return [cls(name, a) for a in args]

    @classmethod
    def reduce_args(
            cls,
            former_args: Tuple[_T,
                               ...],
            latter_args: Tuple[_T,
                               ...]) -> Tuple[_T,
                                              ...]:
        """
        Reduce arguments, presumably for the same setting.
        """
        if latter_args:
            return latter_args[-1 :]
        elif former_args:
            return former_args[-1 :]
        else:
            return ()

    @classmethod
    def parse_command(cls: _C, command: str) -> _C:  # type: ignore
        """
        Deserialize by parsing a Vernacular command.
        """
        setting: Union[CoqFlag, CoqOption, CoqTable]
        try:
            setting = CoqOption._parse_command(command)
        except ValueError:
            try:
                setting = CoqTable._parse_command(command)
            except ValueError:
                setting = CoqFlag._parse_command(command)
        return typing.cast(_C, setting)

    @classmethod
    def parse_arg(cls, is_set: bool, arg: str) -> Union['CoqFlag', 'CoqOption']:
        """
        Parse a setting from a command-line argument.
        """
        arg = unquote(arg)
        args = arg.split('=', maxsplit=1)
        result: Union[CoqFlag, CoqOption]
        if len(args) == 1:
            result = CoqFlag(arg, is_set)
        else:
            result = CoqOption(args[0], args[1])
        return result

    @classmethod
    def parse_print_table(
            cls,
            setting_name: str,
            feedback: str) -> 'CoqSetting':
        """
        Parse a setting's value from the output of ``Print Table ...``.
        """
        if setting_name in CoqTable.known_tables:
            return CoqTable._parse_print_table(setting_name, feedback)
        else:
            return CoqOption._parse_print_table(setting_name, feedback)

    @classmethod
    def from_dict(
        cls,
        setting_states: Dict[str,
                             Tuple[Type['CoqSetting[Any]'],
                                   Tuple[Any,
                                         ...]]]
    ) -> List['CoqSetting[Any]']:
        """
        Construct settings from a map of their names and arguments.

        The (pseudo)inverse of `to_dict`.
        """
        settings = []
        for nm, (tp, args) in setting_states.items():
            settings.extend(tp.from_args(nm, args))
        return settings

    @classmethod
    def simplify(
            cls,
            settings: Iterable['CoqSetting[Any]']) -> List['CoqSetting[Any]']:
        """
        Remove redundant settings.

        A setting is redundant if a subsequent setting would replace it.
        """
        return cls.from_dict(cls.to_dict(settings))

    @classmethod
    def to_dict(
        cls,
        settings: Iterable['CoqSetting[Any]']
    ) -> Dict[str,
              Tuple[Type['CoqSetting[Any]'],
                    Tuple[Any,
                          ...]]]:
        """
        Convert a collection of settings to a dictionary.

        The dictionary effectively removes duplicates by choosing the
        *last* version of each setting encountered when iterating over
        the provided `settings`.

        Parameters
        ----------
        settings : Iterable[CoqSetting[Any]]
            An iterable container of settings.

        Returns
        -------
        Dict[str, Tuple[Type[CoqSetting[Any]], Tuple[Any, ...]]]
            A map from setting names to their type and arguments with
            which they can be reconstructed.
        """
        setting_states: Dict[str,
                             Tuple[Type['CoqSetting[Any]'],
                                   Tuple[Any,
                                         ...]]] = {}
        for s in settings:
            if s.name in setting_states:
                _, former_args = setting_states[s.name]
                clz = type(s)
                setting_states[s.name] = (
                    clz,
                    clz.reduce_args(former_args,
                                    s.args))
            else:
                setting_states[s.name] = (type(s), s.args)
        return setting_states


@dataclass(unsafe_hash=True)
class CoqFlag(CoqSetting[bool]):
    """
    A Boolean flag.
    """

    def __str__(self) -> str:
        """
        Format the flag as it would appear as a command-line option.
        """
        if self.value:
            result = f'-set "{self.name}"'
        else:
            result = f'-unset "{self.name}"'
        return result

    def as_command(self) -> str:
        """
        Get a Vernacular command for setting this flag.
        """
        if self.value:
            command = f'Set {self.name}.'
        else:
            command = f'Unset {self.name}.'
        return command

    @classmethod
    def _parse_command(cls, command: str) -> 'CoqFlag':  # noqa: D105
        error_msg = f"Syntax error when parsing flag from {command}"
        try:
            cmd, flag_name = command.split(maxsplit=1)
        except ValueError as e:
            raise ValueError(error_msg) from e
        if cmd == 'Set':
            flag = CoqFlag(flag_name, True)
        elif cmd == 'Unset':
            flag = CoqFlag(flag_name, False)
        else:
            raise ValueError(error_msg)
        return flag

    @classmethod
    def _parse_print_table(cls, flag_name: str, feedback: str) -> CoqSetting:
        return CoqOption._parse_print_table(flag_name, feedback)


@dataclass(unsafe_hash=True)
class CoqOption(CoqSetting[Optional[Union[int, str]]]):
    """
    An option set to a numeric or string value.
    """

    _print_table_regex: ClassVar[re.Pattern] = re.compile(
        r'^.*\s(?P<option_value>".*"|[^"]+)$',
        flags=re.DOTALL)
    """
    A simple regex for parsing the output of ``Print Table ...".

    The regex assumes the value always appears last (and may be quoted).
    """

    def __post_init__(self) -> None:
        """
        Convert string options to numeric (integral) if possible.
        """
        if self.value is not None and isinstance(self.value, str):
            value = unquote(self.value)
            try:
                value = int(value)
            except ValueError:
                pass
            self.value = value

    def __str__(self) -> str:
        """
        Format the option as it would appear as a command-line option.
        """
        value = self.value
        if isinstance(value, str):
            # escape double quotes for shell
            value = value.replace('"', r'\"')
        if value is not None:
            result = f'-set "{self.name}={value}"'
        else:
            result = ""
        return result

    def as_command(self) -> str:
        """
        Get a Vernacular command for setting this option.
        """
        value = self.value
        if value is None:
            # set to default
            command = f'Unset {self.name}.'
        else:
            command = f'Set {self.name} {self.value}.'
        return command

    @classmethod
    def _parse_command(cls, command: str) -> 'CoqOption':  # noqa: D105
        error_msg = f"Syntax error when parsing option from {command}"
        try:
            cmd, option_name = command.split(maxsplit=1)
        except ValueError as e:
            raise ValueError(error_msg) from e
        if cmd == 'Set':
            value: Union[int, str]
            try:
                option_name, value = option_name.rsplit(option_name, maxsplit=1)
            except ValueError as e:
                raise ValueError(error_msg) from e
            option = CoqOption(option_name, value)
        elif cmd == 'Unset':
            option = CoqOption(option_name, None)
        else:
            raise ValueError(error_msg)
        return option

    @classmethod
    def _parse_print_table(cls, option_name: str, feedback: str) -> CoqSetting:
        feedback = feedback.encode('utf-8').decode('unicode-escape')
        m = CoqOption._print_table_regex.match(feedback)
        if m is not None:
            value = m['option_value']
            if value in {'on',
                         'off'}:
                return CoqFlag(option_name, value == 'on')
            elif value == 'undefined':
                value = None
            else:
                value = value.encode('utf-8').decode('unicode_escape')
            return CoqOption(option_name, value)
        else:
            raise ValueError(f"Cannot parse option value from '{feedback}'")


@dataclass
class CoqTable(CoqSetting[Set[str]]):
    """
    A table containing a set of strings or qualids.
    """

    inclusive: bool
    """
    Whether this setting adds values to a table or removes them.
    """
    known_tables: ClassVar[Set[str]] = {
        "Search Blacklist",
        "Printing Coercion",
        "Printing If",
        "Printing Let",
        "Printing Record",
        "Printing Constructor",
        "Keep Equalities"
    }
    """
    An exhaustive list of known tables.

    Required for parsing table names from commands since we do not have
    access to the Coq parser.
    List obtained from an invocation of ``Print Options.``.
    Do not modify this list.
    """
    _known_table_regex: ClassVar[re.Pattern] = regex_from_options(
        known_tables,
        True,
        False,
        True)

    def __post_init__(self):
        """
        Validate that at least one value is provided.
        """
        if not isinstance(self.value, set):
            raise TypeError(f"Expected a set of values, got {type(self.value)}")
        elif len(self.value) == 0:
            raise ValueError("At least one table value must be specified.")

    def __hash__(self) -> int:  # noqa: D105
        return hash((self.name, tuple(sorted(self.value)), self.inclusive))

    def __str__(self) -> str:
        """
        Format the table as it would appear as a command-line option.
        """
        return ""

    @property
    def args(self) -> Tuple[Set[str], Set[str]]:
        """
        A pair of sets of values added or removed from the table.
        """
        if self.inclusive:
            return (self.value, set())
        else:
            return (set(), self.value)

    def as_command(self) -> str:
        """
        Get a Vernacular command for modifying this table.
        """
        if self.inclusive:
            prefix = "Add"
        else:
            prefix = "Remove"
        result = f'{prefix} {self.name} {" ".join(self.value)}'
        return result

    @classmethod
    def _parse_command(cls, command: str) -> 'CoqTable':
        error_msg = f"Syntax error when parsing table from {command}"
        try:
            cmd, table_setting = command.split(maxsplit=1)
        except ValueError as e:
            raise ValueError(error_msg) from e
        if cmd == 'Add':
            inclusive = True
        elif cmd == 'Remove':
            inclusive = False
        else:
            raise ValueError(error_msg)
        m = cls._known_table_regex.match(table_setting)
        if m is None:
            raise ValueError
        table_name = m.groups()[0]
        values_ = table_setting[m.end():].split()
        # recombine any split strings
        values: List[str] = []
        in_string = False
        for value in values_:
            if in_string:
                values[-1] += value
                if value[-1] == '"':
                    in_string = False
                continue
            elif value[0] == '"':
                in_string = True
            values.append(value)
        return CoqTable(table_name, set(values), inclusive)

    @classmethod
    def _parse_print_table(cls, table_name: str, feedback: str) -> 'CoqTable':
        """
        Parse a table's value from the output of ``Print Table ...``.
        """
        delimiter = ":"
        if table_name == "Keep Equalities":
            # no colon for this table
            delimiter = "proofs"
        values: Union[str, Set[str]]
        try:
            _msg, values = feedback.split(delimiter, maxsplit=1)
        except ValueError as e:
            raise ValueError(
                f"Cannot parse table value from '{feedback}'") from e
        if len(values) == 1 and values[0] == "None":
            values = set()
        else:
            values = {v[:-1] if v.endswith('.') else v for v in values.split()}
        return CoqTable(table_name, values, True)

    @classmethod
    def from_args(cls,  # noqa: D102
                  name: str,
                  args: Tuple[Set[str],
                              ...]) -> List[CoqSetting[Set[str]]]:
        tables: List[CoqSetting[Set[str]]] = []
        for i, values in enumerate(args):
            is_inclusive = not bool(i % 2)
            tables.append(CoqTable(name, values, is_inclusive))
        if not tables:
            tables.append(CoqTable(name, set(), True))
        return tables

    @classmethod
    def reduce_args(  # noqa: D102
            cls,
            former_args: Tuple[Set[str],
                               ...],
            latter_args: Tuple[Set[str],
                               ...]) -> Tuple[Set[str],
                                              ...]:
        inclusions: Set[str] = reduce(
            lambda x,
            y: x.union(y),
            former_args[:: 2] + latter_args[:: 2],
            initial=set())
        exclusions: Set[str] = reduce(
            lambda x,
            y: x.union(y),
            former_args[1 :: 2] + latter_args[1 :: 2],
            initial=set())
        return (
            inclusions.difference(exclusions),
            exclusions.difference(inclusions))


@dataclass
class LoadedFile:
    """
    A Coq file loaded via commmand-line option.
    """

    # NOTE: We could track relative file paths like IQR flags, but at
    # the moment we delay that feature in anticipation of the need being
    # rare.

    is_verbose: bool
    """
    Whether the Coq file is loaded verbosely or not.
    """
    name: str
    """
    The name of the Coq file to load.
    """

    def __str__(self) -> str:
        """
        Format the corresponding command-line option.
        """
        if self.is_verbose:
            result = f'-lv "{self.name}"'
        else:
            result = f'-l "{self.name}"'
        return result

    def as_command(self) -> str:
        """
        Get a Vernacular command for loading this file.
        """
        if self.is_verbose:
            command = f'Load Verbose {self.name}.'
        else:
            command = f'Load {self.name}.'
        return command


@dataclass
class SerAPIOptions:
    """
    A comprehensive set of Coq compiler options that are used by SerAPI.

    Note that some of these options are not directly supported by SerAPI
    but must be manually mimicked using Vernacular commands.
    See https://coq.inria.fr/refman/practical-tools/coq-commands.html#by-command-line-options
    for a complete list of Coq command-line options.
    """  # noqa: W505, B950

    # NOTE: more options can be added as needed

    noinit: bool
    """
    Whether to load Coq's standard library (`Coq.Init.Prelude`) on
    startup or not.
    """
    iqr: IQR
    """
    Physical to logical library path binding and load paths.
    """
    warnings: List[CoqWarning]
    """
    A sequence of explicitly set warning options.

    Note that the order of the list matters as later warnings override
    previously listed ones.
    Each set warning is equivalent to ``Set Warning <w>.``.
    """
    settings: List[Union[CoqFlag, CoqOption]]
    """
    A sequence of explicitly set flags or options.
    """
    allow_sprop: bool
    """
    If True, then enables the use of `SProp`.

    Equivalent to ``Set Allow StrictProp.``.
    """
    disallow_sprop: bool
    """
    If True, then disables the use of `SProp`.

    Equivalent to ``Unset Allow StrictProp.``.

    This option is supported only in SerAPI 8.11.0+0.11.1 and later.
    """
    type_in_type: bool
    """
    If True, disable strict universe checking.

    Equivalent to ``Unset Universe Checking.``.
    """
    impredicative_set: bool
    """
    Change the logical theory of Coq by declaring the sort `Set` to be
    impredicative.

    This option is supported only in SerAPI 8.16.0+0.16.2 and later.
    """
    indices_matter: bool
    """
    Levels of indices (and nonuniform parameters) contribute to the
    level of inductives.

    This option is supported only in SerAPI 8.11.0+0.11.1 and later.
    """
    loaded_files: List[LoadedFile]
    """
    Load a Coq file "f.v".

    Equivalent to ``Load "f".``.
    """

    def __or__(self, other: 'SerAPIOptions') -> 'SerAPIOptions':
        """
        Merge these options with another set.
        """
        if not isinstance(other, SerAPIOptions):
            return NotImplemented
        warning_states: Dict[str,
                             CoqWarningState] = {}
        for w in itertools.chain(self.warnings, other.warnings):
            warning_states[w.name] = w.state
        setting_states: Dict[str,
                             Tuple[Type[CoqSetting],
                                   Optional[Union[bool,
                                                  str,
                                                  int]]]] = {}
        for s in itertools.chain(self.settings, other.settings):
            assert not isinstance(s, CoqTable), \
                "Tables cannot be assigned values directly"
            setting_states[s.name] = (type(s), s.value)
        loaded_files: Dict[str,
                           bool] = {}
        for load in itertools.chain(self.loaded_files, other.loaded_files):
            if load not in loaded_files:
                loaded_files[load.name] = load.is_verbose
        return SerAPIOptions(
            self.noinit or other.noinit,
            self.iqr | other.iqr,
            [CoqWarning(v,
                        k) for k,
             v in warning_states.items()],
            typing.cast(
                List[Union[CoqFlag,
                           CoqOption]],
                [tp(k,
                    v) for k,
                 (tp,
                  v) in setting_states.items()]),
            allow_sprop=self.allow_sprop or other.allow_sprop,
            disallow_sprop=self.disallow_sprop or other.disallow_sprop,
            type_in_type=self.type_in_type or other.type_in_type,
            impredicative_set=self.impredicative_set or other.impredicative_set,
            indices_matter=self.indices_matter or other.indices_matter,
            loaded_files=[LoadedFile(v,
                                     k) for k,
                          v in loaded_files.items()])

    def __str__(self) -> str:
        """
        Format the options as they would appear on the command line.
        """
        options = ['-noinit'] if self.noinit else []
        options.append(str(self.iqr))
        options.extend(f"-w {warning}" for warning in self.warnings)
        options.extend(str(setting) for setting in self.settings)
        options.extend(["-allow-sprop"] if self.allow_sprop else [])
        options.extend(["-disallow-sprop"] if self.disallow_sprop else [])
        options.extend(["-type-in-type"] if self.type_in_type else [])
        options.extend(["-impredicative-set"] if self.impredicative_set else [])
        options.extend(['-indices-matter'] if self.indices_matter else [])
        options.extend([f"-load-vernac-source {f}" for f in self.loaded_files])
        return ' '.join(options)

    @property
    def settings_dict(
        self
    ) -> Dict[str,
              Tuple[Type[Union[CoqFlag,
                               CoqOption]],
                    Optional[Union[bool,
                                   str,
                                   int]]]]:
        """
        A dictionary mapping setting names to their values.
        """
        return typing.cast(
            Dict[str,
                 Tuple[Type[Union[CoqFlag,
                                  CoqOption]],
                       Optional[Union[bool,
                                      str,
                                      int]]]],
            CoqSetting.to_dict(self.settings))

    @property
    def warnings_dict(self) -> Dict[str, CoqWarningState]:
        """
        A dictionary mapping warning names to their states.
        """
        warning_states: Dict[str,
                             CoqWarningState] = {}
        for w in self.warnings:
            warning_states[w.name] = w.state
        return warning_states

    def _check_option_validity(
            self,
            serapi_version: Union[str,
                                  Version]) -> None:
        """
        Check that valid options are being given to SerAPI.
        """
        is_pre_8_10 = OpamVersion.less_than(serapi_version, '8.10.0')
        is_pre_8_11 = OpamVersion.less_than(serapi_version, '8.11.0+0.11.1')
        is_pre_8_16 = OpamVersion.less_than(serapi_version, '8.16.0+0.16.2')
        if is_pre_8_10:
            if self.allow_sprop:
                raise SerAPIOptionException(
                    "Unsupported SerAPI option: -allow-sprop")
            if self.disallow_sprop:
                raise SerAPIOptionException(
                    "Unsupported SerAPI option: -disallow-sprop")
        if is_pre_8_11:
            if self.indices_matter:
                raise SerAPIOptionException(
                    "Unsupported SerAPI option: -indices-matter")
        if is_pre_8_16:
            # No known way to set impredicative set via Vernacular
            if self.impredicative_set:
                raise SerAPIOptionException(
                    "Unsupported SerAPI option: -impredicative-set")

    def as_coq_args(self) -> str:
        """
        Get the corresponding Coq compiler command-line argument string.
        """
        return str(self)

    def as_serapi_args(self, serapi_version: Union[str, Version]) -> str:
        """
        Get the corresponding `sertop` command-line argument string.
        """
        self._check_option_validity(serapi_version)
        is_pre_8_10 = OpamVersion.less_than(serapi_version, '8.10.0')
        is_pre_8_11 = OpamVersion.less_than(serapi_version, '8.11.0+0.11.1')
        is_pre_8_16 = OpamVersion.less_than(serapi_version, '8.16.0+0.16.2')
        if is_pre_8_10:
            options = ['--no_init'] if self.noinit else []
        else:
            options = ['--no_prelude'] if self.noinit else []
        options.append(self.iqr.as_serapi_args())
        if not is_pre_8_11:
            options.extend(["--disallow-sprop"] if self.disallow_sprop else [])
            options.extend(["--indices-matter"] if self.indices_matter else [])
        if not is_pre_8_16:
            options.extend(
                ["--impredicative-set"] if self.impredicative_set else [])
        return ' '.join(options)

    def get_sertop_commands(
            self,
            serapi_version: Union[str,
                                  Version]) -> List[Tuple[bool,
                                                          str]]:
        """
        Get commands that must be executed to imitate certain options.

        Not all command-line options are directly supported by `sertop`.
        Each yielded command is paired with a Boolean indicating whether
        it belongs to the SerAPI protocol (True) or should be executed
        as a Coq Vernacular command (False). The commands should be
        executed in the order returned.
        """
        self._check_option_validity(serapi_version)
        is_pre_8_10 = OpamVersion.less_than(serapi_version, '8.10.0')
        is_pre_8_11 = OpamVersion.less_than(serapi_version, '8.11.0+0.11.1')
        is_pre_8_16 = OpamVersion.less_than(serapi_version, '8.16.0+0.16.2')
        commands: List[Tuple[bool, str]] = []
        if is_pre_8_10 and self.noinit:
            commands.append(
                (
                    True,
                    '(NewDoc ('
                    '(top_name (TopLogical (DirPath ((Id "Sertop"))))) '
                    '(require_libs ()) '
                    '))'))
        commands.extend((False, w.as_command()) for w in self.warnings)
        commands.extend((False, s.as_command()) for s in self.settings)
        if self.type_in_type:
            commands.append((False, "Unset Universe Checking."))
        if is_pre_8_11:
            commands.extend(
                [(False,
                  "Set Allow StrictProp.")] if self.allow_sprop else [])
            commands.extend(
                [(False,
                  "Unset Allow StrictProp.")] if self.disallow_sprop else [])
        if is_pre_8_16:
            # No known way to set impredicative set via Vernacular
            pass
        return commands

    def serialize(self) -> str:
        """
        Serialize the options as they would appear on the command line.
        """
        return str(self)

    @classmethod
    def parse_args(
            cls,
            args: Union[str,
                        List[str]],
            pwd: PathLike = "") -> 'SerAPIOptions':
        """
        Extract Coq options from command-line arguments.

        Parameters
        ----------
        args : str | List[str]
            A list of string arguments associated with a command.
        pwd : PathLike, optional
            The directory in which the command was executed, by default
            an empty string.

        Returns
        -------
        CoqOptions
            The parsed Coq compiler options.
        """
        is_string = False
        if isinstance(args, str):
            # written this way for type checking
            is_string = True
            args = shlex.split(args)
        # preprocess warning args to avoid leading dashes
        is_warning_arg = False
        for i in range(len(args)):
            arg = args[i]
            if is_warning_arg:
                if arg.startswith('-'):
                    args[i] = ' ' + arg
                is_warning_arg = False
            elif arg == "-w":
                is_warning_arg = True
        parser = argparse.ArgumentParser()
        parser.add_argument(
            '-w',
            metavar=('w1,..,wn'),
            nargs=1,
            action='append',
            default=[],
            help='configure display of warnings')
        parser.add_argument(
            '-set',
            nargs=1,
            action='append',
            default=[],
            help="Enable a flag or set an option's value")
        parser.add_argument(
            '-unset',
            nargs=1,
            action='append',
            default=[],
            help="Disable a flag")
        parser.add_argument(
            '-noinit',
            '-nois',
            action='store_true',
            default=False,
            help='start without loading the Init library')
        parser.add_argument(
            '-load-vernac-source',
            '-l',
            nargs=1,
            action='append',
            default=[],
            help="Load and execute a Coq script")
        parser.add_argument(
            '-load-vernac-source-verbose',
            '-lv',
            nargs=1,
            action='append',
            default=[],
            help="Load and execute a Coq script. "
            "Write its contents to the standard output as it is executed.")
        parser.add_argument(
            '-disallow-sprop',
            action='store_true',
            default=False,
            help='Forbid using the proof irrelevant SProp sort')
        parser.add_argument(
            '-allow-sprop',
            action='store_true',
            default=False,
            help='Allow using the proof irrelevant SProp sort')
        parser.add_argument(
            '-type-in-type',
            action='store_true',
            default=False,
            help='Disable universe consistency checking')
        parser.add_argument(
            '-indices-matter',
            action='store_true',
            default=False,
            help='Levels of indices (and nonuniform parameters) contribute '
            'to the level of inductives.')
        parser.add_argument(
            '-impredicative-set',
            action='store_true',
            default=False,
            help='Declare the sort Set to be impredicative')
        parsed_args, args = parser.parse_known_args(args)
        noinit = parsed_args.noinit
        if is_string:
            # make robust to parsing serialized IQR flags with commas
            args = ' '.join(args)
        iqr = IQR.parse_args(args, pwd)
        warnings = []
        for warning_option in parsed_args.w:
            warns = warning_option[0].split(',')
            for warning in warns:
                warnings.append(CoqWarning.deserialize(warning))
        settings = [
            CoqSetting.parse_arg(True,
                                 setting[0]) for setting in parsed_args.set
        ]
        settings.extend(
            CoqSetting.parse_arg(False,
                                 setting[0]) for setting in parsed_args.unset)
        loaded_files = [
            LoadedFile(False,
                       filename[0])
            for filename in parsed_args.load_vernac_source
        ]
        loaded_files.extend(
            LoadedFile(True,
                       filename[0])
            for filename in parsed_args.load_vernac_source_verbose)
        return SerAPIOptions(
            noinit,
            iqr,
            warnings,
            settings,
            allow_sprop=parsed_args.allow_sprop,
            disallow_sprop=parsed_args.disallow_sprop,
            type_in_type=parsed_args.type_in_type,
            impredicative_set=parsed_args.impredicative_set,
            indices_matter=parsed_args.indices_matter,
            loaded_files=loaded_files)

    deserialize = parse_args

    @classmethod
    def empty(cls, pwd: PathLike = "") -> 'SerAPIOptions':
        """
        Get an empty set of options.
        """
        return SerAPIOptions(
            False,
            IQR(set(),
                set(),
                set(),
                pwd),
            warnings=[],
            settings=[],
            allow_sprop=False,
            disallow_sprop=False,
            type_in_type=False,
            impredicative_set=False,
            indices_matter=False,
            loaded_files=[])

    @classmethod
    def merge(
            cls,
            options: Sequence['SerAPIOptions'],
            root: PathLike) -> 'SerAPIOptions':
        """
        Merge multiple `SerAPIOptions` instances into one object.

        Parameters
        ----------
        options : Sequence[SerAPIOptions]
            One or more parsed options.
            Note that the order matters when combining sequential fields
            such as `warnings`.
        root : PathLike
            The root directory to which all path-like options including
            `IQR` flags should be relative.

        Returns
        -------
        SerAPIOptions
            The combined options.
        """

        def or_(x, y):
            return x | y

        return reduce(or_, [c for c in options], SerAPIOptions.empty(root))

    @classmethod
    def from_coq_project_files(cls,
                               project_root: PathLike
                               ) -> Optional['SerAPIOptions']:
        """
        Infer options from ``_CoqProject`` files within a directory.
        """
        serapi_options = []
        for coq_project_file in itertools.chain(
                glob.glob(f"{project_root}/**/_CoqProject",
                          recursive=True),
                glob.glob(f"{project_root}/**/Make",
                          recursive=True)):
            coq_project_path = Path(coq_project_file).parent
            with open(coq_project_file, "r") as f:
                lines = f.readlines()
            serapi_options.append(
                cls.parse_args(' '.join(lines),
                               coq_project_path))
        if len(serapi_options) > 0:
            result = cls.merge(serapi_options, root=project_root)
        else:
            result = None
        return result
