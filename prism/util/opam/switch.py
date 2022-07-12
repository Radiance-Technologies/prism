"""
Provides an object-oriented abstraction of OPAM switches.
"""
import logging
import os
import re
from dataclasses import dataclass
from functools import cached_property
from os import PathLike
from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess
from typing import ClassVar, Dict, List, Optional

from seutil import bash

from .constraint import VersionConstraint
from .version import OCamlVersion, OpamVersion, Version

logger = logging.getLogger(__file__)
logger.setLevel(logging.DEBUG)


@dataclass(frozen=True)
class OpamSwitch:
    """
    An OPAM switch.

    Note that OPAM must be installed to use all of the features of this
    class.

    .. warning::
        This class does not yet fully support the full expressivity of
        OPAM dependencies as documented at
        https://opam.ocaml.org/blog/opam-extended-dependencies/.
    """

    _whitespace_regex: ClassVar[re.Pattern] = re.compile(r"\s+")
    _newline_regex: ClassVar[re.Pattern] = re.compile("\n")
    name: Optional[str] = None
    """
    The name of the switch, by default None.

    If None, then this implies usage of the "default" switch.
    Equivalent to setting ``$OPAMSWITCH`` to `name`.
    """
    root: Optional[PathLike] = None
    """
    The current root path, by default None.

    If None, then this implies usage of the default root.
    Equivalent to setting ``$OPAMROOT`` to `root`.
    """

    def __post_init__(self) -> None:
        """
        Perform validation.
        """
        # force computation of environment to validate switch exists
        self.env

    def __str__(self) -> str:
        """
        Return the name of the switch.
        """
        return self.name

    @cached_property
    def env(self) -> Dict[str, str]:
        """
        Get the environment for this switch.

        Returns
        -------
        Dict[str, str]
            The environment variables corresponding to this switch.

        Raises
        ------
        CalledProcessError
            If the ``opam env`` command fails.
        """
        opam_env = {}

        r = (
            Path(self.root or '~/.opam/').expanduser() /
            (self.name or 'default') / '.opam-switch/environment').read_text()

        envs: List[str] = r.split('\n')[::-1]
        for env in envs:
            if (env == ''):
                continue
            var, _, val, _ = env.strip().split("\t")
            opam_env[var] = val
        return opam_env

    @property
    def environ(self) -> Dict[str, str]:
        """
        Get the complete environment suitable for use with `subprocess`.
        """
        environ = dict(os.environ)
        new_path = self.env.pop('PATH', None)
        environ.update(self.env)
        if new_path is not None:
            self.env.update({'PATH': new_path})
            environ['PATH'] = os.pathsep.join([new_path, environ['PATH']])
        if self.root is not None:
            environ['OPAMROOT'] = self.root

        environ['OPAMSWITCH'] = Path(self.env["OPAM_SWITCH_PREFIX"]).name

        return environ

    def add_repo(self, repo_name: str, repo_addr: Optional[str] = None) -> None:
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
        CalledProcessError
            If the addition fails it will raise this exception
        """
        if repo_addr is not None:
            repo_name = f"{repo_name} {repo_addr}"
        self.run(f"opam repo add {repo_name}")

    def get_available_versions(self, pkg: str) -> List[Version]:
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
        r = self.run(f"opam show -f all-versions {pkg}")
        versions = re.split(r"\s+", r.stdout)
        versions.pop()
        return [OCamlVersion.parse(v) for v in versions]

    def get_dependencies(
            self,
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
        r = self.run(f"opam show -f depends: {pkg}")
        # exploit fact that each dependency is on its own line in output
        dependencies: List[List[str]]
        dependencies = [
            self._whitespace_regex.split(dep,
                                         maxsplit=1)
            for dep in self._newline_regex.split(r.stdout)
        ]
        dependencies.pop()
        return {
            dep[0][1 :-1]:
            VersionConstraint.parse(dep[1] if len(dep) > 1 else "")
            for dep in dependencies
        }

    def get_installed_version(self, package_name: str) -> Optional[str]:
        """
        Get the installed version of the given package.

        Parameters
        ----------
        package_name : str
            The name of an Opam package.

        Returns
        -------
        str or None
            The installed version of the package or None if it is not
            installed in this switch.

        Raises
        ------
        RuntimeError
            If Opam yields information for a package by a different
            name.
        """
        r = self.run(f"opam list {package_name} -i").stdout.split("\n")
        if len(r) > 2:
            # output has following form:
            #  Packages matching: installed & name-match(<package_name>)
            #  Name # Installed # Synopsis
            #  <package_name> <version> <description>
            fields = r[2].split()
            name, installed = fields[0], fields[1]
            if package_name != name:
                raise RuntimeError(
                    f"Expected package {package_name}, got {name}")
            return str(OpamVersion.parse(installed))
        else:
            return None

    def install(
            self,
            pkg: str,
            version: Optional[str] = None,
            yes: Optional[bool] = False) -> None:
        """
        Install the indicated package.

        Parameters
        ----------
        pkg : str
            The name of an OCaml package.
        version : Optional[str], optional
            A specific version of the package, by default None.
            If not given, then the default version will be installed.
        yes : Optional[bool], optional
            Whether to include the --yes flag for installation.

        Exceptions
        ----------
        CalledProcessError
            If the installation fails (due to bad version usually)
            it will raise this exception
        """
        if version is not None:
            pkg = f"{pkg}.{version}"
        cmd = f"opam install {pkg}"
        if yes:
            cmd = cmd + " -y"
        self.run(cmd)

    def remove_pkg(
        self,
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
        self.run(f"opam remove {pkg}")

    def remove_repo(self, repo_name: str) -> None:
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
        self.run(f"opam repo remove {repo_name}")

    @cached_property
    def parent(self):
        """
        Name of the switch that this switch was cloned from.

        If this switch ISN'T a clone, this is the name of this switch.
        """
        return Path(self.env['OPAM_SWITCH_PREFIX']).name

    def run(
            self,
            command: str,
            check: bool = True,
            env: Optional[Dict[str,
                               str]] = None,
            **kwargs) -> CompletedProcess:
        """
        Run a given command and check for errors.
        """
        if env is None:
            env = self.environ

        opam_root = Path(self.root or '~/.opam').expanduser()
        real_name = self.name or 'default'
        if real_name != self.parent:
            # this is a clone and it needs to be mounted
            # at the location it thinks it is at.
            src = opam_root / real_name
            dest = opam_root / self.parent

            # out of excessive caution,
            # let's ensure we didn't get passed something
            # crazy like a switch called ".."
            # or "../././/."
            # before we bind mount to it.
            if (Path(real_name) == Path("..")
                    or Path(self.parent) == Path("..")):
                raise ValueError("Illegal name for opam switch: '..'.")
            # also, that it's not a directory.
            if (len(Path(real_name).parts) != 1
                    or len(Path(self.parent).parts) != 1):
                raise ValueError("Was given a switch named like a directory.")

            if not dest.exists():
                # we need a mountpoint.
                # maybe the original clone was deleted?
                dest.mkdir()

            command = 'bwrap --dev-bind / / --bind' \
                      + f' {src} {dest} -- {command}'
        r = bash.run(command, env=env, **kwargs)
        if check:
            self.check_returncode(command, r)
        return r

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
