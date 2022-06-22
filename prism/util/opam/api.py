"""
Defines an interface for programmatically querying OPAM.
"""
import logging
import os
import re
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from os import PathLike
from subprocess import CalledProcessError, CompletedProcess
from typing import ClassVar, Dict, Generator, List, Optional, Union

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
    opam_env: ClassVar[Dict[str,
                            str]] = {}
    """
    The output of ``opam env``.
    """
    opam_root: ClassVar[Optional[PathLike]] = None
    """
    The current root path, by default None.
    Equivalent to setting ``$OPAMROOT`` to `opam_root`.
    """
    opam_switch: ClassVar[Optional[str]] = None
    """
    The current switch, by default None.
    Equivalent to setting ``$OPAMSWITCH`` to `opam_switch`.
    """

    @classmethod
    def _environ(cls) -> Dict[str, str]:
        environ = dict(os.environ)
        new_path = cls.opam_env.pop('PATH', None)
        environ.update(cls.opam_env)
        if new_path is not None:
            environ['PATH'] = os.pathsep.join([new_path, environ['PATH']])
        if cls.opam_root is not None:
            environ['OPAMROOT'] = cls.opam_root
        if cls.opam_switch is not None:
            environ['OPAMSWITCH'] = cls.opam_switch
        return environ

    @classmethod
    def add_repo(cls, repo_name: str, repo_addr: Optional[str] = None) -> None:
        """
        Add a repo to the current switch.

        Parameters
        ----------
        repo_name : str
            The name of an opam repository.

        repo_addr : str
            The address of the repository. If omitted,
            the repo_name will be searched in already existing
            repos on the switch.

        Exceptions
        ----------
        subprocess.CalledProcessError
            If the addition fails it will raise this exception
        """
        if repo_addr is not None:
            repo_name = f"{repo_name} {repo_addr}"
        cls.run(f"opam repo add {repo_name}")

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
        command = f'opam switch create {switch_name} {compiler}'
        r = cls.run(command, check=False)
        if (r.returncode == 2
                and any(ln.strip().startswith(cls._SWITCH_INSTALLED_ERROR)
                        for ln in r.stderr.splitlines())):
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
        r = cls.run(f"opam show -f all-versions {pkg}")
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
        r = cls.run(f"opam show -f depends: {pkg}")
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
    def install(cls, pkg: str, version: Optional[str] = None) -> None:
        """
        Install the indicated package.

        Parameters
        ----------
        pkg : str
            The name of an OCaml package.
        version : Optional[str], optional
            A specific version of the package, by default None.
            If not given, then the default version will be installed.

        Exceptions
        ----------
        CalledProcessError
            If the installation fails (due to bad version usually)
            it will raise this exception
        """
        if version is not None:
            pkg = f"{pkg}.{version}"
        cls.run(f"opam install --yes {pkg}")

    @classmethod
    def remove_pkg(
        cls,
        pkg: str,
    ) -> None:
        """
        Remove the indicated package.

        Parameters
        ----------
        pkg : str
            The name of an OCaml package.

        Exceptions
        ----------
        CalledProcessError
            If the removal fails it will raise this exception
        """
        cls.run(f"opam remove {pkg}")

    @classmethod
    def remove_repo(cls, repo_name: str) -> None:
        """
        Remove a repo from the current switch.

        Parameters
        ----------
        repo_name : str
            The name of an opam repository.

        Exceptions
        ----------
        CalledProcessError
            If the removal fails it will raise this exception
        """
        cls.run(f"opam repo remove {repo_name}")

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
        cls.run(f'opam switch remove {switch_name} -y')

    @classmethod
    def run(cls, command: str, check: bool = True) -> CompletedProcess:
        """
        Run a given command and check for errors.
        """
        r = bash.run(command, env=cls._environ())
        if check:
            cls.check_returncode(command, r)
        return r

    @classmethod
    def set_switch(cls, switch_name: Optional[str]) -> None:
        """
        Set the currently active switch to the given one.

        Parameters
        ----------
        switch_name : str | None
            The name of an existing switch or None if one wants to
            restore the global switch.

        Raises
        ------
        CalledProcessError
            If the `opam env` comand fails, e.g., if the indicated
            switch does not exist.
        """
        cls.opam_env = {}
        if switch_name is not None:
            r = cls.run(f"opam env --switch={switch_name}")
            envs = r.stdout.split(';')[0 :-1 : 2]
            for env in envs:
                var, val = env.strip().split("=", maxsplit=1)
                cls.opam_env[var] = val
        cls.opam_switch = switch_name

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
        r = cls.run('opam switch show')
        return r.stdout.strip()

    @classmethod
    @contextmanager
    def switch(cls, switch_name: str) -> Generator[None, None, None]:
        """
        Get a context in which the given switch is active.

        The previously active switch is restored at the context's exit.
        """
        current_switch = cls.opam_switch
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
