"""
Provides an object-oriented abstraction of OPAM switches.
"""
import logging
import os
import re
from dataclasses import InitVar, dataclass, field
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
    _external_dirname: ClassVar[str] = "_opam"
    switch_name: InitVar[Optional[str]] = None
    """
    The name of the switch, by default None.

    If None, then this implies usage of the "default" switch.
    """
    switch_root: InitVar[Optional[PathLike]] = None
    """
    The root path in which to create the switch, by default None.

    If None, then this implies usage of the "default" root.
    """
    name: str = field(init=False)
    """
    The name of the switch.

    Equivalent to setting ``$OPAMSWITCH`` to `name`.
    """
    root: PathLike = field(init=False)
    """
    The root in which the switch was created.

    Equivalent to setting ``$OPAMROOT`` to `root`.
    """
    _is_external: bool = field(init=False)
    """
    Whether this is an external (i.e., local) switch.
    """

    def __post_init__(
            self,
            switch_name: Optional[str],
            switch_root: Optional[PathLike]):
        """
        Realize switch name and root and perform validation.
        """
        if switch_name is None:
            # get the name of the current default (global) switch
            switch_name = bash.run("opam var switch").stdout.strip()
        if switch_root is None:
            # get the name of the current default root
            switch_root = bash.run("opam var root").stdout.strip()
        if self.is_external(switch_name):
            # ensure local switch name is unambiguous
            switch_name = str(Path(switch_name).absolute())
        object.__setattr__(self, 'name', switch_name)
        object.__setattr__(self, 'root', switch_root)
        object.__setattr__(self, '_is_external', self.is_external(self.name))
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
        ValueError
            If no switch exists at the configured path.
        """
        opam_env = {}

        try:
            r = (self.path / '.opam-switch/environment').read_text()
        except FileNotFoundError:
            raise ValueError(
                f"No such switch: {self.name} with root {self.root}")

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

        environ['OPAMROOT'] = self.root

        environ['OPAMSWITCH'] = self.name if not self.is_clone else self.origin

        return environ

    @property
    def is_clone(self) -> bool:
        """
        Return whether this switch is a clone or not.
        """
        return self.origin is not None

    @cached_property
    def origin(self) -> Optional[str]:
        """
        Get the name of the switch from which this switch was cloned.

        If this switch *isn't* a clone, then ``None`` is returned.

        Notes
        -----
        If this switch was cloned from a clone, then this yields the
        original clone's origin. One can apply this rule recursively to
        conclude that the origin always refers to a real switch.
        """
        # get the original switch name from the copied and unaltered
        # environment file
        original_prefix = Path(self.env['OPAM_SWITCH_PREFIX'])
        origin = original_prefix.name
        if origin == self._external_dirname:
            origin = str(original_prefix.parent)
        if origin == self.name:
            origin = None
        return origin

    @cached_property
    def path(self) -> Path:
        """
        Get the path to the switch directory.
        """
        return self.get_root(self.root, self.name)

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
        if self.is_clone:
            # this is a clone and it needs to be mounted
            # at the location it thinks it is at
            # for the duration of the command
            src = self.path
            # by limitations of `OpamAPI.clone_switch`, a clone must
            # share the root of its origin
            dest = self.get_root(self.root, self.origin)
            if not dest.exists():
                # we need a mountpoint.
                # maybe the original clone was deleted?
                dest.mkdir()
            command = f'bwrap --dev-bind / / --bind {src} {dest} -- {command}'
        r = bash.run(command, env=env, **kwargs)
        if check:
            self.check_returncode(command, r)
        return r

    @classmethod
    def get_root(cls, root: PathLike, name: str) -> Path:
        """
        Get the root directory of the switch's files.

        Note that this is not to be confused with the Opam root, which
        may differ in the case of external (local) switches.

        Parameters
        ----------
        root : PathLike
            The Opam root with respect to which the hypothetical switch
            `name` should be evaluated.
        name : str
            The name of a hypothetical switch.

        Returns
        -------
        Path
            The absolute path to the switch's directory.
        """
        # based on `get_root` at src/format/opamSwitch.ml in Opam's
        # GitHub repository
        if cls.is_external(name):
            path = Path(name).absolute() / cls._external_dirname
        else:
            path = Path(root) / name
        return path.absolute()

    @classmethod
    def is_external(cls, name: str) -> bool:
        """
        Return whether `name` denotes an external (i.e., local) switch.
        """
        # based on `is_external` at src/format/opamSwitch.ml in Opam's
        # GitHub repository
        return name.startswith(".") or os.path.sep in name

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
