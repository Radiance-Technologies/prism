"""
Subpackage containing functionality extracted from `radpytools`.
"""

from functools import lru_cache, partial, partialmethod
from multiprocessing import RLock
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
)

T = TypeVar('T')


class _cachedmethod:
    """
    Internal implementation of cached methods.

    See Also
    --------
    cachedmethod: For public API.
    """

    cachedmethods = "_cachedmethods"
    cachedclassmethods = "_cachedclassmethods"  # includes static
    registry_lock = RLock()

    def __init__(
            self,
            func: Callable[...,
                           Any],
            *,
            maxsize: Optional[int] = None,
            **kwargs: Dict[str,
                           Any]) -> None:
        if not callable(func) and not hasattr(func, "__get__"):
            raise TypeError(f"{repr(func)} is not callable or a descriptor")
        self._f = func
        self._isclassmethod = isinstance(func, (classmethod, staticmethod))
        self._f_name = None
        self.cache_name = None
        self.__doc__ = func.__doc__
        kwargs.update({'maxsize': maxsize})
        self.cache_kwargs = kwargs
        self.lock = RLock()

    def __set_name__(self, owner: Type[T], name: str):
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
        if self._f_name is None:
            self._f_name = name
            self._owner = owner
        elif name != self._f_name:
            raise TypeError(
                "Cannot assign the same cachedmethod to two different names "
                f"({self._f_name!r} and {name!r}).")
        if self._owner is None:
            self._owner = owner
        elif owner != self._owner:
            raise TypeError(
                "Cannot assign the same cachedmethod to two different types "
                f"({self._owner!r} and {owner!r}).")
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
                temp = set()
                registry[owner] = temp
                registry = temp
            # is this method registered?
            if name not in registry:
                # register it
                registry.add(name)

    def __get__(self, instance: T, owner: Type[T] = None):
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
        if self._isclassmethod:
            obj = owner
        else:
            obj = instance
        if owner is None:
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
                        cache_fun = cache_fun(self._f.__get__(instance, owner))
                        if self._isclassmethod:
                            type.__setattr__(obj, self.cache_name, cache_fun)
                        else:
                            object.__setattr__(obj, self.cache_name, cache_fun)
                        return cache_fun
        else:
            # obj can only be None if a class tried to call an instance
            # method
            return self._f.__get__(instance, owner)

    def __set__(self, _instance: T, _value: Any):
        """
        Reject attempts to overwrite the method.
        """
        raise AttributeError(f"Cannot set cached method {self._f_name}")

    @staticmethod
    def clear_cachedmethod_cache(
            registry_name: str,
            self: T,
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
    def get_cache_name(method_name: str, owner: Type[T]) -> str:
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
        _func: Callable[...,
                        Any] = None,
        *,
        maxsize: Optional[int] = None,
        **kwargs: Dict[str,
                       Any]) -> _cachedmethod:
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


def unzip(zipped: Iterable[Tuple]) -> Tuple[Iterable]:
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
