"""
Module for base node in project graph.
"""
from abc import abstractmethod
import networkx as nx
from dataclasses import astuple, dataclass, fields

from typing import Type, Tuple, Dict, Optional, Any, List
from prism.util.compare import Criteria
from prism.util.iterable import shallow_asdict
from prism.project.metadata.storage import Context
from .type import (
    EdgeIdSet,
    NodeId,
    DataDict,
    NodeIdSet,
    EdgeType,
    NodeType,
)


@dataclass
class ProjectNode:
    """
    A class defining a graph node.
    """
    context: Context

    class TypeCriteria(Criteria):

        def __init__(self, type: Type['ProjectNode'], *args, **kwargs):
            Criteria.__init__(self, *args, **kwargs)
            self.type = type

        def evaluate(self, node: NodeId, data: DataDict) -> bool:
            """
            Return True if type in node data matches ``self.type``.
            """
            return data["type"] == self.type



    def __post_init__(self):
        self.__hash = None
        self.__data = None
        self.__node = None
        self.__parent = None
        self.__super = None
        self._node_type = None

    def __hash__(self) -> int:
        """
        Generate a hash based on context.

        Returns
        -------
        int
            context hash.
        """
        return self.type.hash_data(self.context, self.data)

    @property
    def data(self) -> Dict[str, Any]:
        """
        Return the data dictionary to be stored in the node.

        Returns
        -------
        Dict[str, Any]
            Dictionary passed as kwargs to ``nx.Graph().add_node``.
        """
        if self.__data is None:
            self.__data = self.get_data()
            self.__data["typename"] = self.typename
            self.__data["type"] = self.type
            self.__data["node_type"] = self.node_type
        return self.__data

    @property
    def hash(self) -> int:
        """
        Generate the hash for the instance.

        Returns
        -------
        int
            instance hash.
        """
        return self.hash_data(self.context, self.data)

    @property
    def node(self) -> str:
        """
        Return a unique identifier to a node.

        Returns
        -------
        str
            Node id.
        """
        if self.__node is None and self.type != ProjectNode:
            name = self.typename
            self.__node = f"{name}: {hash(self)}"
        return self.__node

    @property
    def node_type(self) -> NodeType:
        """
        Return NodeType for instance
        """
        return self._node_type

    @property
    def parent(self) -> 'ProjectNode':
        """
        Return ``ProjectNode`` instance that is parent to this.

        Returns
        -------
        ProjectNode
            The return instance would have a ParentToChild and
            ChildToParent edges with this if they were both added
            to a graph.
        """
        if self.__parent is None:
            self.__parent = self.init_parent()
        return self.__parent

    @property
    def super(self) -> 'ProjectNode':
        """
        Return ``ProjectNode`` that is first (mro) super class of this.

        Returns
        -------
        ProjectNode
            This instance super class can be initialized using
            the instance attributes. The returned ``ProjectNode``
            is the outcome of that initialization operation.
        """
        if self.__super is None and self.type != ProjectNode:
            if issubclass(self.type, ProjectNode):
                self_dict = shallow_asdict(self)
                super_class = self.type.__bases__[0]
                super_fields = fields(super_class)
                super_dict = {
                    field.name: self_dict[field.name] for field in super_fields
                }
                super_instance = super_class(**super_dict)
            else:
                super_instance = None
            self.__super = super_instance
        return self.__super

    @property
    def typename(self) -> str:
        """
        Return class name through property.

        Returns
        -------
        str
            The name of this instance's class
        """
        return self.__class__.__name__

    @property
    def type(self):
        """
        Return self.__class__
        """
        return self.__class__

    def add_to_graph(
        self,
        graph: nx.Graph,
        add_parent: bool = True,
        connect_parent: bool = True,
        edgetypes: Optional[List[EdgeType]] = None
    ) -> Tuple[NodeIdSet, EdgeIdSet]:
        """
        Add the project node to a graph.

        Parameters
        ----------
        graph : nx.Graph
            The graph the project node will be added to.
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
        Tuple[Set[Hashable], Set[Tuple[Hashable, Hashable, str]]]
            Return the added node ids and added edge ids as a tuple of sets.
        """
        added_nodes = self.add_nodes_to_graph(graph, add_parent)
        added_nodes_, added_edges = self.add_edges_to_graph(graph, connect_parent, edgetypes)
        added_nodes = added_nodes.union(added_nodes_)
        return added_nodes, added_edges

    def add_nodes_to_graph(
        self,
        graph: nx.Graph,
        add_parent: bool = True,
    ) -> NodeIdSet:
        """
        Add this node and possibly parent node to graph.

        Parameters
        ----------
        graph : nx.Graph
            The graph the project node will be added to.
        add_parent : bool, optional
            If True and the parent instance doesn't exist in the graph,
            add it, by default True.
    
        Returns
        -------
        NodeIdSet
            Return the added node ids
        """
        added_nodes = set()
        graph.add_node(self.node, **self.data)
        added_nodes.add(self.node)
        if add_parent and self.parent and not graph.has_node(self.parent.node):
            added_nodes = added_nodes.union(self.parent.add_nodes_to_graph(graph, add_parent=add_parent))
        return added_nodes

    def add_edges_to_graph(
        self,
        graph: nx.Graph,
        connect_parent: bool = True,
        edgetypes: Optional[List[EdgeType]] = None,
    ) -> EdgeIdSet:
        """
        Add the project node to a graph.

        Parameters
        ----------
        graph : nx.Graph
            The graph the project node will be added to.
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
        Set[Tuple[Hashable, Hashable, str]]
            Return the added edge ids.
        """
        added_edges = set()
        added_nodes = set()
        if connect_parent and self.parent:
            added_edges.union(self.edge_from_instance(graph, self.parent, EdgeType.ParentToChild))
            added_edges.union(self.edge_to_instance(graph, self.parent, EdgeType.ChildToParent))
        if edgetypes is not None:
            added_nodes, added_edges_ = self.connect(graph, edgetypes)
            added_edges = added_edges.union(added_edges_)
        return added_nodes, added_edges

    def edge_from_instance(
        self,
        graph: nx.Graph,
        instance: 'ProjectNode',
        edgetype: EdgeType,
        **edge_data
    ) -> EdgeIdSet:
        """
        Add outward edge from given instance to this node.

        Parameters
        ----------
        graph : nx.Graph
            The graph the project node will be added to.
        instance : ProjectNode
            The project node that has outward relationship
            to this node.
        edgetype : EdgeType
            The type of edge to add. This value is used to construct
            the edge key.

        Returns
        -------
            ) -> EdgeIdSet:
            Return the added edge ids.
        """
        key = f"{edgetype}: {self.node}"
        edgetype.add_edge
        edge_data['edge_type'] = edgetype
        identifier = (instance.node, self.node, key)
        graph.add_edge(instance.node, self.node, key=key, **edge_data)
        return {identifier}

    def edge_to_instance(
        self,
        graph: nx.Graph,
        instance: 'ProjectNode',
        edgetype: EdgeType,
        **edge_data,
    ) -> EdgeIdSet:
        """
        Add inward edge from given instance to this node.

        Parameters
        ----------
        graph : nx.Graph
            The graph the project node will be added to.
        instance : ProjectNode
            The project node that has inward relationship
            to this node.
        edgetype : EdgeType
            The type of edge to add. This value is used to construct
            the edge key.

        Returns
        -------
            ) -> EdgeIdSet:
            Return the added edge ids.
        """
        key = f"{edgetype}: {instance.node}"
        edge_data['edge_type'] = edgetype
        identifier = (self.node, instance.node, key)
        graph.add_edge(self.node, instance.node, key=key, **edge_data)
        return {identifier}

    @abstractmethod
    def connect(
        self,
        graph: nx.Graph,
        edgetypes: List[EdgeType]
    ) -> Tuple[NodeIdSet, EdgeIdSet]:
        """
        Add connections to and from this node to other nodes in graph.

        Parameters
        ----------
        graph : nx.Graph
            The graph containing this node.
        edgetypes : List[EdgeType]
            Allow adding given EdgeTypes to the graph, by default None.

        Returns
        -------
        Tuple[Set[Hashable], Set[Tuple[Hashable, Hashable, str]]]
            Return the added node ids and added edge ids as a tuple of sets.
        """
        pass

    @abstractmethod
    def get_data(self) -> DataDict:
        """
        Extract data dictionary from project node.

        Returns
        -------
        Dict[str, Any]
            The data dictionary extracted from this instance.
        """
        pass

    @abstractmethod
    def init_parent(self) -> 'ProjectNode':
        """
        Initialize the parent project node using this instance's attributes.

        Returns
        -------
        ProjectNode
            The return instance would have a ParentToChild and
            ChildToParent edges with this if they were both added
            to a graph.
        """
        pass

    @classmethod
    def hash_data(
        cls,
        context: Context,
        data: DataDict
    ) -> int:
        """
        Generate hash from data.

        Parameters
        ----------
        context : Context
            The context for a project node.
        data : Dict[str, Any]
            The data dictionary from a project node.

        Returns
        -------
        int
            The hash of a project node instance.
        """
        value = 0
        if cls == ProjectNode:
            value = hash(context.revision.project_source)
        else:
            value = hash(frozenset(astuple(context) + tuple(data.items())))
        return value

    @classmethod
    def nodes_from_graph(
        cls,
        graph: nx.Graph,
        criteria: Optional[Criteria] = None
    ) -> NodeIdSet:
        """
        Return all nodes that return true for all conditions.

        Only nodes of the given ProjectNode subclass will
        be returned since a type specific condition is added to
        the conditions provided as arguments.

        Parameters
        ----------
        graph : nx.Graph
            The graph whose nodes will be searched.
        """ 

        type_criteria  = cls.TypeCriteria(cls)
        if criteria:
            criteria = type_criteria & criteria
        else:
            criteria = type_criteria

        return set(
            node for node, data in graph.nodes(data=True) if criteria(node, data)
        )

    @classmethod
    def init_from_node(
        cls,
        graph: nx.Graph,
        node: str,
    ) -> 'ProjectNode':
        """
        Initialize project node instance from the graph node.

        Parameters
        ----------
        graph : nx.Graph
            The graph containing the node ``node``.
        node : str
            The node value returned by some project node
            instance. The instance that would return that
            node value will be equivilant to the instance
            this methods returns.

        Returns
        -------
        ProjectNode
            The project node that returns ``node`` value.
        """
        super_node = None
        super_cls = cls.__bases__[0]
        current_cls = cls
        trail = []
        while super_node is None:
            parent_node = current_cls.get_parent_node(graph, node)
            parent_type = graph.nodes[parent_node]['type']
            trail.append((parent_node, parent_type))
            if parent_type == super_cls:
                super_node = parent_node
            else:
                node = parent_node
            current_cls = parent_type
        return trail

    @classmethod
    def from_instance(
        cls,
        instance: 'ProjectNode',
        *args,
        **kwargs
        ):
        """
        Initialize project node using given instance attributes.

        Parameters
        ----------
        graph : nx.Graph
            The graph containing the node ``node``.
        instance : ProjectNode
            A project node instance whose attributes will be
            used to populate this class's instance's attributes.
            Any missing arguments or keyword arguments must be
            provided via *args, **kwargs.

        Returns
        -------
        ProjectNode
            The project node that returns ``node`` value.
        """
        args = list(args)
        cls_field_names = tuple(field.name for field in fields(cls))
        instance_dict = shallow_asdict(instance)
        cls_dict = {}
        for cls_field_name in cls_field_names:
            if cls_field_name in kwargs:
                value = kwargs[cls_field_name]
            elif cls_field_name in instance_dict:
                value = instance_dict[cls_field_name]
            else:
                value = args.pop(0)
            cls_dict[cls_field_name] = value
        return cls(**cls_dict)

    @classmethod
    def from_parent(
        cls,
        parent_instance: 'ProjectNode',
        *args,
        **kwargs
    ):
        """
        Initialize project node using given instance attributes.

        Parameters
        ----------
        graph : nx.Graph
            The graph containing the node ``node``.
        parent_instance : ProjectNode
            A project node instance that is expected
            to be the parent of the return project node instance.
            The given instance would have ParentToChild and
            ChildToParent edges with the returned instance if they\
            were both added to a graph.

        Returns
        -------
        ProjectNode
            A project node instance that would be the child node of
            the ``parent_instance`` if they were both added to a graph.
        """
        instance = cls.from_instance(parent_instance, *args, **kwargs)
        instance.__parent = parent_instance
        return instance

    @classmethod
    def from_super(
        cls,
        super_instance: 'ProjectNode',
        *args,
        **kwargs
    ):
        """
        Return ``ProjectNode`` that is first (mro) super class of this.

        Parameters
        ----------
        graph : nx.Graph
            The graph containing the node ``node``.
        super_instance : ProjectNode
            A project node instance that is expected to be the
            super of the returned project node instance.

        Returns
        -------
        ProjectNode
            A project node that contains the super instance as
            a subset of it's attributes.
        """
        instance = cls.from_instance(super_instance, *args, **kwargs)
        instance.__super = super_instance
        return instance

    @classmethod
    def get_parent_node(
        cls,
        graph: nx.Graph,
        node: str
    ) -> str:
        """
        Extract the node id of the parent of the given node.

        Parameters
        ----------
        graph : nx.Graph
            The graph containing a node that is the
            parent of this instance.
        node : str
            The node that has ChildToParent and ParentToChild
            edges between this node and it's parent node.

        Returns
        -------
        str
            The nodeid of the node that has ChildToParent and
            ParentToChild edges between it and ``node``.
        """
        for source, _, data in graph.in_edges(node, data=True, default=None):
            if data['edge_type'] is EdgeType.ParentToChild:
                return source

    @classmethod
    def get_super_node(
        cls,
        graph: nx.Graph,
        node: str
    ) -> str:
        """
        Extract the node id of the super of given node.

        Parameters
        ----------
        graph : nx.Graph
            The graph containing a node that is the
            parent of this instance.
        node : str
            A node whose predecessor has the same type as the super class
            of the given node.

        Returns
        -------
        str
            The node id of ``node``'s predeccessor that can be used
            to initialize an instance of ``nodes``'s super class.
        """
        super_node = None
        super_cls = cls.__bases__[0]
        while super_node is None:
            parent_node = cls.get_parent_node(graph, node)
            parent_class = graph.nodes[parent_node]['type']
            if parent_class != super_cls:
                node = parent_node
            else:
                super_node = parent_node
        return super_node
