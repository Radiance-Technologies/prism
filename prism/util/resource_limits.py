"""
Miscellaneous console-related utilities.
"""
import os
import resource
import signal
import time
import warnings
from enum import IntEnum
from subprocess import TimeoutExpired
from typing import Callable, Dict, Optional, Tuple, TypedDict, Union

import psutil


def get_SIGXCPU_handler(soft: int):
    """
    Create function to raise `TimeoutExpired` when called.

    The fuction return is intended to passed to `signal.signal`.
    https://docs.python.org/3.8/library/signal.html#signal.signal
    """

    def signal_handler(*args):
        raise TimeoutExpired('', soft)

    return signal_handler


def get_SIGALRM_handler(soft):
    """
    Create function to check runtime when alarm is raised.

    If runtime has been exceed by time alarm is called, then
    the returned function will send a `signal.SIGXCPU` to the
    current process. Results of previous step will depende on
    if `signal.alarm` is called in subprocess or main process.

    The fuction returned is intended to passed to `signal.signal`.
    https://docs.python.org/3.8/library/signal.html#signal.signal

    The function returned assumes `signal.alarm(soft)` has been called
    prior to when the runtime counter would starts. It is only
    neccessary to use this function for `ProcessResource.RUNTIME`
    limits because python doesn't automatically handle sending a
    signal.SIGXCPU signal when runtime is exceeded.
    """
    start = time.time()

    def signal_handler(*args):
        if soft is not None and soft > -1 and time.time() - start >= soft:
            psutil.Process(os.getpid()).send_signal(signal.SIGXCPU)

    return signal_handler


ResourceLimits = Union[int, Tuple[int, int]]
"""
A max size for a resource.

If an int is given, it is assumed to be a soft limit. If a
2-tuple of ints are given, the 0 index is taken to be a soft
limit and 1 index is taken to be the hard limit.
"""


def split_limit(
        limit: Optional[ResourceLimits]) -> Tuple[Optional[int],
                                                  Optional[int]]:
    """
    Determine soft and hard limit from a ResourceLimit.

    Parameters
    ----------
    limit : Optional[ResourceLimits]
        A resource limit, or None.

    Returns
    -------
    Tuple[Optional[int], Optional[int]]
        Tuple containing soft and hard limit.
    """
    if limit is None:
        soft = None
        hard = None
    elif isinstance(limit, int):
        soft = limit
        hard = None
    elif len(limit) == 1:
        soft = limit[0]
        hard = None
    elif len(limit) == 2:
        soft = limit[0]
        hard = limit[1]
    return soft, hard


class ResourceMapValueDict(TypedDict):
    """
    Dictionary of keywords used to set resource limits.
    """

    soft: Optional[int]
    """
    Soft resource limit. Does not result in SIGKILL signal
    when passed. Specific signal depends on resource.
    By default, None.
    """
    hard: Optional[int]
    """
    Hard resource limit. Results in SIGKILL signal
    when passed. By default, None.
    """


def _value_to_valuedict(value: ResourceLimits) -> ResourceMapValueDict:
    """
    Return a ResourceMapValueDict that contains the given value.

    Parameters
    ----------
    value : ResourceLimits
        Value to place in ResourceMapValueDict

    Returns
    -------
    ResourceMapValueDict
        Dictionary mapping the value data to
        specific keys in ResourceMapValueDict.
    """
    value_dict: ResourceMapValueDict = {}
    soft, hard = split_limit(value)
    if soft is not None:
        value_dict['soft'] = soft
    if hard is not None:
        value_dict['hard'] = hard
    return value_dict


def _repeated_valuedict_keys_msg(resource_name: str, key: str) -> str:
    """
    Return message for repeated values corresponding to same resource.

    Parameters
    ----------
    resource_name : str
        Resource name
    key : str
        A ResourceMapValueDict key.

    Returns
    -------
    str
        Messaging describing which resource name has repeated values.

    Raises
    ------
    ValueError
        Key is not a key expected by ResourceMapValueDict.
    """
    if key == "soft":
        name = "soft limit"
    elif key == "hard":
        name = "hard limit"
    else:
        raise ValueError(f"Unexpected key ('{key}') for ResourceMapValueDict")
    return f"Multiple {name}s given for {resource_name}"


class ProcessResource(IntEnum):
    """
    Enumeration of resources thatcan be limited.
    """

    MEMORY: int = resource.RLIMIT_AS
    """
    The maximum area (in bytes) of address space which may be taken
    by the process.
    """

    RUNTIME: int = resource.RLIMIT_CPU
    """
    The maximum amount of processor time (in seconds) that a
    process can use. If this limit is exceeded, a SIGXCPU signal
    is sent to the process.
    """

    def _limit_current_process(
            self,
            rss_map_value_dict: ResourceMapValueDict,
            start_alarm: bool = False,
            alarm_offset: int = 0):
        """
        Limit the resource usage of the current process.

        Parameters
        ----------
        rss_map_value_dict: ResourceMapValueDict
            Dictionary containing soft limit, hard limit, and
            resource specific exception. See ResourceMapValueDict
            for details.
        start_alarm : bool, optional
            If True call signal.alarm using soft limit
        alarm_offset : int, optional
            Number of seconds to add runtime. The added time
            accounts for time between context creation and
            start of subprocess or time limited function code.

        Raises
        ------
        ValueError
            An exception was given when `self` was not
            `ProcessResource.RUNTIME`.
        """
        # Get existing limits
        existing = resource.getrlimit(self.value)
        # Get requested soft and hard limits
        soft = rss_map_value_dict.get('soft', None)
        hard = rss_map_value_dict.get('hard', None)
        # Use existing limit when requested limit is None.
        if soft is None and hard is not None:
            # Use existing soft limit and requested hard limit.
            soft = existing[0]
            if hard > 0 and soft > hard:
                # Lower existing soft limit so that it's not larger
                # than requested hard limit.
                warnings.warn(
                    f"Lowering existing {self.name} soft limit ({soft})"
                    f" to match requested {self.name} hard limit ({hard}).")
                soft = hard
        elif hard is None and soft is not None:
            # Use existing hard limit and requested soft limit.
            hard = existing[1]
        elif soft is None and hard is None:
            soft, hard = existing

        # Only set limits if one or both limits are given.
        # If invalid pair is used, `setrlimit` will raise a
        # ValueError exception.
        limits = (soft, hard)
        resource.setrlimit(self.value, limits)

        # Set handler for signal when limit is passed that
        # raises the given exception.
        if self == ProcessResource.RUNTIME and soft is not None:

            # Depending on the process being resource limited
            # a SIGXCPU signal may not sent automatically.
            # So instead we rely on an external triggered alarm signal
            # to be sent to tell us to send the SIGXCPU signal.
            signal.signal(signal.SIGALRM, get_SIGALRM_handler(soft))
            # signal.SIGXCPU is sent when runtime is exceeded, or
            # from handler in expression above when alarm signal is
            # sent.
            signal.signal(signal.SIGXCPU, get_SIGXCPU_handler(soft))
            if start_alarm:
                # Starting the alarm here in a subprocess's preexec_fn
                # will result in a returncode of -14.
                # Otherwise it will result in a resource specific
                # exception being raised with return code 1.
                signal.alarm(soft + alarm_offset)
            else:
                # Warn the user that they should be maintaing the alarm
                # if they want the signal.SIGXCPU to ever be sent once
                # runtime limit is passed.
                warnings.warn(
                    "User has to manually monitor and send"
                    " `signal.SIGXCPU` signal themselves when"
                    " when runtime is exceeded. Or pass `start_alarm=True`"
                    " to `ProcessResource.limit_current_process`.")

    @classmethod
    def create_resource_map(
        cls,
        kwargs: Dict[Union[str,
                           int,
                           'ProcessResource'],
                     ResourceLimits]
    ) -> Dict['ProcessResource',
              ResourceMapValueDict]:
        """
        Create map between resources and limits/exception.

        Returns
        -------
        Dict['ProcessResource', ResourceMapValueDict]
            A mapping between a specific resource and the limits
            on that resource, as well as the exception raised
            when the soft resource limit is exceeded.

        Raises
        ------
        ValueError
            Multiple soft limits, hard limits, or exceptions
            were given for the same resource.
        """
        resource_map = {}
        for rss in kwargs:
            value = kwargs[rss]
            if not isinstance(value, dict):
                value_dict = _value_to_valuedict(value)
            else:
                value_dict = value

            # Convert resource to ProcessResource
            rss = cls.get(rss)

            # Add values to resource map
            if rss not in resource_map:
                resource_map[rss] = {}
            for k in value_dict:
                if k in resource_map[rss]:
                    raise ValueError(_repeated_valuedict_keys_msg(rss.name, k))
            resource_map[rss].update(value_dict)
        return resource_map

    @classmethod
    def get(cls, rss: Union[int, str, 'ProcessResource']) -> 'ProcessResource':
        """
        Return correct ProcessResource type for given value.

        Parameters
        ----------
        rss : Union[int, str, ProcessResource]
            The integer value of the resource or resource name.
            Passing a `ProcessResource` results in returning the
            value back unchanged.

        Returns
        -------
        ProcessResource
            A process resource.

        Raises
        ------
        TypeError
            The type of `rss` is not an
            integer or string.
        """
        # Convert resource to ProcessResource
        if isinstance(rss, str):
            rss = cls[rss.upper()]
        elif isinstance(rss, int):
            rss = cls(rss)
        elif isinstance(rss, ProcessResource):
            pass
        else:
            raise TypeError(
                "Integer value of resource or resource name expected.")
        return rss

    @classmethod
    def limit_current_process(
        cls,
        limits: Optional[Dict[Union[str,
                                    int,
                                    'ProcessResource'],
                              ResourceLimits]] = None,
        start_alarm: bool = False,
        alarm_offset: int = 0,
    ):
        """
        Limit the resource usage of the current process.

        If this is being called in a subprocess's `preexec_fn`
        function then `start_alarm=True` will result in return code
        of -14 from the subprocess. If `start_alarm=False` then the
        alarm should be started (via `signal.alarm(...)`) prior to
        subprocess start in parent process. In the case of the latter,
        an exception will be raised in the main thread if RUNTIME is
        exceeded.

        Parameters
        ----------
        limits: Optional[Dict[Union[str, int, 'ProcessResource'],
                         ResourceLimits]], optional
            A dictionary mapping different ProcessResource(s)
            to resource limits.
        start_alarm : bool, optional
            If True call signal.alarm using soft limit
        alarm_offset : int, optional
            Number of seconds to add runtime. The added time
            accounts for time between context creation and
            start of subprocess or time limited function code.
        """
        if limits is not None:
            # Aggregate limits and exceptions into single dictionary
            # that uses `ProcessResource` as keys and keyword
            # arguments of the
            # `ProcessRsource.<value>._limit_current_process` method
            # as values.
            resource_map = cls.create_resource_map(limits)

            # Apply resource constraints.
            for rss, rss_map_value_dict in resource_map.items():
                if rss == cls.RUNTIME:
                    kw = {
                        'start_alarm': start_alarm,
                        'alarm_offset': alarm_offset,
                    }
                else:
                    kw = {}
                rss._limit_current_process(rss_map_value_dict, **kw)


def get_resource_limiter_callable(
    memory: Optional[ResourceLimits] = None,
    runtime: Optional[ResourceLimits] = None,
    start_alarm: bool = False,
    alarm_offset: int = 0,
) -> Callable[[],
              None]:
    """
    Return function limits resources that when called.

    Parameters
    ----------
    memory : Optional[ResourceLimits], optional
        Maximum memory allowed, by default None
    runtime : Optional[ResourceLimits], optional
        maximum time allowed, by default None
    start_alarm : bool, optional
        If True call signal.alarm using soft limit
        after setting the limit.
    alarm_offset : int, optional
        Number of seconds to add runtime. The added time
        accounts for time between calling the returned function
        and start of runtime limited code. Only used when
        `alarm_offset=True`.

    Returns
    -------
    Callable
        Function that can be called to limit resources of in calling
        process. Can be passed as `preexec_fn` keyword argument used
        in `subprocess` library.
    """

    def limiter():
        limits = {
            ProcessResource.MEMORY: memory,
            ProcessResource.RUNTIME: runtime
        }
        ProcessResource.limit_current_process(
            limits,
            start_alarm=start_alarm,
            alarm_offset=alarm_offset)

    return limiter


class ProcessLimiterContext:
    """
    Class to create context that handles alarms for resource limits.

    Using this context manager and passing instance as a subprocess's
    `preexec_fn` function will result in exception being raised in the
    parent process. To obtain the above functionality, use
    `subprocess=True` keyword argument.
    """

    def __init__(
            self,
            memory: Optional[ResourceLimits] = None,
            runtime: Optional[ResourceLimits] = None,
            alarm_offset: int = 0,
            subprocess: bool = False,
            **kwargs):
        """
        Return function limits resources that when called.

        Parameters
        ----------
        memory : Optional[ResourceLimits], optional
            Maximum memory allowed, by default None
        runtime : Optional[ResourceLimits], optional
            maximum time allowed, by default None
        alarm_offset : int, optional
            Number of seconds to add runtime. The added time
            accounts for time between context creation and
            start of subprocess or time limited function code.
        subprocess : bool, optional
            If True, instance must be called to set resource limits
            and alarm will be created at context creation. If False,
            then resource limits are set at context creation.
        """
        if memory is not None:
            kwargs['memory'] = memory
        if runtime is not None:
            kwargs['runtime'] = runtime
        self.limits = ProcessResource.create_resource_map(kwargs)
        if self._soft_limit(ProcessResource.RUNTIME) is not None:
            self.set_runtime_alarm = True
        else:
            self.set_runtime_alarm = False
        self.subprocess = subprocess
        self._cache = {}
        self._alarm_offset = alarm_offset

    def _cache_current_limits(self):
        """
        Create an in-memory cache of existing resource limits.
        """
        for rss in self.limits:
            self._cache[rss] = resource.getrlimit(rss.value)

    def _restore_limits(self):
        """
        Create an in-memory cache of existing resource limits.
        """
        for rss in self.limits:
            limit = self._cache.pop(rss)
            resource.setrlimit(rss.value, limit)

    def _soft_limit(self, rss: ProcessResource) -> Optional[int]:
        """
        Return soft limit of resource.

        Parameters
        ----------
        rss : ProcessResource
            A process resource.

        Returns
        -------
        Optional[int]
            Returns value from `self.limits` if present, otherwise
            returns None.
        """
        if rss in self.limits and "soft" in self.limits[rss]:
            return self.limits[rss]["soft"]
        return None

    def __enter__(self) -> 'ProcessLimiterContext':
        """
        Call process limiting functions.
        """
        if not self.subprocess:
            self._cache_current_limits()
            ProcessResource.limit_current_process(self.limits)
        if self.set_runtime_alarm:
            soft = self._soft_limit(ProcessResource.RUNTIME)
            signal.signal(signal.SIGALRM, get_SIGALRM_handler(soft))
            signal.alarm(soft + self._alarm_offset)
        return self

    def __exit__(self, type, value, traceback):
        """
        Disable alarm.
        """
        if not self.subprocess:
            self._restore_limits()
        if self.set_runtime_alarm:
            signal.alarm(0)

    def __call__(self):
        """
        Set resource Limits.
        """
        ProcessResource.limit_current_process(self.limits)
