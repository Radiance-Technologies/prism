#!/usr/bin/env python
# coding: utf-8

# In[1]:

from genericpath import exists
import json
from multiprocessing.sharedctypes import Value
import networkx as nx
from prism.project.build.library.component.logical import LogicalName, LogicalGraphType
from prism.project.build.library.component.physical import PhysicalPath
from enum import Enum, auto, Flag
from networkx import MultiGraph, DiGraph
from itertools import accumulate, chain, compress, zip_longest
from functools import reduce
from pathlib import Path
from typing import OrderedDict, Tuple, Sequence
import re
from tqdm import tqdm
from dataclasses import dataclass, asdict, fields
from radpytools.dataclasses import default_field, immutable_dataclass
from radpytools.builtins import cachedmethod
from typing import Optional, Set, Dict, Iterable, Literal, Any, Hashable, Callable, List, Union
import typing
from functools import partial
from prism.project.build.library.component.flags import IQRFlag, extract_from_file
from prism.project.util import name_variants
from typing import TypeVar, Type, Generic
import types
from abc import ABC, abstractmethod, abstractclassmethod
import os
from dataclasses import astuple, field, dataclass


def matches_variant(value, variant):
    split = value.split('.')
    lead = split[0]
    if len(split) > 1:
        matches = split[0].startswith(variant)
    else:
        matches = (lead == variant)
    return matches



coq_standard = open("coq_standard.txt", "r").readlines()
coq_standard = [lib.strip() for lib in coq_standard]
coq_ext = open("coq_ext.txt", "r").readlines()
coq_ext = [lib.strip() for lib in coq_ext]


skip = [
    "Omega",
    "Events",
    "Types",
    "Vector",
    "Max",
    "Ensembles",
    "Orders",
    "Sets",
    "Functions",
    "Tactics",
    "Memory",
    "Reals",
    "Extraction",
    "Relations",
    "main",
    "Misc",
    "Syntax",
    "util",
    "Monad",
    "Utils",
    "misc",
    "Lt",
    "BinNums",
    "Sorting",
    "State",
    "Functor",
    "list",
    "Heaps",
    "Values",
    "base",
    "Ascii",
    "Even",
    "Div",
    "Plus",
    "Matrix",
    "Category",
    "Map",
    "Image",
    "Behaviors",
    "Separation",
    "Rules",
    "syntax",
    "Decidable",
    "common",
    "Compare_dec",
    "Wf",
    "Fin",
    "Monoid",
    "Graph",
    "Main",
    "Core",
    "Registers",
    "Equivalence",
    "Test",
    "Simulation",
    "Lia",
    "Compiler",
    "Lattice",
    "Le",
    "Permutation",
    "Nat",
    "Semantics",
    "ListSet",
    "LibTactics",
    "Util",
    "Option",
    "Axioms",
    "Equality",
    "Integers",
    "Basics",
    "Ring",
    "Classical",
    "Common",
    "Notations",
    "Coqlib",
    "Maps",
    "tactics",
    "Program",
    "String",
    "Setoid",
    "Morphisms",
    "Bool",
    "List",
    "Words",
    "Errors",
    "Summation",
    "Tutorial",
    "Hierarchy",
    "Extensions",
    "Functor.Product",
    "Term",
    "nominal",
    "utils",
    "Definitions",
    "Union",
    "Tactic",
    "Reals.Ratan",
    "make",
    "Value",
    "Source",
    "Factorization",
    "Descent",
    "Groups",
    "machine",
    "Reg",
    "Var",
    "Fresh",
    "Reachability",
    "Theory",
    "Refinement",
    "RealAux",
    "Sound",
    "Imp",
    "Examples",
    "Utility",
    "Filter",
    "general_tactics",
    "Zadd",
    "Substitution",
    "prime",
    "monoid",
    "properties",
    "digraph",
    "SmallStep",
    "Zle",
    "field",
    "Zgcd"
    "Sums",
    "discrete",
    "Qfield",
    "Relations_1",
    "Relations_1_facts",
    "gcd",
    "poly",
    "matrix",
    "ps",
    "union",
    "concrete",
    "time_clocks",
]


@dataclass
class LibraryContext:
    """

    """
    level: int
    project_names: List[str]
    iqrs: Set[LogicalName]
    resolved: Set[LogicalName]
    lazy: Set[LogicalName]


@dataclass
class StandardContext(LibraryContext):
    level: int = -1
    project_names: List[str] = field(default_factory=lambda: ['Coq'] + list(name_variants('Coq')))
    iqrs: Set[LogicalName] = field(default_factory=set)
    resolved: Set[LogicalName] = field(default_factory=lambda: coq_standard)
    lazy: Set[LogicalName] = field(default_factory=set)

    def __post_init__(self):
        self.level = -1


@dataclass
class ExternalContext(LibraryContext):
    level: int
    project_names: List[str] = field(default_factory=list)
    iqrs: Set[LogicalName] = field(default_factory=set)
    resolved: Set[LogicalName] = field(default_factory=set)
    lazy: Set[LogicalName] = field(default_factory=set)

    def __post_init__(self):
        self.project_names = [coq_ext[self.level]]


class MethodType(Enum):
    equality = auto()
    relative = auto()
    root = auto()
    variant = auto()

    @property
    def match(self):

        def auto_cast(*args):
            return tuple(
                arg if isinstance(arg, LogicalName) else LogicalName(arg) for arg in args
            )

        if self.name == 'equality':
            def match(
                query: LogicalName,
                reference: LogicalName
            ):
                query, reference = auto_cast(query, reference)
                return query == reference
        elif self.name == 'relative':
            def match(
                query: LogicalName,
                reference: LogicalName,
            ):
                query, reference = auto_cast(query, reference)
                return query.is_relative_to(reference)
        elif self.name == 'root':

            def match(
                query: LogicalName,
                reference: LogicalName
            ):
                query, reference = auto_cast(query, reference)
                n = len(reference.parts)
                if len(query.parts) > n:
                    return False
                else:
                    return query.parts[:n] == reference.parts

        elif self.name == 'variant':

            def match(
                query: LogicalName,
                variant: str
            ):
                query, = auto_cast(query)
                if len(query.parts) > 1:
                    matches = query.parts[0] == variant
                else:
                    matches = str(query).startswith(str(variant))
                return matches
        return match


class MatchType(Enum):
    project_name = auto()
    iqr = auto()
    resolved = auto()
    lazy = auto()
    failed = auto()

    def find_match(self, query: LogicalName, context: LibraryContext, all: bool = False):

        matches = set()
        if self.name == 'project_name':
            match_variant = MethodType.variant.match
            for variant in context.project_names:
                if match_variant(query, variant):
                    matches.add((variant, context.project_names[0]))
                    if not all:
                        break
        elif self.name == 'iqr':
            match_iqr = MethodType.root.match
            for iqr in context.iqrs:
                if match_iqr(query, iqr):
                    matches.add((iqr, context.project_names[0]))
                    if not all:
                        break
        elif self.name in ['resolved', 'lazy']:
            match_name = MethodType.equality.match
            for name in context.resolved:
                if match_name(query, name):
                    matches.add((name, context.project_names[0]))
                    if not all:
                        break
        elif self.name == 'failed':
            matches = set()
        return matches


class LibraryType(Enum):
    local = auto()
    standard = auto()
    external_library = auto()
    external_project = auto()
    unknown = auto()


MatchTypeOrder = tuple(
    match_type for match_type in MatchType
)
NameOrder = (
    LibraryType.local,
    LibraryType.standard,
    LibraryType.external_library,
    LibraryType.external_project,
)
IQROrder = (
    LibraryType.local,
    LibraryType.external_project,
)
ResolvedOrder = (
    LibraryType.local,
    LibraryType.standard,
)
LazyOrder = (
    LibraryType.local,
)
ResolutionOrderMap = {
    MatchType.project_name: NameOrder,
    MatchType.iqr: IQROrder,
    MatchType.resolved: ResolvedOrder,
    MatchType.lazy: LazyOrder,
    MatchType.failed: (LibraryType.unknown,),

}

STANDARD_CONTEXT = StandardContext()
EXTERNAL_CONTEXT = [ExternalContext(i) for i in range(len(coq_ext))]


class Resolver:

    def __init__(
        self,
        ctx_external_projects: List[LibraryContext],
        ctx_standard: LibraryContext = STANDARD_CONTEXT,
        ctx_external_libs: List[LibraryContext] = EXTERNAL_CONTEXT,
    ):
        self.ctx_external_projects = ctx_external_projects
        self.ctx_standard = ctx_standard
        self.ctx_external_libs = ctx_external_libs

    def _lowest(self, inputs):
        lowest_idx = None
        matches = []
        for idx, match in inputs:
            if lowest_idx is None:
                lowest_idx = idx
            if idx > lowest_idx:
                continue
            if idx < lowest_idx:
                matches = []
                lowest_idx = idx
            matches.append(match)

        return lowest_idx, matches

    def resolve_requirement(self, ctx_local: LibraryContext, requirement: LogicalName):
        matches = []
        match_found = False
        for midx, match_type in enumerate(MatchTypeOrder):
            matches_ = []
            if match_found:
                continue
            for lidx, lib_type in enumerate(ResolutionOrderMap[match_type]):
                matches__ = []
                if match_found:
                    continue
                if lib_type is LibraryType.local:
                    matches__ = list(match_type.find_match(requirement, ctx_local))
                elif lib_type is LibraryType.standard:
                    matches__ = list(match_type.find_match(requirement, self.ctx_standard))
                elif lib_type is LibraryType.external_library:
                    for external_lib in self.ctx_external_libs:
                        lib_matches = list(match_type.find_match(requirement, external_lib))
                        matches__.extend(list(lib_matches))
                elif lib_type is LibraryType.external_project:
                    for project_lib in self.ctx_external_projects:
                        lib_matches = list(match_type.find_match(requirement, project_lib))
                        matches__.extend(list(lib_matches))
                elif lib_type is LibraryType.unknown:
                    continue

                if len(matches__) > 0:
                    matches__ = [(lidx, match) for match in matches__]
                    matches_.extend(matches__)
                    match_found = True

            if len(matches_) > 0:
                matches_ = [(midx, match) for match in matches_]
                matches.extend(matches_)
        try:
            if len(matches) > 0:
                midx, lowest = self._lowest(matches)
                match_type = MatchTypeOrder[midx]
                lidx, match = self._lowest(lowest)
                lib_type = ResolutionOrderMap[match_type][lidx]
                match = [m if isinstance(m, tuple) else (None, m) for m in match]
            else:
                match_type = MatchType.failed
                lib_type = LibraryType.unknown
                match = None
        except Exception as exc:
            raise exc
        return match, match_type, lib_type

    def __call__(self, ctx_local: LibraryContext, requirement: LogicalName):
        return self.resolve_requirement(ctx_local, requirement)


def cross_check(item):
    """
    Check for all requirements that crosses project boundaries
    """
    local_name, jsons_data = item
    local_data = jsons_data.pop(local_name)
    local_context = local_data['context']
    requirements = local_data['requirements']
    contexts = [data['context'] for data in jsons_data.values()]
    resolve = Resolver(contexts)
    cross = []
    libraries = {}
    for requirement in requirements:
        (matches,
         match_type,
         lib_type,) = resolve.resolve_requirement(local_context, requirement)
        if lib_type is not LibraryType.external_project:
            continue
        for library, project in matches:
            if project is not None:
                if project not in cross:
                    cross.append(project)
                if library not in libraries:
                    libraries[library] = {'match_types': [], 'lib_types': [], 'count': 0}
                libraries[library]['match_types'].append(match_type)
                libraries[library]['lib_types'].append(lib_type)
                libraries[library]['count'] += 1
    return local_name, cross, libraries


def load_json(item):
    """
    Load a relative project json files.
    """
    level, name = item
    libs = f"/home/atouchet/projects/PEARLS/dependencies/{name}_libraries.json"
    reqs = f"/home/atouchet/projects/PEARLS/dependencies/{name}_requirements.json"
    with open(str(libs), "r") as f:
        libs = json.load(f)
    with open(str(reqs), "r") as f:
        reqs = json.load(f)

    result = {
        'libraries': {},
        'requirements': []
    }
    modified = {}
    for key, values in libs.items():
        modified[key] = []
        for value in values:
            value: str = value
            if value.startswith('.'):
                continue
            if value != '' and value != ' ':
                modified[key].append(value)
            else:
                continue
    result['libraries'].update(modified)

    modified = []
    for key, req_dict in reqs.items():
        for req in req_dict:
            if req != '' and req != ' ':
                modified.append(req)
            else:
                continue
    result['requirements'].extend(modified)
    names = name_variants(name)
    if name in names:
        names.remove(name)
    names = [name] + list(names)
    iqrs = result['libraries']['iqrs']
    resolved = result['libraries']['resolved']
    lazy = result['libraries'].get('last', result['libraries'].get('guesses', set()))
    context = LibraryContext(len(coq_ext) + level, names, iqrs, resolved, lazy)
    return name, {'requirements': result['requirements'], 'context': context}


from multiprocessing import Pool


dirs = list(os.listdir("/workspace/datasets/pearls/repos"))
root = Path("/workspace/datasets/pearls/repos")
dirs = [root / Path(d) for d in dirs]

root = Path("/home/atouchet/projects/PEARLS/dependencies")
projects = {}
for file in root.glob("*_libraries.json"):
    project = str(file.stem).split('_libraries')[0]
    projects[project] = file

items = [(key, projects) for key in projects]

with Pool(40) as p:
    jsons = list(
        tqdm(
            p.imap(load_json,
                   list(enumerate(projects.keys()))),
            total=len(dirs),
            desc="jsons",
        ))

jsons = dict(jsons)

items = [(key, jsons) for key in jsons]

with Pool(40) as p:
    crosses = list(
        tqdm(
            p.imap(cross_check,
                   items),
            total=len(dirs),
            desc="projects",
        ))
    print("dont")

all_libraries = []
all_crosses = {}
all_counts = {}

for name, cross, libraries in crosses:
    names = list(libraries.keys())
    all_libraries.extend(names)
    if len(cross) > 0:
        all_crosses[name] = cross

counted = {lib: all_libraries.count(lib) for lib in all_libraries}
counted = dict(sorted(counted.items(), key=lambda item: item[1]))
with open("counted.json", "w") as f:
    json.dump(counted, f)

with open("crosses.json", "w") as f:
    json.dump(all_crosses, f)

variants = [name_variants(project) for project in projects]
reduced_counted = {}
for name in counted:
    first = name.split('.')[0]
    if not (
        any(first in project for project in variants)
        or any(first.lower() in project for project in variants)
    ):
        reduced_counted[name] = counted[name]

with open("reduced_counted.json", "w") as f:
    json.dump(reduced_counted, f)
