"""
Subpackage containing functionality extracted from `radpytools`.
"""

from functools import cached_property, lru_cache, partial, partialmethod
from multiprocessing import RLock
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    Iterable,
    Optional,
    Protocol,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    runtime_checkable,
)

from .path import PathLike  # noqa: F401

_T = TypeVar('_T')
_S = TypeVar('_S', contravariant=True)


@runtime_checkable
class _Named(Protocol):
    """
    Part of the descriptor protocol.

    See https://docs.python.org/3/howto/descriptor.html#automatic-name-notification
    """  # noqa: W505

    def __set_name__(self, _owner: type, name: str) -> None:  # noqa: D105
        ...


@runtime_checkable
class _NonDataDescriptor(Protocol):
    """
    Part of the descriptor protocol.

    See https://docs.python.org/3/howto/descriptor.html#descriptor-protocol.
    """  # noqa: W505

    def __get__(self, _instance: Any, _owner: Optional[type] = ...) -> Any:
        ...


@runtime_checkable
class _NamedNonDataDescriptor(_NonDataDescriptor, _Named, Protocol):
    """
    Part of the descriptor protocol.

    See https://docs.python.org/3/howto/descriptor.html#automatic-name-notification
    """  # noqa: W505

    pass


@runtime_checkable
class _MutationDescriptor(Protocol):
    """
    TPart of the descriptor protocol.

    See https://docs.python.org/3/howto/descriptor.html#descriptor-protocol.
    """  # noqa: W505

    def __set__(self, _instance: Any, _value: Any) -> None:  # noqa: D105
        ...


@runtime_checkable
class _NamedMutationDescriptor(_MutationDescriptor, _Named, Protocol):
    """
    Part of the descriptor protocol.

    See https://docs.python.org/3/howto/descriptor.html#automatic-name-notification
    """  # noqa: W505

    pass


@runtime_checkable
class _DestructiveDescriptor(Protocol):
    """
    Part of the descriptor protocol.

    See https://docs.python.org/3/howto/descriptor.html#descriptor-protocol.
    """  # noqa: W505

    def __delete__(self, _instance: Any) -> None:  # noqa: D105
        ...


@runtime_checkable
class _NamedDestructiveDescriptor(_DestructiveDescriptor, _Named, Protocol):
    """
    Part of the descriptor protocol.

    See https://docs.python.org/3/howto/descriptor.html#automatic-name-notification
    """  # noqa: W505

    pass


@runtime_checkable
class _DataDescriptor(_DestructiveDescriptor, _MutationDescriptor, Protocol):
    """
    Part of the descriptor protocol.

    See https://docs.python.org/3/howto/descriptor.html#automatic-name-notification
    """  # noqa: W505

    pass


@runtime_checkable
class _NamedDataDescriptor(_DestructiveDescriptor,
                           _MutationDescriptor,
                           _Named,
                           Protocol):
    """
    Part of the descriptor protocol.

    See https://docs.python.org/3/howto/descriptor.html#automatic-name-notification
    """  # noqa: W505

    pass


MutationDescriptor = Union[_MutationDescriptor, _NamedMutationDescriptor]
DestructiveDescriptor = Union[_DestructiveDescriptor,
                              _NamedDestructiveDescriptor]
NonDataDescriptor = Union[_NonDataDescriptor, _NamedNonDataDescriptor]
DataDescriptor = Union[MutationDescriptor,
                       DestructiveDescriptor,
                       _DataDescriptor,
                       _NamedDataDescriptor]
"""
Part of the descriptor protocol.

See https://docs.python.org/3/howto/descriptor.html#descriptor-protocol.
"""


@runtime_checkable
class _Descriptor(_NonDataDescriptor,
                  _MutationDescriptor,
                  _DestructiveDescriptor,
                  Protocol):
    """
    The descriptor protocol.

    See https://docs.python.org/3/howto/descriptor.html#descriptor-protocol.
    """  # noqa: W505

    pass


@runtime_checkable
class _NamedDescriptor(_NonDataDescriptor,
                       _MutationDescriptor,
                       _DestructiveDescriptor,
                       _Named,
                       Protocol):
    """
    The descriptor protocol.

    See https://docs.python.org/3/howto/descriptor.html#descriptor-protocol.
    """  # noqa: W505

    pass


Descriptor = Union[DataDescriptor,
                   NonDataDescriptor,
                   _Descriptor,
                   _NamedDescriptor]
"""
The descriptor protocol.

See https://docs.python.org/3/howto/descriptor.html#descriptor-protocol.
"""


class descriptor(Generic[_T]):
    """
    A base class for custom descriptors.

    See https://docs.python.org/3/howto/descriptor.html#descriptorhowto
    for more information about writing descriptors.
    """

    def __init__(
            self,
            func: Union[Callable[...,
                                 Any],
                        Descriptor],
            require_read: bool = False,
            require_write: bool = False,
            require_delete: bool = False) -> None:
        if (not callable(func)
                and not ((require_read and hasattr(func,
                                                   "__get__")) or  # noqa: W504
                         (require_write and hasattr(func,
                                                    "__set__")) or  # noqa: W504
                         (require_delete and hasattr(func,
                                                     "__delete__")))):
            raise TypeError(
                f"{repr(func)} is not callable or a valid descriptor")
        self._f = func
        self._isclassmethod: bool
        if isinstance(func, descriptor):
            self._isclassmethod = func._isclassmethod
        else:
            self._isclassmethod = isinstance(func, (classmethod, staticmethod))
        self._isproperty = isinstance(func, (property, cached_property))
        self._f_name: Optional[str]
        self._f_name = None
        self.__doc__ = func.__doc__

    def __set_name__(self, owner: Type[_T], name: str):
        """
        Set the name of the descriptor.

        Parameters
        ----------
        owner : Type[T]
            The class defining the cached method.
        name : str
            The name of the attribute to which this descriptor is
            assigned.

        Raises
        ------
        TypeError
            If one attempts to alter the name of the descriptor.
        """
        if hasattr(self._f, '__set_name__'):
            self._f.__set_name__(owner, name)  # type: ignore
        # else: _f does not implement this part of descriptor protocol
        if self._f_name is None:
            self._f_name = name
            self._owner = owner
        elif name != self._f_name:
            raise TypeError(
                "Cannot assign the same descriptor to two different names "
                f"({self._f_name!r} and {name!r}).")
        if self._owner is None:
            self._owner = owner
        elif owner != self._owner:
            raise TypeError(
                "Cannot assign the same descriptor to two different types "
                f"({self._owner!r} and {owner!r}).")

    def __get__(self, _instance: _T, _owner: Optional[Type[_T]] = None) -> Any:
        """
        Reject attempts to get the descriptor.
        """
        raise AttributeError(f"unreadable attribute {self._f_name}")

    def __set__(self, _instance: _T, _value: Any) -> None:
        """
        Reject attempts to overwrite the descriptor.
        """
        raise AttributeError(f"can't set attribute {self._f_name}")

    def __delete__(self, _instance: _T) -> None:
        """
        Reject attempts to delete the descriptor.
        """
        raise AttributeError(f"can't delete attribute {self._f_name}")


class _cachedmethod(descriptor[_T]):
    """
    Internal implementation of cached methods.

    See Also
    --------
    cachedmethod: For public API.
    """

    # NOTE (AG): It looks like I chose a poor example to emulate caching
    # when basing this on functools.cached_property. Track the
    # resolution of https://github.com/python/cpython/issues/87634.

    cachedmethods = "_cachedmethods"
    cachedclassmethods = "_cachedclassmethods"  # includes static
    registry_lock = RLock()

    def __init__(
            self,
            func: Callable[...,
                           Any],
            *,
            maxsize: Optional[int] = None,
            **kwargs) -> None:
        super().__init__(func, require_read=True)
        self.cache_name: str
        kwargs.update({'maxsize': maxsize})
        self.cache_kwargs = kwargs
        self.lock = RLock()

    def __set_name__(self, owner: Type[_T], name: str):
        """
        Set the name of the descriptor and cache.

        Parameters
        ----------
        owner : Type[T]
            The class defining the cached method.
        name : str
            The name of the attribute to which this descriptor is
            assigned.

        Raises
        ------
        TypeError
            If one attempts to alter the name of the descriptor.
        """
        super().__set_name__(owner, name)
        self.cache_name = self.get_cache_name(name, owner)
        # take the opportunity to create the cached method registry
        # two new attributes are added to the owner class
        with self.registry_lock:
            if self._isclassmethod:
                registry_name = self.cachedclassmethods
            else:
                registry_name = self.cachedmethods
            # does registry exist?
            try:
                registry = getattr(owner, registry_name)
            except AttributeError:
                registry = {}
                setattr(owner, registry_name, registry)
            # is the desciptor owner registered?
            try:
                registry = registry[owner]
            except KeyError:
                temp: Set[str] = set()
                registry[owner] = temp
                registry = temp
            # is this method registered?
            if name not in registry:
                # register it
                registry.add(name)

    def __get__(self, instance: _T, owner: Optional[Type[_T]] = None) -> Any:
        """
        Retrieve the cached method wrapper.

        Each instance of the class is assigned its own cache.

        Parameters
        ----------
        instance : T
            An instance of the cached method owner.
        owner : type, optional
            The type of the instance, by default None.

        Returns
        -------
        callable
            The instance method wrapped with a caching mechanism.

        Notes
        -----
        On first invocation on a given `instance`, a wrapper for the
        instance's method that manages the cache is created and assigned
        to the attribute ``self.cache_name``.
        """
        if instance is None and owner is None:
            return self
        obj: Union[_T, Optional[Type[_T]]]
        if self._isclassmethod:
            obj = owner
        else:
            obj = instance
        if owner is None:
            assert instance is not None
            owner = type(instance)
        if obj is not None:
            try:
                return getattr(obj, self.cache_name)
            except AttributeError:
                with self.lock:
                    # check to see if another thread created the cache
                    # while we waited for the lock
                    try:
                        return getattr(obj, self.cache_name)
                    except AttributeError:
                        cache_fun = lru_cache(**self.cache_kwargs)
                        assert isinstance(self._f, _NonDataDescriptor)
                        cache_fun = cache_fun(self._f.__get__(instance, owner))
                        if self._isclassmethod:
                            assert isinstance(obj, type)
                            type.__setattr__(obj, self.cache_name, cache_fun)
                        else:
                            object.__setattr__(obj, self.cache_name, cache_fun)
                        return cache_fun
        else:
            # obj can only be None if a class tried to call an instance
            # method
            assert isinstance(self._f, _NonDataDescriptor)
            return self._f.__get__(instance, owner)

    def __set__(self, _instance: _T, _value: Any) -> None:
        """
        Reject attempts to overwrite the method.
        """
        raise AttributeError(f"Cannot set cached method {self._f_name}")

    @staticmethod
    def clear_cachedmethod_cache(
            registry_name: str,
            self: _T,
            methods: Optional[Union[str,
                                    Iterable[str]]] = None) -> None:
        """
        Clear method caches of an instance or class.

        This function keeps the implementation of the caches hidden from
        the user.

        Parameters
        ----------
        registry_name : str
            Identifies the registry of cached methods.
            Used to distinguish between cached class methods and cached
            instance methods in the event ``None`` is provided for
            `methods`.
        self : T
            An instance of the class with a cached method.
        methods : Union[str, Iterable[str]] or None
            The names of the method(s) whose cache(s) should be cleared.
            If None, then clear all methods' caches. By default None.
            Unknown method names are ignored.
        """
        try:
            registry = getattr(self, registry_name)
        except AttributeError:
            # no caches have been initialized yet
            return
        if isinstance(methods, str):
            methods = {methods}
        elif methods is not None and not isinstance(methods, set):
            methods = set(methods)
        for owner, owned_methods in registry.items():
            if methods is None:
                ms = owned_methods
            else:
                ms = methods.intersection(owned_methods)
            for m in ms:
                cache_name = _cachedmethod.get_cache_name(m, owner)
                if hasattr(self, cache_name):
                    getattr(self, cache_name).cache_clear()

    @staticmethod
    def get_cache_name(method_name: str, owner: Type[_T]) -> str:
        """
        Return the canonical name of a method's cache.

        Parameters
        ----------
        method_name : str
            The name of a method.
        owner : type
            The class that owns the method.

        Returns
        -------
        str
            The name of the corresponding cache.
        """
        return f'_{method_name}_{owner.__module__}_{owner.__name__}_cache'


# once yapf and other tools support positional-only parameters, alter
# the definition to ``def cachedmethod(f, /, *, ...)``
def cachedmethod(
    _func: Optional[Callable[...,
                             Any]] = None,
    *,
    maxsize: Optional[int] = None,
    **kwargs: Dict[str,
                   Any]
) -> Union[_cachedmethod,
           Callable[[Callable[...,
                              Any]],
                    _cachedmethod]]:
    """
    Make a cached method decorator.

    A wrapper around a method that caches args and results.
    Analogue to the `functools.cache` decorator but applied instance
    methods such that each instance of a class obtains an independent
    cache for the decorated method.
    Note that a cached method should be free of side-effects and not
    depend on mutable instance state that could cause the cached values
    to become stale.
    See the `mutable_method_caches` class decorator if one wants to
    cache mutable methods regardless.
    `cachedmethod` may be applied to class and static methods as well,
    but it is functionally equivalent to `functools.cache` unless
    mutability is desired.

    Parameters
    ----------
    _func : callable
        The method to be wrapped with a caching mechanism.
        The arguments to `f` must be hashable.
        This argument should not be called by keyword and must be
        provided positionally.
    maxsize : int or None, optional
        The maximum size of the cache, by default unbounded.
    kwargs
        Additional keyword arguments to `lru_cache`.

    Returns
    -------
    _cachedmethod
        Internal implementation of a cached instance method.

    See Also
    --------
    mutable_method_caches
    functools.cache
    lru_cache

    Examples
    --------
    >>> @dataclass
    ... class Example:
    ...     x : float
    ...
    ...     @cachedmethod
    ...     def f(self, y : float):
    ...         print(f"Argument: {y}")
    ...         return y*self.x
    ...
    >>> ex = Example(2.0)
    >>> ex.f(3.0)
    Argument: 3.0
    6.0
    >>> ex.f(3.0)
    6.0
    >>> ex2 = Example(4.0)
    >>> ex2.f(3.0)
    Argument: 3.0
    12.0
    >>> ex2.f(3.0)
    12.0
    >>> ex.f(3.0)
    6.0
    """

    def wrap(func):
        return _cachedmethod(func, maxsize=maxsize, **kwargs)

    # See if we're called as @cachedmethod or @cachedmethod()
    if _func is None:
        # called as @cachedmethod()
        return wrap

    # called without parentheses
    return wrap(_func)


def mutable_method_caches(cls):
    """
    Expose interface for making a class's method caches mutable.

    If one wants to cache a method that acts on mutable state (for
    example, if the rate of mutation is relatively slow), then one
    should manually clear the cache of affected methods whenever the
    mutation occurs.
    This decorator adds two convenience functions to the class for this
    purpose: `clear_cachedmethods_cache`, which accepts
    an optional list of cached method names for purging their caches in
    a particular instance, and
    `clear_cachedclassmethods_cache`, which performs the
    same service for class and static methods.

    .. warning::
        Class and static method caches are shared across all subclasses.
        Thus, if one clears a cache of a parent or subclass, one also
        clears the cache of the subclass or parent.
    """
    setattr(
        cls,
        f"clear{_cachedmethod.cachedmethods}_cache",
        partialmethod(
            partial(
                _cachedmethod.clear_cachedmethod_cache,
                _cachedmethod.cachedmethods)))
    setattr(
        cls,
        f"clear{_cachedmethod.cachedclassmethods}_cache",
        classmethod(
            partial(
                _cachedmethod.clear_cachedmethod_cache,
                _cachedmethod.cachedclassmethods)))
    return cls


def unzip(zipped: Iterable[Tuple[Any, ...]]) -> Tuple[Iterable[Any], ...]:
    """
    Unzip an iterable of tuples.

    Note that if the size of the tuples are not constant, this may have
    unexpected results with larger tuples' elements being dropped.

    Parameters
    ----------
    zipped : iterable of tuples
        A zip object or other iterator over tuples of arbitrary type.

    Returns
    -------
    unzipped : tuple of iterables
        A tuple of iterators over each projection of the original tuple
        elements.

    Examples
    --------
    >>> unzip(enumerate([3,4,5]))
    ((0, 1, 2), (3, 4, 5))
    >>> unzip(zip(range(4), range(100)))
    ((0, 1, 2, 3), (0, 1, 2, 3))
    """
    return tuple(zip(*zipped))
