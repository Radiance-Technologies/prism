"""
Provides metadata regarding Coq-related versions.
"""
import typing
from dataclasses import InitVar, dataclass
from pathlib import Path
from subprocess import CalledProcessError
from typing import Dict, List, Optional, Set, Tuple, Union

import seutil.io as io

from prism.util.opam import OCamlVersion, OpamAPI, Version
from prism.util.opam.formula import LogicalPF, PackageConstraint, VersionFormula
from prism.util.opam.formula.package import PackageFormula
from prism.util.opam.version import OpamVersion
from prism.util.radpytools import cachedmethod
from prism.util.radpytools.dataclasses import default_field

DATA_FILE = Path(__file__).parent / "version_info.yml"


@dataclass(frozen=True)
class VersionInfo:
    """
    Encapsulates version/dependency metadata.
    """

    coq_versions: InitVar[Optional[Union[VersionFormula, Set[Version]]]] = None
    serapi_versions: InitVar[Optional[Union[VersionFormula,
                                            Set[Version]]]] = None
    ocaml_versions: InitVar[Optional[Union[VersionFormula,
                                           Set[Version]]]] = None
    available_coq_versions: Set[str] = default_field(set())
    available_serapi_versions: Set[str] = default_field(set())
    available_ocaml_versions: Set[str] = default_field(set())
    coq_ocaml_compatibility: Dict[str, Set[str]] = default_field(dict())
    serapi_coq_compatibility: Dict[str, Set[str]] = default_field(dict())

    def __post_init__(  # noqa: C901
            self,
            coq_versions,
            serapi_versions,
            ocaml_versions) -> None:
        """
        Precompute dependencies.
        """

        def _init_versions(
                pkg: str,
                versions: Optional[Union[VersionFormula,
                                         Set[Version]]],
                attr: Set[str]) -> Tuple[List[str],
                                         List[Version]]:
            if versions is None or isinstance(versions, VersionFormula):
                available_versions = OpamAPI.active_switch.get_available_versions(
                    pkg)
                if versions is None:
                    versions = set(available_versions)
                else:
                    versions = {v for v in available_versions if v in versions}
            versions = typing.cast(Set[Version], versions)
            version_strs = {str(v) for v in versions}
            version_strs = version_strs.difference(attr)
            attr.update(version_strs)
            return (
                sorted(version_strs),
                sorted([Version.parse(v) for v in attr]))

        new_coq_versions, sorted_coq_versions = _init_versions(
            'coq',
            coq_versions,
            self.available_coq_versions)
        new_serapi_versions, _ = _init_versions(
            'coq-serapi',
            serapi_versions,
            self.available_serapi_versions)
        _, sorted_ocaml_versions = _init_versions(
            'ocaml',
            ocaml_versions,
            self.available_ocaml_versions)

        serapi_coq_compat = self.serapi_coq_compatibility
        for serapi_version in new_serapi_versions:
            dependencies = OpamAPI.active_switch.get_dependencies(
                "coq-serapi",
                serapi_version)
            assert isinstance(dependencies, LogicalPF)
            dependencies = dependencies.to_conjunctive_list()
            coq_constraint = None
            for dependency in dependencies:
                if (isinstance(dependency,
                               PackageConstraint)
                        and dependency.package_name == 'coq'):
                    coq_constraint = dependency.version_constraint
                    break
            assert coq_constraint is not None
            for coq_version in coq_constraint.filter_versions(
                    sorted_coq_versions):
                coq_version = str(coq_version)
                if coq_version not in serapi_coq_compat:
                    serapi_coq_compat[coq_version] = set()
                serapi_coq_compat[coq_version].add(serapi_version)

        coq_ocaml_compat = self.coq_ocaml_compatibility
        for coq_version in new_coq_versions:
            if coq_version not in coq_ocaml_compat:
                coq_ocaml_compat[coq_version] = set()
            dependencies = OpamAPI.active_switch.get_dependencies(
                "coq",
                coq_version)
            if isinstance(dependencies, LogicalPF):
                dependencies = typing.cast(
                    List[PackageFormula],
                    dependencies.to_conjunctive_list())
            else:
                dependencies = [dependencies]
            if not OpamVersion.less_than(coq_version, "8.17.0"):
                try:
                    # bandaid in lieu of constructing a general solution
                    # with a dependency graph
                    # Coq 8.17 introduced coq-core package, which
                    # transitively introduces a dependency on ocaml
                    core_dependencies = OpamAPI.active_switch.get_dependencies(
                        "coq-core",
                        coq_version)
                except CalledProcessError:
                    core_dependencies = []
                else:
                    if isinstance(core_dependencies, LogicalPF):
                        core_dependencies = typing.cast(
                            List[PackageFormula],
                            core_dependencies.to_conjunctive_list())
                    else:
                        core_dependencies = [core_dependencies]
                dependencies.extend(core_dependencies)
            ocaml_constraint = None
            for dependency in dependencies:
                if (isinstance(dependency,
                               PackageConstraint)
                        and dependency.package_name == 'ocaml'):
                    ocaml_constraint = dependency.version_constraint
                    break
            assert ocaml_constraint is not None
            for ocaml_version in ocaml_constraint.filter_versions(
                    sorted_ocaml_versions):
                ocaml_version = str(ocaml_version)
                coq_ocaml_compat[coq_version].add(ocaml_version)

    def are_serapi_coq_compatible(
            self,
            coq_version: Optional[Union[str,
                                        Version]],
            serapi_version: Optional[Union[str,
                                           Version]]) -> bool:
        """
        Return whether the given Coq and SerAPI versions are compatible.
        """
        if coq_version is not None and not isinstance(coq_version, str):
            coq_version = str(coq_version)
        if serapi_version is not None and not isinstance(serapi_version, str):
            serapi_version = str(serapi_version)
        return (
            coq_version is None or serapi_version is None or (
                coq_version in self.serapi_coq_compatibility and serapi_version
                in self.serapi_coq_compatibility[coq_version]))

    def are_coq_ocaml_compatible(
            self,
            coq_version: Optional[Union[str,
                                        Version]],
            ocaml_version: Optional[Union[str,
                                          Version]]) -> bool:
        """
        Return whether the given Coq and OCaml versions are compatible.
        """
        if coq_version is not None and not isinstance(coq_version, str):
            coq_version = str(coq_version)
        if ocaml_version is not None and not isinstance(ocaml_version, str):
            ocaml_version = str(ocaml_version)
        return (
            coq_version is None or ocaml_version is None or (
                coq_version in self.coq_ocaml_compatibility
                and ocaml_version in self.coq_ocaml_compatibility[coq_version]))

    @cachedmethod
    def get_serapi_version(self,
                           coq_version: Optional[Union[str,
                                                       Version]]
                           ) -> Optional[str]:
        """
        Get the latest compatible SerAPI version for a Coq version.

        Parameters
        ----------
        coq_version : Optional[str]
            A version of Coq.

        Returns
        -------
        Optional[str]
            The latest version of SerAPI compatible with `coq_version`.
        """
        if coq_version is None:
            return None
        elif not isinstance(coq_version, str):
            coq_version = str(coq_version)
        serapi_versions = [
            OCamlVersion.parse(v)
            for v in self.serapi_coq_compatibility[coq_version]
        ]
        if serapi_versions:
            return str(max(serapi_versions))
        else:
            raise RuntimeError(
                f"Unable to find any SerAPI version supporting Coq={coq_version}."
            )


# precompute version information to avoid lengthy startup times
try:
    version_info = typing.cast(
        VersionInfo,
        io.load(DATA_FILE,
                io.Fmt.yaml,
                clz=VersionInfo))
except FileNotFoundError:
    version_info = VersionInfo()
io.dump(DATA_FILE, version_info, io.Fmt.yaml)
