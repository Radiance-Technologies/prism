"""
Defines a representation of the OPAM file format for packaging.

See https://opam.ocaml.org/doc/Manual.html#Package-definitions for
more information.
"""

import os
from dataclasses import dataclass, field, fields
from itertools import chain
from typing import Any, Dict, List, Optional, Tuple, Union

from prism.util.radpytools.dataclasses import default_field

from .formula import PackageFormula
from .version import Version

Filter = str
URL = str
Email = str
PackageName = str
Checksum = str

CommandSequence = List[Tuple[List[Tuple[str,
                                        Optional[Filter]]],
                             Optional[Filter]]]


@dataclass
class OpamFile:
    """
    An OPAM file describing an installable package.
    """

    opam_version: str = field(init=False)
    """
    The file format version, should be ``"2.0"`` as of this writing.
    """
    name: PackageName
    """
    The name of the package.
    """
    version: str
    """
    The version of the package.
    """
    maintainer: str
    """
    The address of the package maintainer.
    """
    authors: List[str] = default_field(list())
    """
    The original authors of the package.
    """
    license: List[str] = default_field(list())
    """
    The SPDX expression of the license(s) under which the source
    software is available.
    """
    homepage: List[URL] = default_field(list())
    """
    URLs pointing to the homepage for the package.
    """
    doc: List[URL] = default_field(list())
    """
    URLs pointing to package documentation.
    """
    bug_reports: List[URL] = default_field(list())
    """
    URLs pointing to bug reporting and tracking sites.
    """
    dev_repo: URL = ""
    """
    The URL of the package's source repository.
    """
    tags: List[str] = default_field(list())
    """
    An optional list of semantic tags used to classify the package.
    """
    patches: List[Tuple[os.PathLike, Optional[Filter]]] = default_field(list())
    """
    A list of files relative to the project source root that are
    applied sequentially with the ``patch`` command.
    Each file may be paired with a filter.
    """
    substs: List[os.PathLike] = default_field(list())
    """
    A list of files relative to the project source root to be
    generated from their ``.in`` counterparts, with variable
    interpolations expanded.
    """
    build: CommandSequence = default_field(list())
    """
    Build commands as distinctly listed arguments with optional filters.
    """
    install: CommandSequence = default_field(list())
    """
    The set of commands that will be run to install the package.
    """
    build_doc: CommandSequence = default_field(list())
    """
    Deprected. Use `build` and `install` instead with ``with-doc``
    filters.
    """
    build_test: CommandSequence = default_field(list())
    """
    Deprected. Use `build` and `install` instead with ``with-test``
    filters.
    """
    run_test: CommandSequence = default_field(list())
    """
    Instructions for running package tests.
    """
    remove: CommandSequence = default_field(list())
    """
    Commands to run before removing the package.
    """
    depends: Optional[PackageFormula] = None
    """
    A formula describing this package's external, required dependencies.
    """
    depopts: Optional[PackageFormula] = None
    """
    A formula describing this package's external, optional dependencies.
    """
    conflicts: Optional[PackageFormula] = None
    """
    A formula describing packages with which this package has conflicts.
    """
    conflict_class: List[str] = default_field(list())
    """
    Alternative way of specifying conflicts.

    Packages sharing a conflict class are considered incompatible.
    """
    depexts: List[Tuple[List[str], Filter]] = default_field(list())
    """
    Dependencies external to OPAM filtered, for example, by operating
    system or system architecture.
    """
    messages: List[Tuple[str, Filter]] = default_field(list())
    """
    Optional messages to show the user upon package installation.
    """
    post_messages: List[Tuple[str, Filter]] = default_field(list())
    """
    Optional messages to show the user after installation (or failure).
    """
    available: List[Filter] = default_field(list())
    """
    Used to add constraints to the OS and other global variables, e.g.,
    to disable package installation if the filters do no evaluate to
    True.
    """
    flags: List[str] = default_field(list())
    """
    Package flags that may alter package behavior.

    See OPAM manual for acceptable flags.
    """
    features: Dict[str,
                   Tuple[List[Tuple[PackageName,
                                    PackageFormula]],
                         str]] = default_field(dict())
    """
    Bind identifiers to dependency formulas and descriptions.
    """
    synopsis: str = ""
    """
    A short (one line) description of the package.
    """
    description: str = ""
    """
    A long description of the package.
    """
    url: URL = ""
    """
    The URL where the package source can be obtained.
    """
    setenv: Dict[str, str] = default_field(dict())
    """
    Environment variable updates applied upon installing the package and
    exported via ``opam env``.
    """
    build_env: Dict[str, str] = default_field(dict())
    """
    Environment variable updates applied upon building, installing, or
    removing the package.
    """
    extra_source: Optional[Tuple[os.PathLike, URL]] = None
    """
    The name of a file to which additional source data should be
    downloaded from the given URL.
    """
    extra_files: List[List[Tuple[os.PathLike,
                                 Checksum]]] = default_field(list())
    """
    Optional list of files with their checksums for integrity checks.
    """
    pin_depends: List[List[Tuple[PackageName, URL]]] = default_field(list())
    """
    When pinning this package, also pin those listed in this field.
    """
    extra_fields: Dict[str, str] = default_field(dict())
    """
    Arbitrary extra fields, each ultimately prepended with ``x-``.
    """

    def __post_init__(self):
        """
        Set additional defaults.
        """
        self.opam_version = "2.0"
        if isinstance(self.version, Version):
            self.version = str(self.version)

    def __str__(self) -> str:
        """
        Get the contents of the formatted file.
        """
        # TODO: Properly format all fields with special-case handling.
        file_str = []
        for (field_name,
             _field_type,
             field_value) in chain([(f.name,
                                     f.type,
                                     getattr(self,
                                             f.name))
                                    for f in fields(self)
                                    if f.name != "extra_fields"],
                                   [(f"x-{k}",
                                     str,
                                     v) for k,
                                    v in self.extra_fields.items()]):
            field_str = []
            if field_value:
                field_str.append(f'{field_name.replace("_", "-")}:')
                OpamFile._str_value(field_str, field_value)
                if field_name == "url" or field_name == "extra_source":
                    field_str[-1] = '{%s}' % field_str[-1]
                file_str.append(' '.join(field_str))
        return '\n'.join(file_str)

    @staticmethod
    def _str_value(
            field_str: List[str],
            field_value: Union[Tuple[Any,
                                     ...],
                               List[Any],
                               Dict[str,
                                    Any]]) -> None:

        if isinstance(field_value, (list, dict)):
            field_str.append("[")
            if isinstance(field_value, dict):
                for k, v in field_value.items():
                    OpamFile._str_value(field_str, (k, v))
            else:
                for v in field_value:
                    OpamFile._str_value(field_str, v)
            field_str.append("]")
        elif isinstance(field_value, tuple):
            for v in field_value:
                OpamFile._str_value(field_str, v)
        elif isinstance(field_value, str):
            field_str.append(f'"{field_value}"')
        else:
            field_str.append(str(field_value))
