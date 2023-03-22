"""
Defines an abstraction of Coq compiler options that are used by SerAPI.
"""
import argparse
import glob
import itertools
import shlex
from dataclasses import dataclass
from enum import Enum, auto
from functools import reduce
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

from prism.interface.coq.iqr import IQR
from prism.util.opam import OpamVersion, Version
from prism.util.radpytools import PathLike


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


@dataclass
class CoqSetting:
    """
    A Coq flag, option, or table.

    See https://coq.inria.fr/refman/coq-optindex.html.
    """

    is_set: bool
    """
    Whether the flag is enabled.

    Irrelevant for non-Boolean options.
    """
    name: str
    """
    The name of the flag, option, or table.
    """

    def __str__(self) -> str:
        """
        Format the setting as it would appear as a command-line option.
        """
        if self.is_set:
            result = f'-set "{self.name}"'
        else:
            result = f'-unset "{self.name}"'
        return result

    def as_command(self) -> str:
        """
        Get a Vernacular command for setting this warning.
        """
        if self.is_set:
            command = f'Set {self.name}.'
        else:
            command = f'Unset {self.name}.'
        return command


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
    settings: List[CoqSetting]
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
                             bool] = {}
        for s in itertools.chain(self.settings, other.settings):
            setting_states[s.name] = s.is_set
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
            [CoqSetting(v,
                        k) for k,
             v in setting_states.items()],
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
            options.extend(["-disallow-sprop"] if self.disallow_sprop else [])
            options.extend(["-indices-matter"] if self.indices_matter else [])
        if not is_pre_8_16:
            options.extend(
                ["-impredicative-set"] if self.impredicative_set else [])
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
            help='Disable universe consistency checking')
        parser.add_argument(
            '-impredicative-set',
            action='store_true',
            default=False,
            help='Disable universe consistency checking')
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
        settings = [CoqSetting(True, setting[0]) for setting in parsed_args.set]
        settings.extend(
            CoqSetting(False,
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
