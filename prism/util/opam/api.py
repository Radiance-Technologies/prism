"""
Defines an interface for programmatically querying OPAM.
"""
from contextlib import contextmanager
import logging
import re
from dataclasses import dataclass
import warnings
from subprocess import CalledProcessError, CompletedProcess
from typing import ClassVar, Dict, List, Optional, Union, Generator
from os import PathLike

from seutil import bash

from .constraint import VersionConstraint
from .version import OCamlVersion, Version

logger = logging.getLogger(__file__)
logger.setLevel(logging.DEBUG)


@dataclass
class OpamAPI:
    """
    Provides methods for querying the OCaml package manager.

    Note that OPAM must be installed.

    .. warning::
        This class does not yet fully support the full expressivity of
        OPAM dependencies as documented at
        https://opam.ocaml.org/blog/opam-extended-dependencies/.
    """

    _whitespace_regex: ClassVar[re.Pattern] = re.compile(r"\s+")
    _newline_regex: ClassVar[re.Pattern] = re.compile("\n")
    _SWITCH_INSTALLED_ERROR: ClassVar[
        str] = "[ERROR] There already is an installed switch named"
    opam_root: ClassVar[Optional[PathLike]] = None
    """
    The current root path, by default None.
    Equivalent to setting ``$OPAMROOT`` to `root`.
    """
    switch_name: ClassVar[Optional[str]] = None

    @classmethod
    def _root_option(cls) -> str:
        if cls.opam_root is not None:
            return f"--root={cls.opam_root}"
        return ""

    @classmethod
    def _switch_option(cls) -> str:
        if cls.switch_name is not None:
            return f"--switch={cls.switch_name}"
        return ""

    @classmethod
    def create_switch(
            cls,
            switch_name: str,
            compiler: Union[str,
                            Version]) -> None:
        """
        Create a new switch.

        If a switch with the desired name already exists, then this
        function has no effect.

        Parameters
        ----------
        switch_name : str
            The name of the desired switch.
        compiler : Union[str, Version]
            A version of the OCaml compiler on which to base the switch.

        Raises
        ------
        CalledProcessError
            If the ``opam switch create`` command fails.
        VersionParseError
            If `compiler` is not a valid version identifier.

        Warns
        -----
        UserWarning
            If a switch with the given name already exists.
        """
        if isinstance(compiler, str):
            compiler = OCamlVersion.parse(compiler)
        command = f'opam switch {cls._root_option()} create {switch_name} {compiler}'
        r = bash.run(command)
        if (r.returncode == 2
                and r.stderr.strip().startswith(cls._SWITCH_INSTALLED_ERROR)):
            warning = f"opam: the switch {switch_name} already exists"
            warnings.warn(warning)
            logger.log(logging.WARNING, warning)
            return
        cls.check_returncode(command, r)

    @classmethod
    def get_available_versions(cls, pkg: str) -> List[Version]:
        """
        Get a list of available versions of the requested package.

        Parameters
        ----------
        pkg : str
            The name of a package.

        Returns
        -------
        List[Version]
            The list of available versions of `pkg`.

        Raises
        ------
        CalledProcessError
            If the ``opam show`` command fails.
        """
        r = cls.run(
            f"opam show {cls._root_option()} {cls._switch_option()} "
            f"-f all-versions {pkg}")
        versions = re.split(r"\s+", r.stdout)
        versions.pop()
        return [OCamlVersion.parse(v) for v in versions]

    @classmethod
    def get_dependencies(
            cls,
            pkg: str,
            version: Optional[str] = None) -> Dict[str,
                                                   VersionConstraint]:
        """
        Get the dependencies of the indicated package.

        Parameters
        ----------
        pkg : str
            The name of an OCaml package.
        version : Optional[str], optional
            A specific version of the package, by default None.
            If not given, then either the latest or the installed
            version of the package will be queried for dependencies.

        Returns
        -------
        Dict[str, VersionConstraint]
            Dependencies as a map from package names to version
            constraints.

        Raises
        ------
        CalledProcessError
            If the ``opam show`` command fails.
        """
        if version is not None:
            pkg = f"{pkg}={version}"
        r = cls.run(
            f"opam show {cls._root_option()} {cls._switch_option()} "
            f"-f depends: {pkg}")
        # exploit fact that each dependency is on its own line in output
        dependencies: List[List[str]]
        dependencies = [
            cls._whitespace_regex.split(dep,
                                        maxsplit=1)
            for dep in cls._newline_regex.split(r.stdout)
        ]
        dependencies.pop()
        return {
            dep[0][1 :-1]:
            VersionConstraint.parse(dep[1] if len(dep) > 1 else "")
            for dep in dependencies
        }

    @classmethod
    def remove_switch(cls, switch_name: str) -> None:
        """
        Remove the indicated switch.

        Parameters
        ----------
        switch_name : str
            The name of an existing switch.

        Raises
        ------
        CalledProcessError
            If the `opam switch remove` command fails, e.g., if the
            indicated switch does not exist.
        """
        cls.run(f'opam switch {cls._root_option()} remove {switch_name} -y')

    @classmethod
    def set_switch(cls, switch_name: str) -> None:
        """
        Set the currently active switch to the given one.

        Parameters
        ----------
        switch_name : str
            The name of an existing switch.
        """
        cls.switch_name = switch_name

    @classmethod
    def show_switch(cls) -> str:
        """
        Get the name of the current switch.

        Returns
        -------
        str
            The name of the current switch.

        Raises
        ------
        CalledProcessError
            If the `opam switch show` command fails.
        """
        if cls.switch_name is None:
            r = cls.run('opam switch show')
            cls.switch_name = r.stdout
        return cls.switch_name

    @classmethod
    @contextmanager
    def switch(cls, switch_name: str) -> Generator[None, None, None]:
        """
        Get a context in which the given switch is active.

        The previously active switch is restored at the context's exit.
        """
        current_switch = cls.show_switch()
        try:
            cls.set_switch(switch_name)
            yield
        finally:
            cls.set_switch(current_switch)

    @staticmethod
    def check_returncode(command: str, r: CompletedProcess) -> None:
        """
        Check the return code and log any errors.

        Parameters
        ----------
        command : str
            A command.
        r : CompletedProcess
            The result of the given `command`.
        """
        try:
            r.check_returncode()
        except CalledProcessError:
            logger.log(
                logging.CRITICAL,
                f"'{command}' returned {r.returncode}: {r.stdout} {r.stderr}")
            raise

    @staticmethod
    def run(command: str) -> CompletedProcess:
        """
        Run a given command and check for errors.
        """
        r = bash.run(command)
        OpamAPI.check_returncode(command, r)
        return r
