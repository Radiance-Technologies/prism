"""
Provides an object-oriented abstraction of OPAM switches.
"""
import logging
import os
import re
from dataclasses import dataclass
from functools import cached_property
from os import PathLike
from subprocess import CalledProcessError, CompletedProcess
from typing import ClassVar, Dict, List, Optional

from seutil import bash

from .constraint import VersionConstraint
from .version import OCamlVersion, Version

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

    If None, then this implies usage of the default switch.
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
    def coq_version(self) -> str:
        """
        Obtain relevant coq_version for this particular Opam switch.
        """
        r = self.run("opam show coq --raw").stdout.split("\n")
        if len(r) > 2:
            if 'coq' not in r[1]:
                raise ValueError("Opam returned version for incorrect package")
            regex = r"version: \"(.*)\""
            matchObj = re.match(regex, r[2])
            if matchObj:
                return matchObj.groups()[0]
            else:
                raise ValueError("Coq version malformed")
        else:
            raise ValueError("Coq version not found")

    @cached_property
    def ocaml_version(self) -> str:
        """
        Obtain relevant ocaml_version for this particular Opam switch.
        """
        r = self.run("opam show ocaml --raw").stdout.split("\n")
        if len(r) > 2:
            if 'ocaml' not in r[1]:
                raise ValueError("Opam returned version for incorrect package")
            regex = r"version: \"(.*)\""
            matchObj = re.match(regex, r[2])
            if matchObj:
                return matchObj.groups()[0]
            else:
                raise ValueError("Ocaml version malformed")
        else:
            raise ValueError("Ocaml version not found")

    @cached_property
    def _environ(self) -> Dict[str, str]:
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
        if self.name is not None:
            environ['OPAMSWITCH'] = self.name
        return environ

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
        environ = dict(os.environ)
        if self.root is not None:
            environ['OPAMROOT'] = self.root
        if self.name is not None:
            environ['OPAMSWITCH'] = self.name
        r = self.run("opam env", env=environ)
        envs: List[str] = r.stdout.split(';')[0 :-1 : 2]
        for env in envs:
            var, val = env.strip().split("=", maxsplit=1)
            opam_env[var] = val.strip("'")
        return opam_env

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
        subprocess.CalledProcessError
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

    def install(self, pkg: str, version: Optional[str] = None) -> None:
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
        self.run(f"opam install {pkg}")

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
                               str]] = None) -> CompletedProcess:
        """
        Run a given command and check for errors.
        """
        if env is None:
            env = self._environ
        r = bash.run(command, env=env)
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
