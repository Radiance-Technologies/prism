"""
Module for base node in project graph.
"""
import os
from copy import copy
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Dict, Set, Tuple, Type, Union

import networkx as nx

from prism.project.base import SentenceExtractionMethod
from prism.project.dir import ProjectDir
from prism.project.graph.entity.iqr import IQRFlag, extract_from_file
from prism.project.graph.entity.logical import LogicalName
from prism.project.util import name_variants
from prism.util.iterable import shallow_asdict

from .entity import (
    LibraryAlias,
    ProjectCoqDependency,
    ProjectCoqLibrary,
    ProjectCoqLibraryRequirement,
    ProjectEntity,
    ProjectExtractedIQR,
    ProjectFile,
    ProjectRoot,
)
from .entity.type import (
    DataDict,
    EdgeIdSet,
    EdgeType,
    NodeId,
    NodeIdSet,
    NodeType,
    ProjectFileType,
)


@dataclass
class ProjectNode:
    """
    A class defining a graph node.
    """

    entity: ProjectEntity

    @property
    def parent(self) -> 'ProjectNode':
        """
        Return parent node of instance node.

        Returns
        -------
        ProjectNode
            An inferred parent node of this instance.
        """
        arguments = shallow_asdict(self.entity)

        if self.entity.type in [ProjectRoot, ProjectEntity]:
            cls = None
        elif self.entity.type is ProjectFile:
            parent = self.entity.project_file_path.parent
            if parent == self.entity.project_path:
                cls = ProjectRoot
            else:
                cls = ProjectFile
                filetype = ProjectFileType.infer(parent)
                arguments['project_file_path'] = parent
                arguments['project_file_type'] = filetype
        elif self.entity.type is LibraryAlias:
            cls = ProjectCoqLibrary
            arguments['logical_name'] = self.entity.default_lib_name
        else:
            cls = self.entity.type.__base__
        if cls is not None:
            return ProjectNode(
                cls(**{f.name: arguments[f.name] for f in fields(cls)}))

    @property
    def node_data(self) -> DataDict:
        """
        Return node data.

        Returns
        -------
        DataDict
            Dictionary of data stored in node.
        """
        data = copy(self.entity.data)
        data["entity_type"] = self.entity.type
        data["node_id"] = self.node_id
        return data

    @property
    def node_id(self) -> NodeId:
        """
        Return NodeType for instance.

        Returns
        -------
        NodeId
            The value that uniquely identifies a node.
        """
        return self.entity.entity_id

    def get_root_node(self) -> 'ProjectNode':
        """
        Return ProjectNode that has root entity.

        Returns
        -------
        ProjectNode
            A ProjectNode containing a ProjectRoot entity.
        """
        return ProjectNode(
            ProjectRoot(self.entity.project_path,
                        self.entity.context),
            NodeType.root)

    def get_root_node_id(self) -> NodeId:
        """
        Return this instances root node id.

        Returns
        -------
        NodeId.
            This instances root node id.
        """
        return self.get_root_node().node_id


@dataclass
class AddedElements:
    """
    Collection of added nodes and edge ids.
    """

    nodes: NodeIdSet = field(default_factory=set)
    edges: EdgeIdSet = field(default_factory=set)

    def _parse(
        self,
        nodes_andor_edges: Union[NodeIdSet,
                                 EdgeIdSet,
                                 Tuple[NodeIdSet,
                                       EdgeIdSet],
                                 'AddedElements']
    ) -> Tuple[NodeIdSet,
               EdgeIdSet]:
        """
        Parse the arguments of the + and += operators.
        """
        if isinstance(nodes_andor_edges, AddedElements):
            nodes = nodes_andor_edges.nodes
            edges = nodes_andor_edges.edges
        elif isinstance(nodes_andor_edges, tuple):
            nodes, edges = nodes_andor_edges
        else:
            element = next(iter(nodes_andor_edges))
            if isinstance(element, tuple):
                nodes, edges = set(), nodes_andor_edges
            else:
                nodes, edges = nodes_andor_edges, set()

        return nodes, edges

    def __add__(
        self,
        nodes_andor_edges: Union[NodeIdSet,
                                 EdgeIdSet,
                                 Tuple[NodeIdSet,
                                       EdgeIdSet],
                                 'AddedElements']
    ) -> 'AddedElements':
        """
        Add combine nodes and or edges from self and other.

        Parameters
        ----------
        nodes_andor_edges : Union[NodeIdSet,
                                 EdgeIdSet,
                                 Tuple[NodeIdSet, EdgeIdSet],
                                 'AddedElements'
                                ]
            A set of nodes, set of edges, or a tuple of both sets
            that will be combined with instance sets.

        Returns
        -------
        AddedElements
            A collection of sets that is the union of both
            this instance and inputs.
        """
        nodes, edges = self._parse(nodes_andor_edges)
        nodes = self.nodes.union(nodes)
        edges = self.edges.union(edges)
        return AddedElements(nodes, edges)

    def __iadd__(
        self,
        nodes_andor_edges: Union[NodeIdSet,
                                 EdgeIdSet,
                                 Tuple[NodeIdSet,
                                       EdgeIdSet],
                                 'AddedElements']
    ) -> 'AddedElements':
        """
        Add combine nodes and or edges from self and other in place.

        Parameters
        ----------
        nodes_andor_edges : Union[NodeIdSet,
                                 EdgeIdSet,
                                 Tuple[NodeIdSet, EdgeIdSet],
                                 'AddedElements'
                                ]
            A set of nodes, set of edges, or a tuple of both sets
            that will be combined with instance sets.

        Returns
        -------
        AddedElements
            A collection of sets that is the union of both
            this instance and inputs.
        """
        nodes, edges = self._parse(nodes_andor_edges)
        self.nodes = self.nodes.union(nodes)
        self.edges = self.edges.union(edges)
        return self


class ProjectNodeGraph(nx.MultiDiGraph):
    """
    A graph of ProjectNodes.
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize the graph and create mappings of root entities.
        """
        super(ProjectNodeGraph, self).__init__(*args, **kwargs)
        self._roots = set()
        self._map: Dict[NodeId,
                        Dict[Type[ProjectEntity],
                             Set[NodeId]]] = {}
        self._root_variants: Dict[NodeId,
                                  Set[str]] = {}
        self._root_map: Dict[NodeId, Dict[Type[ProjectNode], Set[NodeId]]]

    def _add_path(self, path: Path) -> AddedElements:
        """
        Add a path as a ProjectFile under a root node.

        If the path a subpath of another root path

        Parameters
        ----------
        path : Path
            A subpath of some root node.
        """
        path = Path(path)
        file_type = ProjectFileType.infer(path)

        if not file_type:
            return set(), set()

        roots = self.roots
        root = None
        for r in roots:
            if path.is_relative_to(r.entity.project_path):
                root = r

        if root is None:
            raise ValueError("Cannot find a match project root in graph.")

        file = ProjectFile.from_super(
            root.entity,
            project_file_path=path,
            project_file_type=file_type)
        added = self.add_project_node(file, add_parent=False)

        if (file_type is ProjectFileType.coqfile
                or file_type is ProjectFileType.coqdirectory):
            library = ProjectCoqLibrary.from_instance(file, logical_name=None)
            added += self.add_project_node(library, add_parent=False)
        elif file_type is ProjectFileType.coqproject:

            def match_roots(iqr_name, other_root_id):
                is_variant = iqr_name in self._root_variants[other_root_id]
                is_not_target_root = other_root_id != root.node_id
                return is_variant and is_not_target_root

            iqrs = extract_from_file(str(file.project_file_path))
            for flag in iqrs:
                # Ignore -I flag since many projects may not even use
                # it!
                if flag is IQRFlag.I:
                    continue
                # Create the iqr node and add it to the graph.
                for iqr_path, name in iqrs[flag]:
                    iqr_path = Path(iqr_path)
                    iqr = ProjectExtractedIQR.from_parent(
                        file,
                        iqr_path=iqr_path,
                        iqr_name=name,
                        iqr_flag=flag,
                    )
                    # Add only iqrs that don't match another root
                    if not any(match_roots(name, r) for r in self._roots):
                        added += self.add_project_node(iqr)
                        added += self.add_project_edge(
                            ProjectNode(iqr),
                            ProjectNode(file),
                            EdgeType.IQRToProjectFile)
        return added

    def add_aliases(self, node_id: NodeId) -> AddedElements:
        """
        Add logical aliases imposed by iqr arguments to graph.

        Parameters
        ----------
        node_id : NodeId
            The root node whose libraries will be added to the
            graph.

        Returns
        -------
        AddedElements
            Sets of added elements to graph.
        """
        entity_class = ProjectExtractedIQR
        added = AddedElements()
        for iqr_node in self.nodes_of_type(node_id, entity_class):
            for library_node, alias_node in self.deduced_aliases(iqr_node):
                added += self.add_project_node(alias_node)
                added += self.add_project_edge(
                    alias_node,
                    library_node,
                    EdgeType.LibraryAliasToLibrary)
        return added

    def add_dependencies(self, node_id: NodeId) -> AddedElements:
        """
        Add project dependency nodes.

        This will also connect dependency nodes to the root node,
        requirement nodes, and any matching libraries. Additionally the
        point will be set

        Parameters
        ----------
        node_id : NodeId
            The root node whose files will be added to the graph.

        Returns
        -------
        AddedElements
            Sets of added elements to graph.
        """
        added = AddedElements()
        entity_class = ProjectCoqLibraryRequirement

        def create(root_node, requirement_node):
            return ProjectNode(
                ProjectCoqDependency.from_parent(
                    root_node.entity,
                    logical_name=requirement_node.entity.requirement))

        # Add a dependency for each requirement found under root node.
        for requirement_node in self.nodes_from_graph(entity_class):
            # Create dependency node and add to the graph.
            root_node = requirement_node.get_root_node()
            if root_node.node_id != node_id:
                continue
            dependency_node = create(root_node, requirement_node)
            # Add dependency and edge to requirement
            if not self.has_node(dependency_node.node_id):
                added += self.add_project_node(dependency_node)
                added += self.add_project_edge(
                    dependency_node,
                    requirement_node,
                    EdgeType.DependencyToRequirement)
            # Find a matching library to the dependency graph.
            for library_node in self.match_dependency_to_library(
                    dependency_node.entity):
                added += self.add_project_edge(
                    dependency_node,
                    library_node,
                    EdgeType.DependencyToLibrary)
        return added

    def add_files(self, node_id: NodeId) -> AddedElements:
        """
        Add all project files as nodes under root node.

        Parameters
        ----------
        node_id : NodeId
            The root node whose files will be added to the graph.

        Returns
        -------
        AddedElements
            Sets of added elements to graph.
        """
        root = self.init_node(node_id)
        added = AddedElements()
        for dirname, _, files in os.walk(str(root.entity.project_path)):
            dirname = Path(dirname)
            if str(dirname) != str(root.entity.project_path):
                added += self._add_path(dirname)

            for file in files:
                file = dirname / Path(file)
                added += self._add_path(file)
        self.add_aliases(node_id)
        return added

    def add_project_edge(
        self,
        src: Union[ProjectEntity,
                   ProjectNode],
        dst: Union[ProjectEntity,
                   ProjectNode],
        edgetype: EdgeType,
    ) -> AddedElements:
        """
        Add an edge between two nodes.

        Parameters
        ----------
        src : Union[ProjectEntity, ProjectNode]
            The source node for the added edge.
        dst : Union[ProjectEntity, ProjectNode]
            The destination node for the added edge.
        edgetype : EdgeType
            Type of edge between the two nodes. Used construct
            edge key and is also stored in edge data.

        Returns
        -------
        AddedElements
            Sets of added elements to graph.
        """
        added = AddedElements()
        if isinstance(src, ProjectEntity):
            src = ProjectNode(src)
        if isinstance(dst, ProjectEntity):
            dst = ProjectNode(dst)
        key = f"{self}: {src.node_id}-->{dst.node_id}"
        if not self.has_node(src.node_id):
            added += self.add_project_node(src)
        if not self.has_node(dst.node_id):
            added += self.add_project_node(dst)
        if not self.has_edge(src.node_id, dst.node_id, key):
            self.add_edge(src.node_id, dst.node_id, key, edge_type=edgetype)
        return AddedElements(edges={(src.node_id,
                                     dst.node_id,
                                     key)})

    def add_project_node(
        self,
        node: Union[ProjectEntity,
                    ProjectNode],
        add_parent: bool = True,
    ) -> AddedElements:
        """
        Add project node unless it exists in the graph.

        Parameters
        ----------
        project_node : ProjectNode
            Add the project node to the graph if
            it isn't in the graph already.
        add_node : bool, optional
            If True and the node will be added to the graph.
        add_parent : bool, optional
            If True and the parent instance doesn't exist in the graph,
            add it, by default True.
        connect_parent : bool, optional
            If true, the instance will reconstruct
            the parent instance to determine it's node id.
            Then it will create both EdgeType.ChildToParent and
            EdgeType.ParentToChild edges between the two nodes.
            By default True.
        edgetypes : List[EdgeType], optional
            Allow adding given EdgeTypes to the graph, by default None.

        Returns
        -------
        NodeIdSet
            Return set of node ids added to the graph.
        """
        if isinstance(node, ProjectEntity):
            node = ProjectNode(node)

        added = AddedElements()

        # Add the node and check if its a root node.
        if not self.has_node(node.node_id):
            self.add_node(node.node_id, **node.node_data)
            added += {node.node_id}
            if node.entity.type is ProjectRoot:
                variants = name_variants(node.entity.project_path.stem)
                self._roots.add(node.node_id)
                self._root_variants[node.node_id] = variants

        # Add the parent node.
        if node.parent is not None:
            if not self.has_node(node.parent.node_id):
                if add_parent:
                    added += self.add_project_node(node.parent)
                else:
                    raise ValueError(f"Parent does not exist: {node.node_id}")
            added += self.add_project_edge(
                node,
                node.parent,
                EdgeType.ChildToParent)
            added += self.add_project_edge(
                node.parent,
                node,
                EdgeType.ParentToChild)

        # Add the node map between roots and node types.
        for nodeid in added.nodes:
            added_node = self.init_node(nodeid)
            entity_class = added_node.entity.type
            root_node_id = added_node.get_root_node_id()

            if (root_node_id is not None and root_node_id not in self._roots
                    and entity_class != ProjectRoot):
                raise ValueError("root node not in graph but child node is.")

            if root_node_id not in self._map:
                self._map[root_node_id] = dict()

            if entity_class not in self._map[root_node_id]:
                self._map[root_node_id][entity_class] = set()

            self._map[root_node_id][entity_class].add(added_node.node_id)

        return added

    def add_requirements(self, node_id: NodeId) -> AddedElements:
        """
        Parse each file, extract requirements, and add them to graph.

        Parameters
        ----------
        node_id : NodeId
            The root node whose requirements will be added to the
            graph.

        Returns
        -------
        AddedElements
            Sets of added elements to graph.
        """
        added = AddedElements()
        sem = SentenceExtractionMethod.HEURISTIC
        project = ProjectDir(
            str(self.nodes[node_id]['project_path']),
            sentence_extraction_method=sem)
        parser = project.sentence_extraction_method.parser()
        extract_kw = dict(glom_proofs=False, sentence_extraction_method=sem)

        def create(parent, req):
            return ProjectCoqLibraryRequirement.from_parent(
                parent,
                requirement=LogicalName(req))

        def extract(path):
            sentences = project.get_sentences(path, **extract_kw)
            sentences = [str(s) for s in sentences]
            stats = parser._compute_sentence_statistics(sentences)
            return stats.requirements

        for file_node in self.files_of_type(node_id, ProjectFileType.coqfile):
            library_node_id = self.find_library_from_file(file_node.node_id)
            library_node = self.init_node(library_node_id)
            path = str(file_node.entity.project_file_path)
            for requirement in extract(path):
                requirement = create(library_node.entity, requirement)
                added += self.add_project_node(ProjectNode(requirement))
        return added

    def children(self, node_id: NodeId) -> NodeIdSet:
        """
        Return all children of the given node.

        A parent will have a inward edges from each child to itself with
        edge_type == EdgeType.ChildtoParent.
        """
        edges = self.out_edges(node_id, data='edge_type', default=None)
        nodes = set()
        for _, destination, edge_type in edges:
            if edge_type == EdgeType.ParentToChild:
                nodes.add(destination)
        return nodes

    def deduced_aliases(self,
                        iqr_node: ProjectNode) -> Tuple[ProjectNode,
                                                        ProjectNode]:
        """
        Find the libraries that require adding aliases due to iqr.

        The following explanation uses the following example IQR
        flag:  ``-R ./lib/comp Comp``.

        All subdirectories and files of ``./lib/comp`` recursively
        can be loaded using a logical name that starts with ``Comp``.
        This method will return the corresponding ProjectFile and
        ProjectCoqLibrary instances, as well as the logical name
        that will be used to define a LibraryAlias node.
        """
        if not isinstance(iqr_node, ProjectNode):
            iqr_node = self.init_node(iqr_node)
        iqr = iqr_node.entity
        root_node_id = iqr_node.get_root_node_id()
        """
        Find the ProjectFile correpsonding to path in iqr node.

        The following explanation uses the following example IQR
        flag:  ``-R ./lib/comp Comp``.

        The IQR argument implies the existance of directory
        ``./lib/comp`` that is logically bound to ``Comp``. This method
        will find the ProjectFile coresponding to ``./lib/comp``.
        """
        project_path = iqr_node.entity.project_path
        iqr_path = iqr.project_file_path.parent / iqr.iqr_path

        if str(iqr_path) == str(project_path):
            path_node = iqr_node.get_root_node()
        else:
            if iqr_path.suffix == '.v':
                filetype = ProjectFileType.coqfile
            else:
                filetype = ProjectFileType.coqdirectory
            file = ProjectFile.from_instance(
                iqr_node.entity,
                project_file_path=iqr_path,
                project_file_type=filetype)
            file_node = ProjectNode(file)
            path_node = file_node

        if not self.has_node(path_node.node_id):
            return

        # Paths under this are effected by the iqr argument.
        # The path node id can correspond to a file (relative)
        # or to the root ndoe (project_path).
        if isinstance(path_node.entity, ProjectFile):
            effected_path = self.nodes[path_node.node_id]['relative']
        elif isinstance(path_node.entity, ProjectRoot):
            effected_path = self.nodes[path_node.node_id]['project_path']
        else:
            raise TypeError(
                f"IQR path is not a file/root node: {path_node.node_id}")
        # Convert the LogicalName given in the IQR argument
        # in to a path. This is done to replace relative
        # path of the files, so that the relative paths
        # can be used to construct the new library aliases.
        modified_root = Path(*str(iqr_node.entity.iqr_name).split('.'))
        for file_node in self.files_of_type(root_node_id,
                                            ProjectFileType.coqfile,
                                            ProjectFileType.coqdirectory):
            current_path = self.nodes[file_node.node_id]['relative']
            effected = current_path.is_relative_to(effected_path)
            if effected:
                lib = self.find_library_from_file(file_node.node_id)
                lib = self.init_node(lib)
                # Construct a new logical name by replaceing the root
                # in current path with modified root. The root
                # being overlap in path between iqr and project file.
                if lib is not None:
                    modified_path = current_path.relative_to(effected_path)
                    path = modified_root / modified_path
                    name = LogicalName.from_physical_path(path)
                    alias = LibraryAlias.from_super(lib.entity, alias=name)
                    yield (lib, ProjectNode(alias))

    def find_library_from_alias(self, nodeid: NodeId) -> ProjectNode:
        """
        Find the library from one of it's aliases.
        """
        edges = EdgeType.LibraryAliasToLibrary.find_edges(self, nodeid)
        result = None
        for alias, library, _ in edges:
            if alias == nodeid:
                result = library
                break
        return self.init_node(result)

    def find_library_from_file(self, nodeid: NodeId) -> NodeId:
        """
        Get ProjectCoqLibrary node connected to a ProjectFile node.
        """
        children = self.children(nodeid)
        for child in children:
            if self.nodes[child]['type'] == ProjectCoqLibrary:
                return child

    def init_node(
        self,
        node_id: NodeId,
    ) -> ProjectNode:
        """
        Initialize project node instance from the graph node.

        Parameters
        ----------
        node_id: NodeId
            The node value returned by some project node
            instance. The instance that would return that
            node value will be equivilant to the instance
            this methods returns.

        Returns
        -------
        ProjectNode
            The project node that returns ``node`` value.
        """
        cls = self.nodes[node_id]['entity_type']
        node_type = self.nodes[node_id]['node_type']
        data = self.nodes[node_id]
        field_data = cls.fields_from_data(data)
        try:
            entity = cls(**field_data)
        except TypeError:
            entity = None

        if entity is None:
            super_node_id = self.get_super_node_id(node_id)
            if super_node_id is None:
                raise ValueError("No Super Found")
            super_node = self.init_node(super_node_id)
            entity = cls.from_super(super_node.entity, **field_data)
        return ProjectNode(entity, node_type)

    def get_parent_node_id(
        self,
        node: NodeId,
    ) -> ProjectNode:
        """
        Initialize project node instance from the graph node.

        Parameters
        ----------
        node : NodeId
            The node value returned by some project node
            instance. The instance that would return that
            node value will be equivilant to the instance
            this methods returns.

        Returns
        -------
        ProjectNode
            The project node that returns ``node`` value.
        """
        edgetype = EdgeType.ChildToParent
        edges = self.edges(node, data='edge_type')
        parent_edges = list(filter(lambda edge: edge[2] is edgetype, edges))
        parents = [parent for _, parent, _ in parent_edges]
        if len(parents) == 0:
            parent = None
        else:  # len(parents) == 1:
            # Get the target node from edge
            parent = list(parents)[0]
        # else:
        #     raise ValueError(
        #         f"Child has more than one parent: {parents}"
        #     )
        return parent

    def get_super_node_id(self, node_id: NodeId) -> NodeId:
        """
        Extract the node id of the super of given node.

        Parameters
        ----------
        node_id : NodeId
            A node whose predecessor has the same type as the super
            class of the given node.

        Returns
        -------
        str
            The node id of ``node``'s predeccessor that can be used
            to initialize an instance of ``nodes``'s super class.
        """
        node_class = self.nodes[node_id]['type']
        super_class = node_class.__bases__[0]
        while node_class != super_class and node_id is not None:
            node_id = self.get_parent_node_id(node_id)
            if node_id is not None:
                node_class = self.nodes[node_id]['type']
        return node_id

    def get_parent_node(self, node_id: NodeId) -> ProjectNode:
        """
        Extract the node id of the parent of the given node.

        Parameters
        ----------
        node_id: NodeId
            The node that has ChildToParent and ParentToChild
            edges between this node and it's parent node.

        Returns
        -------
        str
            The nodeid of the node that has ChildToParent and
            ParentToChild edges between it and ``node``.
        """
        parent_node_id = self.get_parent_node_id(node_id)
        return self.init_node(parent_node_id)

    def get_super_node(self, node_id: NodeId) -> ProjectNode:
        """
        Extract the node id of the parent of the given node.

        Parameters
        ----------
        node_id: NodeId
            The node that has ChildToParent and ParentToChild
            edges between this node and it's parent node.

        Returns
        -------
        str
            The nodeid of the node that has ChildToParent and
            ParentToChild edges between it and ``node``.
        """
        super_node_id = self.get_super_node_id(node_id)
        return self.init_node(super_node_id)

    def nodes_of_type(self, root_id: NodeId, nodetype: Type[ProjectEntity]):
        """
        Iterate of nodes of a specific type under a root.

        Parameters
        ----------
        root_id : NodeId
            Node ID of root node whose descendents will be iterated
            over.
        nodetype : Type[ProjectEntity]
            Type of node entities to return.

        Yields
        ------
        ProjectNode
            Node from graph that matches the type.
        """
        for node_id in self._map.get(root_id,
                                     {}).get(nodetype,
                                             set()):
            node = self.init_node(node_id)
            yield node

    def files_of_type(self, root_id: NodeId, *filetypes: ProjectFileType):
        """
        Iterate of nodes of a specific type under a root.

        Parameters
        ----------
        root_id : NodeId
            Node ID of root node whose descendents will be iterated
            over.
        filetype : Type[ProjectEntity]
            nodes return will be this file type.

        Yields
        ------
        ProjectNode
            Node from graph that matche specified type.
        """
        for node in self.nodes_of_type(root_id, ProjectFile):
            if node.entity.project_file_type in filetypes:
                yield node

    def match_dependency_to_library(self, dependency: ProjectCoqDependency):
        """
        Identify a library in the graph that matches the dependency.

        Yields
        ------
        ProjectNode
            Node from graph that matches the input dependency.
        """
        if dependency is None:
            raise ValueError("Dependency is None, cannot find library.")

        def matches_name(dependency, logical_name):
            return (
                (dependency == logical_name)
                or (logical_name in dependency.shortnames))

        def logical_match(nodeid, data):
            name = data.get('alias', data.get('logical_name'))
            return matches_name(dependency.logical_name, name)

        for library in self.nodes_from_graph(ProjectCoqLibrary, logical_match):
            yield library
        for alias in self.nodes_from_graph(LibraryAlias, logical_match):
            yield self.find_library_from_alias(alias.node_id)

    def nodes_from_graph(
            self,
            entity_class: Type[ProjectEntity],
            criteria=None):
        """
        Return nodes of the specified entity type.

        Yields
        ------
        ProjectNode
            Node from graph that matches the entity type
            and an extra criteria.
        """
        for type_dict in self._map.values():
            for node in type_dict.get(entity_class, []):
                if criteria is None or (criteria
                                        and criteria(node,
                                                     self.nodes[node])):
                    yield self.init_node(node)

    def parent(self, nodeid: NodeId) -> ProjectNode:
        """
        Return node id of the parent of the given node.

        A parent will have a outward edge from itself to the child with
        edge_type == EdgeType.ParentToChild
        """
        edges = self.out_edges(nodeid, data='edge_type', default=None)
        parent = None
        for _, destination, edge_type in edges:
            if edge_type == EdgeType.ChildToParent:
                if parent is None:
                    parent = destination
                else:
                    raise ValueError(
                        "Multiple parents found connected to project node")
        return self.init_node(destination)
