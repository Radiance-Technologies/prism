"""
Module to define and create project graph.
"""
import json
import os
from importlib.machinery import FileFinder
from pathlib import Path
from typing import Dict, List, Set, Tuple

import networkx as nx
from tqdm import tqdm

from prism.project import ProjectDir, SentenceExtractionMethod
from prism.project.graph.node import (
    EdgeType,
    LibraryAlias,
    LogicalName,
    NodeId,
    NodeIdSet,
    Project,
    ProjectCoqDependency,
    ProjectCoqLibrary,
    ProjectCoqLibraryRequirement,
    ProjectExtractedIQR,
    ProjectFile,
    ProjectNode,
)
from prism.project.graph.node.find import NodeFinder
from prism.project.graph.node.iqr import IQRFlag, extract_from_file
from prism.project.graph.node.type import EdgeIdSet, NodeType, ProjectFileType
from prism.project.metadata.storage import Context, Revision
from prism.project.util import name_variants


class ProjectGraph(nx.MultiDiGraph):
    """
    A graph structure that connects project components.
    """
    node_types: List[ProjectNode] = [
        Project,
        ProjectFile,
        ProjectCoqLibrary,
        LibraryAlias,
        ProjectCoqLibraryRequirement,
        ProjectExtractedIQR,
        ProjectCoqDependency,
    ]

    def __init__(self, *args, **kwargs):
        super(ProjectGraph, self).__init__(*args, **kwargs)
        self._roots: Dict[NodeId,
                          Project] = {}
        self._root_variants: Dict[NodeId,
                                  Set[str]] = {}

    @property
    def pointer(self):
        """
        Return a node id that is currently being stored.
        """
        return self._internal_pointer

    @pointer.setter
    def pointer(self, value):
        """
        Set the node id that is currently being stored.
        """
        self._internal_pointer = value

    @property
    def roots(self):
        root_nodes = NodeType.root.find_nodes(self)
        roots = []
        for node in root_nodes:

            if node not in self._roots:
                self._roots[node] = Project.init_from_node(self, node)
            roots.append(self._roots[node])
        return roots

    def _add_project_node(self,
                          project_node: ProjectNode,
                          *args,
                          **kwargs) -> Tuple[NodeIdSet,
                                             EdgeIdSet]:
        """
        Add project node unless it exists in the graph.
        """
        if not self.has_node(project_node.node):
            added_nodes, added_edges = project_node.add_to_graph(self, *args, **kwargs)
        else:
            added_nodes, added_edges = set(), set()

        return added_nodes, added_edges

    def _add_node(self, node, roots, *args, **kwargs):
        expected_name = node.context.revision.project_source.project_name
        if isinstance(node, ProjectFile):
            path = node.project_file_path
        else:
            path = node.project_path

        root = None
        unique = False
        for r in roots:

            name = r.context.revision.project_source.project_name
            variants = self.root_variants[r.node]

            if expected_name == name:
                root = r
            elif (expected_name != name
                  and any(part in variants for part in path.parts)):
                unique = False

        if root is None:
            raise ValueError("Cannot find a match project root in graph.")

        if unique:
            if not self.has_node(node.node):
                added_nodes, added_edges = node.add_to_graph(self, *args, **kwargs)
            else:
                added_nodes, added_edges = set(), set()
        return added_nodes, added_edges

    def _add_nodes(self,
                   nodes: ProjectNode,
                   *args,
                   **kwargs) -> Tuple[NodeIdSet,
                                      EdgeIdSet]:
        """
        Add project node even if it already exist in the node set.
        """
        roots = self.roots
        added_nodes, added_edges = set(), set()
        for node in nodes:
            new_nodes, new_edges = self._add_node(node, roots, *args, **kwargs)
            added_nodes = added_nodes.union(new_nodes)
            added_edges = added_edges.union(new_edges)
        return added_nodes, added_edges

    def add_dependencies(self, node_id):
        """
        Add project dependency nodes.

        This will also connect dependency nodes to the root node,
        requirement nodes, and any matching libraries. Additionally the
        point will be set
        """
        roots = self.roots
        added_nodes = set()
        added_edges = set()

        for req_node in ProjectCoqLibraryRequirement.nodes_from_graph(self):
            requirement = ProjectCoqLibraryRequirement.init_from_node(
                self,
                req_node)

            root = Project(requirement.context, requirement.project_path)
            if root.node != node_id:
                continue

            root = Project(
                requirement.context,
                requirement.project_path,
            )
            dependency = ProjectCoqDependency.from_parent(
                root,
                logical_name=requirement.requirement)
            if not self.has_node(dependency.node):
                new_nodes, new_edges = self._add_node(
                    dependency,
                    roots,
                    True,
                    True
                )
                added_nodes = added_nodes.union(new_nodes)
                added_edges = added_edges.union(new_edges)
                added_edges = added_edges.union(
                    EdgeType.DependencyToRequirement.add_edge(
                        self,
                        dependency.node,
                        requirement.node))
            dependency_name = dependency.logical_name
            for library in self.match_dependency_to_library(dependency):
                added_edges = added_edges.union(
                    EdgeType.DependencyToLibrary.add_edge(
                        self,
                        dependency.node,
                        library.node))
        return added_nodes, added_edges

    def add_path(self, path: Path):
        """
        Add a path as a ProjectFile under a root node.

        If the path a subpath of another root path

        Parameters
        ----------
        path : Path
            A subpath of some root node.

        Raises
        ------
        ValueError
            _description_
        """
        path = Path(path)
        file_type = ProjectFileType.infer(path)

        if not file_type:
            return False

        roots = self.roots
        root = None
        for r in roots:
            if path.is_relative_to(r.project_path):
                root = r

        if root is None:
            raise ValueError("Cannot find a match project root in graph.")

        file_node = ProjectFile.from_super(
            root,
            project_file_path=path,
            project_file_type=file_type)
        return self._add_node(file_node, roots, True, True)

    def add_paths(self, *paths: Path):
        """
        Add a path as a ProjectFile under a root node.

        If the path a subpath of another root path

        Parameters
        ----------
        path : Path
            A subpath of some root node.

        Raises
        ------
        ValueError
            _description_
        """
        added_nodes, added_edges = set(), set()
        for path in paths:
            new_nodes, new_edges = self.add_path(path)
            added_nodes = added_nodes.union(new_nodes)
            added_edges = added_edges.union(new_edges)
        return added_nodes, added_edges

    def add_iqrs(self, node_id: NodeId):
        roots = self.roots
        added_nodes, added_edges = set(), set()
        for coqproject_node in ProjectFileType.coqproject.find_files(self):
            coqproject = ProjectFile.init_from_node(self, coqproject_node)

            root = Project(coqproject.context, coqproject.project_path)
            if root.node != node_id:
                continue

            iqrs = extract_from_file(str(coqproject.project_file_path))
            for iqr_flag in iqrs:
                # Ignore -I flag since many projects may not even use it!
                if iqr_flag is IQRFlag.I:
                    continue
                # Create the iqr node and add it to the graph.
                for iqr_path, iqr_name in iqrs[iqr_flag]:
                    iqr_node = ProjectExtractedIQR.from_parent(
                        coqproject,
                        Path(iqr_path),
                        iqr_name,
                        iqr_flag)
                    if not any(iqr_name in self._root_variants[other_id]
                               and other_id != node_id for other_id in roots):
                        new_nodes, new_edges = self._add_node(
                            iqr_node,
                            roots,
                            True,
                            True,
                            edgetypes=(
                                EdgeType.ChildToParent,
                                EdgeType.ParentToChild,
                                EdgeType.IQRToProjectFile,
                            )
                        )
                        added_nodes = added_nodes.union(new_nodes)
                        added_edges = added_edges.union(new_edges)
        return added_nodes, added_edges

    def add_libraries(self):
        roots = self.roots
        added_nodes, added_edges = set(), set()
        for node in ProjectFileType.coqdirectory.find_files(self):
            file = ProjectFile.init_from_node(self, node)
            library = ProjectCoqLibrary.init_with_local_name(file)
            new_nodes, new_edges = self._add_node(
                        library,
                        roots,
                        True,
                        True,
                        edgetypes=(
                            EdgeType.ChildToParent,
                            EdgeType.ParentToChild,
                        )
                    )
            added_nodes = added_nodes.union(new_nodes)
            added_edges = added_edges.union(new_edges)
        return added_nodes, added_edges

    def add_library_aliases(self, node_id):
        roots = self.roots
        added_nodes = set()
        added_edges = set()
        for node in ProjectExtractedIQR.nodes_from_graph(self):
            iqr = ProjectExtractedIQR.init_from_node(self, node)
            root = Project(iqr.context, iqr.project_path)
            if root.node != node_id:
                continue
            library_iter = FileFinder.find_effected_libraries_by_iqr(self, node)
            for _, library_node, alias in library_iter:

                library = ProjectCoqLibrary.init_from_node(self, library_node)
                alias = LibraryAlias.from_super(library, logical_name=alias)
                new_nodes, new_edges = self._add_node(
                            alias,
                            roots,
                            True,
                            True,
                            edgetypes=(
                                EdgeType.ChildToParent,
                                EdgeType.ParentToChild,
                            )
                        )
                added_nodes = added_nodes.union(new_nodes)
                added_edges = added_edges.union(new_edges)
                alias_edges = EdgeType.LibraryAliasToLibrary.add_edge(
                    self,
                    alias.node,
                    library.node)
                added_edges = added_edges.union(alias_edges)
        return added_nodes, added_edges

    def add_requirements(self, node_id):
        roots = self.roots
        added_nodes, added_edges = set(), set()
        for node in ProjectCoqLibrary.nodes_from_graph(self):
            library = ProjectCoqLibrary.init_from_node(self, node)
            root = Project(library.context, library.project_path)
            if root.node != node_id:
                continue
            project = ProjectDir(
                str(self.project_root),
                sentence_extraction_method=SentenceExtractionMethod.HEURISTIC)
            parser = project.sentence_extraction_method.parser()
            sentences = project.__class__.extract_sentences(
                project.get_file(str(library.project_file_path)),
                glom_proofs=False,
                sentence_extraction_method=project.sentence_extraction_method)
            stats = parser._compute_sentence_statistics(sentences)
            for requirement in stats.requirements:
                requirement = ProjectCoqLibraryRequirement.from_parent(
                    library,
                    requirement=LogicalName(requirement))
                new_nodes, new_edges = self._add_node(
                            requirement,
                            roots,
                            True,
                            True,
                            edgetypes=(
                                EdgeType.ChildToParent,
                                EdgeType.ParentToChild,
                            )
                        )
                added_nodes = added_nodes.union(new_nodes)
                added_edges = added_edges.union(new_edges)
        return added_nodes, added_edges

    def add_root(self, root: Project) -> Tuple[NodeIdSet, EdgeIdSet]:
        """
        Add a new project root to the graph.
        """
        if not self.has_node(root.node):
            added_nodes, added_edges = root.add_to_graph(self)
            self._roots[root.node] = root
            self._root_variants[root.node] = name_variants(
                root.project_path.stem)
        else:
            added_nodes, added_edges = set(), set()
        return added_nodes, added_edges

    def dump_edges(self, prefix=''):
        dep = 'logical_name'
        req = 'requirement'
        lib = 'logical_name'
        file = 'project_file_path'
        edges = {}
        for edgetype in EdgeType:
            if edgetype is EdgeType.DependencyToLibrary:
                edges["DependencyToLibrary"] = self.jsonify_edges(
                    edgetype,
                    dep,
                    lib)
            elif edgetype is EdgeType.DependencyToRequirement:
                edges["DependencyToRequirement"] = self.jsonify_edges(
                    edgetype,
                    dep,
                    req)
        with open(f"{prefix}_edges.json", "w") as f:
            json.dump(edges, f)

    def dump_aliases(self, prefix=''):
        alias_dict = {}
        for node in ProjectCoqLibrary.nodes_from_graph(self):
            lib_name = self.resolve_node_str(node, 'logical_name', False)
            lib = ProjectCoqLibrary.init_from_node(self, node)
            lib_path = str(lib.super.data['relative'])
            if lib_path not in alias_dict:
                alias_dict[lib_path] = []
            alias_dict[lib_path].append(lib_name)
            for alias in NodeFinder.library_aliases(self, node):
                alias = self.resolve_node_str(alias, 'logical_name', False)
                alias_dict[lib_path].append(alias)
        with open(f"{prefix}_aliases.json", "w") as f:
            json.dump(alias_dict, f)

    def dump_requirements(self, prefix=''):
        req_dict = {}
        for node in ProjectCoqLibraryRequirement.nodes_from_graph(self):

            req_name = self.resolve_node_str(node, 'requirement', False)
            req = ProjectCoqLibraryRequirement.init_from_node(self, node)
            req_path = str(req.project_file_path)

            if req_path not in req_dict:
                req_dict[req_path] = {}
            if req_name not in req_dict[req_path]:
                req_dict[req_path][req_name] = []

            for dependency in NodeFinder.requirement_resolution(self, node):
                dependency = self.resolve_node_str(
                    dependency,
                    'logical_name',
                    False)
                req_dict[req_path][req_name].append(dependency)

        with open(f"{prefix}_requirements.json", "w") as f:
            json.dump(req_dict, f)

    def dump_dependencies(self, directory):
        unknown_deps = []
        iqrs = set()
        projects = {}
        local, cross, unknown = self.separate_dependencies()
        for dep_type, dep_list in dict(local=local, cross=cross, unknown=unknown).items():
            for dependency, root, other_root in dep_list:
                project = root.context.revision.project_source.project_name
                logical = dependency.logical_name
                if project not in projects:
                    projects[project] = {
                        'local': [],
                        'cross': [],
                        'unknown': [],
                        'projects': []
                    }
                projects[project][dep_type].append(logical)
                if other_root is not None:
                    other = other_root.context.revision.project_source.project_name
                    projects[project][dep_type]['projects'].append(other)

        for project, project_deps in projects.items():
            basename = f"{project}_dependencies.json"
            path = os.path.join((directory, basename))
            with open(path, "w") as f:
                json.dump(project_deps, f)

    def dump_libaries(self, prefix=''):
        libraries = set()
        full_paths = set()
        iqrs = set()

        proj_dirs = set(next(os.walk(self.project_root.parent))[1])
        proj_dirs.remove(self.project_root.stem)
        projects = proj_dirs
        for p in iter(proj_dirs):
            projects = projects.union(name_variants(p))
        project_dirs = []

        types_ = [ProjectFileType.coqfile, ProjectFileType.coqdirectory]
        for file_node in ProjectFile.nodes_from_graph(
                self,
                lambda n,
                d: d['filetype'] in types_):
            relative = self.nodes[file_node]['relative']
            if relative.stem in projects or any(relative.is_relative_to(p)
                                                for p in project_dirs):
                project_dirs.append(relative)
                continue
            name = LogicalName.from_physical_path(relative)
            if name.startswith('.'):
                continue
            name = LogicalName(name)
            full_paths.add(str(name))

        for node in ProjectExtractedIQR.nodes_from_graph(self):
            iqr_name = self.resolve_node_str(node, 'iqr_name', False)
            if any(iqr_name.startswith(p) for p in projects):
                continue
            iqrs.add(iqr_name)

        for node in ProjectCoqLibrary.nodes_from_graph(self):
            lib_name = self.resolve_node_str(node, 'logical_name', False)
            if any(lib_name.startswith(p) for p in projects):
                continue
            libraries.add(lib_name)
        for node in LibraryAlias.nodes_from_graph(self):
            lib_name = self.resolve_node_str(node, 'logical_name', False)
            if any(lib_name.startswith(p) for p in projects):
                continue
            libraries.add(lib_name)
        with open(f"{prefix}_libraries.json", "w") as f:
            json.dump(
                {
                    'iqrs': list(iqrs),
                    'resolved': list(libraries),
                    'guesses': list(full_paths),
                },
                f)

    def separate_dependencies(self):
        cross = []
        local = []
        for dependency in self.init_iter(ProjectCoqDependency):
            dependency_root = Project(
                dependency.context,
                dependency.project_path)
            source_name = dependency_root.context.revision.project_source.project_name
            found = False
            for library_node in EdgeType.DependencyToLibrary.find_target_nodes(
                    self,
                    dependency.node):
                found = True
                library = ProjectCoqLibrary.init_from_node(self, library_node)
                library_root = Project(library.context, library.project_path)
                target_name = library_root.context.revision.project_source.project_name
                if source_name != target_name:
                    cross.append((dependency, dependency_root, library_root))
                else:
                    local.append((dependency, dependency_root, library_root))
            if not found:
                unknown = local.append((dependency, dependency_root))
        return local, cross, unknown

    def jsonify_edges(self, edgetype, s_att, d_attr):
        edges = []
        for src, dst, key in edgetype.find_edges(self):
            src = self.resolve_node_str(src, s_att)
            dst = self.resolve_node_str(dst, d_attr)
            edges.append(
                {
                    'source': str(src),
                    'destination': str(dst),
                    'key': str(key)
                })
        return edges

    def match_dependency_to_library(self, dependency):
        if dependency is None:
            raise ValueError("Dependency is None, cannot find library.")

        def matches_name(dependency, logical_name):
            return (
                (dependency.logical_name == logical_name)
                or (logical_name in dependency.shortnames))

        libraries = ProjectCoqLibrary.nodes_from_graph(
            self,
            lambda n,
            d: matches_name(dependency.logical_name,
                            d['logical_name']),
        )
        aliases = LibraryAlias.nodes_from_graph(
            self,
            lambda n,
            d: matches_name(dependency.logical_name,
                            d['logical_name']),
        )
        libraries = [
            ProjectCoqLibrary.init_from_node(self,
                                             node) for node in libraries
        ]
        libraries.extend(
            NodeFinder.find_library_from_alias(self,
                                               a) for a in aliases)
        return libraries

    def resolve_node_str(self, node, attr, with_type=True):
        value = self.node[node][attr]
        if with_type:
            type_, _ = node.split(": ")
            node_str = f"{type_}: {value}"
        else:
            node_str = f"{value}"
        return node_str

    def init_iter(self, type, **kwargs):
        for node in type.nodes_from_graph(self, **kwargs):
            yield type.init_from_node(self, node)


from multiprocessing import Pool
from re import sub


def create_trees(project_path):
    context = Context(Revision(project_path.stem, '111'), '', '')
    try:
        tree = ProjectGraph(project_path, context)
        add_library_aliases(tree)
        add_project_dependencies(tree)
    except Exception as exc:
        print(project_path)
        print(exc)
        raise exc
    prefix = f"/home/atouchet/projects/PEARLS/dependencies/{project_path.stem}"
    dump_edges(tree, prefix)
    dump_aliases(tree, prefix)
    dump_unknown(tree, prefix)
    dump_requirements(tree, prefix)
    dump_libaries(tree, prefix)


dirs = list(os.listdir("/workspace/datasets/pearls/repos"))
root = Path("/workspace/datasets/pearls/repos")
dirs = [root / Path(d) for d in dirs]

with Pool(40) as p:
    results = list(
        tqdm(
            p.imap(create_trees,
                   dirs),
            total=len(dirs),
            desc="projects",
        ))
    print("dont")
