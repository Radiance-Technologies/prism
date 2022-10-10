"""
Provides an object-oriented abstraction of OPAM switches.
"""
import logging
import os
import re
import tempfile
import warnings
from dataclasses import InitVar, dataclass, field, fields
from functools import cached_property, reduce
from os import PathLike
from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess
from typing import ClassVar, Dict, List, Optional, Tuple, Union

from seutil import bash

from prism.util.bash import escape

from .file import OpamFile
from .formula import LogicalPF, LogOp, PackageConstraint, PackageFormula
from .version import OCamlVersion, OpamVersion, Version

__all__ = ['OpamSwitch']

logger = logging.getLogger(__file__)
logger.setLevel(logging.DEBUG)

_allow_unsafe_clone = []
# Private module variable to allow fallback in OpamSwitch.run for clones
# that cannot invoke bwrap in an unprivileged container (e.g., a docker
# container runner within Gitlab CI)
# Very hacky and ugly.

Package = Tuple[str, Optional[Version]]
PackageMetadata = Tuple[str, str]


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
            switch_name = str(Path(switch_name).resolve())
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

    def as_clone_command(self, command: str) -> Tuple[str, Path, Path]:
        """
        Get the equivalent command for execution in a cloned switch.

        This does not need to be used in normal circumstances.

        Parameters
        ----------
        command : str
            A command to run in the switch, which is presumed to be a
            clone of some other switch.

        Returns
        -------
        str
            A transformation of `command` that runs in the switch.
        src : str
        """
        # this is a clone and it needs to be mounted
        # at the location it thinks it is at
        # for the duration of the command
        src = self.path
        # by limitations of `OpamAPI.clone_switch`, a clone must
        # share the root of its origin
        if self.origin is None:
            dest = src
        else:
            dest = self.get_root(self.root, self.origin)
        if not dest.exists():
            # we need a mountpoint.
            # maybe the original clone was deleted?
            dest.mkdir()
        command = escape(command)
        command = f'bwrap --dev-bind / / --bind {src} {dest} -- bash -c "{command}"'
        return command, src, dest

    def export(
            self,
            include_id: bool = True,
            include_metadata: bool = False) -> 'OpamSwitch.Configuration':
        """
        Export the switch configuration.

        The switch configuration details installed and pinned package
        versions for replication of the environment.

        Parameters
        ----------
        include_id : bool, optional
            Whether to include the switch root, name, and if it is a
            clone alongside the usual output of ``opam switch export``,
            by default True.
        include_metadata : bool, optional
            If True, then include the metadata of all installed
            packages.

        Returns
        -------
        OpamSwitch.Configuration
            The switch configuration.
        """
        include_metadata = "--full" if include_metadata else ""
        with tempfile.NamedTemporaryFile('r') as f:
            self.run(f"opam switch export {include_metadata} {f.name}")
            # Contents are so close but not quite yaml or json.
            # Custom parsing is required.
            contents: str = f.read()
        # strip package strings of quotes before tokenizing
        contents = contents.split("\npackage ")
        package_metadata = contents[1 :]
        contents = contents[0]
        tokens = contents.split()
        kwargs = {}
        field = None
        # identify fields and their raw values
        for token in tokens:
            if token.endswith(":"):
                assert field is None
                field = token[:-1].replace("-", "_")
            else:
                assert field is not None
                if token.startswith("["):
                    kwargs[field] = []
                    token = token[1 :]
                if field in kwargs:
                    if token.endswith("]"):
                        token = token[:-1]
                        if token:
                            kwargs[field].append(token)
                        field = None
                    elif token:
                        kwargs[field].append(token)
                else:
                    kwargs[field] = token
                    field = None
        # process fields
        for field, value in kwargs.items():
            # safe to modify dict since keys are not added or removed
            if field == "opam_version":
                kwargs[field] = Version.parse(value, require_quotes=True)
            else:
                packages = []
                if not isinstance(value, list):
                    value = [value]
                for package in value:
                    package: PackageConstraint = PackageConstraint.parse(
                        package)
                    packages.append(
                        (package.package_name,
                         package.version_constraint))
                kwargs[field] = packages
        all_metadata = []
        for pm in package_metadata:
            name, metadata = pm.split(" ", maxsplit=1)
            all_metadata.append((name.strip('"'), metadata))
        if package_metadata:
            kwargs['package_metadata'] = all_metadata
        if include_id:
            # Coerce `root` into `str`. `Path` can't be serialized.
            kwargs['opam_root'] = str(self.root)
            kwargs['switch_name'] = self.name
            kwargs['is_clone'] = self.is_clone
        return OpamSwitch.Configuration(**kwargs)

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
            pkg: Union[str,
                       PathLike],
            version: Optional[str] = None) -> PackageFormula:
        """
        Get the dependencies of the indicated package.

        Parameters
        ----------
        pkg : Union[str, PathLike]
            The name of an OCaml package or path to an OPAM file /
            directory containing an OPAM file.
        version : Optional[str], optional
            A specific version of the package, by default None.
            If not given, then either the latest or the installed
            version of the package will be queried for dependencies.

        Returns
        -------
        PackageFormula
            A formula expressing the package's dependencies.

        Raises
        ------
        CalledProcessError
            If the ``opam show`` command fails.
        ValueError
            If both a path and version are given.
        """
        is_path = Path(pkg).exists()
        if version is not None:
            if is_path:
                raise ValueError(
                    "Version cannot be specified for installation from file. "
                    f"Expected None, but got {version} for package {pkg}.")
            pkg = f"{pkg}={version}"
        r = self.run(f"opam show -f depends: {pkg}")
        # Dependencies returned as list of AND-conjoined formulas, but
        # the AND operator is missing.
        # Must parse piecemeal since otherwise there is no known
        # reliable way to infer where AND operators should be inserted
        dep_text = r.stdout.strip()
        pos = 0
        formulas = []
        while pos < len(dep_text):
            formula, pos = PackageFormula.parse(dep_text, exhaustive=False, pos=pos)
            formulas.append(formula)
        formula = reduce(
            lambda l,
            r: LogicalPF(l,
                         LogOp.AND,
                         r),
            formulas[1 :],
            formulas[0])
        return formula

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
            pkg: Union[str,
                       PathLike],
            version: Optional[str] = None,
            deps_only: bool = False) -> None:
        """
        Install the indicated package.

        Parameters
        ----------
        pkg : Union[str, PathLike]
            The name of an OCaml package or the path to a file
            containing a package description or a directory containing
            such a file.
        version : Optional[str], optional
            A specific version of the package, by default None.
            If not given, then the default version will be installed.
        deps_only : bool, optional
            If True, then install all of the packages dependencies, but
            do not actually install it.

        Exceptions
        ----------
        CalledProcessError
            If the installation fails (due to bad version usually)
            it will raise this exception
        ValueError
            If a path and version are both given.
        """
        is_path = Path(pkg).exists()
        if version is not None:
            if is_path:
                raise ValueError(
                    "Version cannot be specified for installation from file. "
                    f"Expected None, but got {version} for package {pkg}.")
            pkg = f"{pkg}.{version}"
        cmd = f"opam install {pkg} -y {'--deps-only' if deps_only else ''}"
        self.run(cmd)

    def install_formula(self, formula: PackageFormula) -> None:
        """
        Install packages satisfying the given formula in this switch.

        Parameters
        ----------
        formula : PackageFormula
            A formula describing package constraints.

        Exceptions
        ----------
        CalledProcessError
            If the installation fails for any reason.
        """
        with tempfile.NamedTemporaryFile('w', delete=False) as f:
            f.write(
                str(
                    OpamFile(
                        Path(f.name).stem,
                        "0.0",
                        "temp@example.com",
                        depends=formula)))
            # close to ensure contents are flushed
        self.install(f.name, deps_only=True)
        # delete the temp file
        os.remove(f.name)

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
            command, src, dest = self.as_clone_command(command)
        r = bash.run(command, env=env, **kwargs)
        if check:
            try:
                self.check_returncode(command, r)
            except CalledProcessError:
                permission_error = (
                    "bwrap: Creating new namespace failed: "
                    "Operation not permitted")
                if (_allow_unsafe_clone and self.is_clone and r.returncode == 1
                        and r.stderr.strip() == permission_error):
                    warnings.warn(
                        "Unable to invoke 'bwrap'. "
                        "Are you running in an unprivileged Docker container? "
                        "Falling back to terrible alternative. ")
                    # temporarily switch clone and origin directories
                    tmp = str(dest) + "-temp"
                    os.rename(dest, tmp)
                    os.rename(src, dest)
                    r = bash.run(
                        command.split("--")[-1].strip(),
                        env=env,
                        **kwargs)
                    try:
                        self.check_returncode(command, r)
                    finally:
                        # restore original directories
                        os.rename(dest, src)
                        os.rename(tmp, dest)
                else:
                    raise
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
            path = Path(name).resolve() / cls._external_dirname
        else:
            path = Path(root) / name
        return path.resolve()

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

    @dataclass
    class Configuration:
        """
        A configuration of an Opam switch that enables reproducibility.

        A handful of optional fields are added to identify the existing
        switch from which the configuration was created.

        Notes
        -----
        See ``opam/src/format/opamFile.ml:SwitchSelectionsSyntax`` for
        derived fields.
        """

        opam_version: OpamVersion
        compiler: Optional[List[Package]] = None
        roots: Optional[List[Package]] = None
        installed: Optional[List[Package]] = None
        pinned: Optional[List[Package]] = None
        package_metadata: Optional[List[PackageMetadata]] = None
        opam_root: Optional[str] = None
        switch_name: Optional[str] = None
        is_clone: Optional[str] = None

        def __str__(self) -> str:
            """
            Pretty-print the configuration in the Opam file format.
            """
            s = []
            for f in fields(self):
                field_name = f.name
                field_value = getattr(self, field_name)
                if field_value is None:
                    continue
                if field_name != "package_metadata":
                    s.append(field_name.replace("_", "-"))
                    s.append(": ")
                    if isinstance(field_value, list):
                        packages = ["["]
                        for name, version in field_value:
                            packages.append(f'"{name}.{version}"')
                        s.append("\n  ".join(packages))
                        s.append("\n]")
                    else:
                        s.append(f'"{field_value}"')
                    s.append("\n")
                else:
                    for name, metadata in field_value:
                        s.append(f'package "{name}"{metadata}\n')
            return ''.join(s)
