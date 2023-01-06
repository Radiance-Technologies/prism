"""
Test suite for alignment algorithms and utilities.
"""
import os
import time
import unittest
import re
from resource import getrlimit, setrlimit
from typing import Callable, Optional, Dict, Union
from seutil import bash

import psutil

from prism.util.resource_limits import (
    MaxRuntimeError,
    ProcessResource,
    ResourceLimits,
    ResourceMapValueDict,
    subprocess_resource_limiter
)


def _under_limit(resource: ProcessResource, offset: int = None):
    """
    Set resource limit, call function, and change limit back.

    Parameters
    ----------
    resource : ProcessResource
        Resource whose limit will be set.
    """
    if resource is ProcessResource.MEMORY:
        if offset is None:
            offset = process.memory_info().rss
        a = 1
        process = psutil.Process(os.getpid())
        soft, _ = getrlimit(resource.value)
        array = [a]* (int(((soft - process.memory_info().rss) - 64 - 8)/8) - 1)
    if resource is ProcessResource.RUNTIME:
        if offset is None:
            offset = 1
        time.sleep(offset)

def _over_limit(resource: ProcessResource, offset: int = None):
    """
    Set resource limit, call function, and change limit back.

    Parameters
    ----------
    resource : ProcessResource
        Resource whose limit will be set.
    """
    if resource is ProcessResource.MEMORY:
        if offset is None:
            offset = process.memory_info().rss
        a = 1
        process = psutil.Process(os.getpid())
        soft, _ = getrlimit(resource.value)
        array = [a]* (int(((soft - process.memory_info().rss) - 64 - 8)/8) - 1)
    if resource is ProcessResource.RUNTIME:
        if offset is None:
            offset = 1
        time.sleep(offset)


def get_time(text):
    subtext = re.findall(r'Elapsed time: \d+.*', text)[0]
    return float(re.findall(r"\d+\.\d+", subtext)[0])

def get_memory(text):
    subtext = re.findall(r'Memory usage: \d+.*', text)[0]
    return int(re.findall(r'\d+', subtext))

def time_command(amt: int) -> float:
    """
    Run sleep command for `amt` seconds.

    Parameters
    ----------
    amt : int
        Number of seconds to sleep.

    Returns
    -------
    float
        Amount of time the process ran.
    """
    return f"/usr/bin/time -f 'Elapsed time: %es\\nMemory usage: %M KB\\nCPU usage: %P' sleep {amt}"

def get_time_command_time(amt:int)
    return get_time(bash.run(time_command(amt)).stderr)


def memory_command(amt: int) -> float:
    """
    Run echo numbers from 1 to `amt`.

    This will consume more memory for larger values.

    Parameters
    ----------
    amt : int
        Max number to echo.

    Returns
    -------
    float
        Amount of memory used in the process.
    """
    cmd = "/usr/bin/time -f 'Elapsed time: %es\\nMemory usage: %M KB\\nCPU usage: %P' echo \{1..{amt}\}".format(amt=amt)
    return get_memory(bash.run(cmd).stderr)


def get_limits(time: int, memory: int) -> Dict[ProcessResource, Union[int,float]]:
    """
    Return amount of resources used by commands with given arguments.

    Parameters
    ----------
    time : int
        Amount of time to sleep
    memory : int
        Max number to echo.

    Returns
    -------
    Dict[ProcessResource, Union[int,float]]
        Dictionary between ProcessResource types
        and a max resource usage given arguments.
    """
    return {
        ProcessResource.MEMORY: memory_command(memory),
        ProcessResource.RUNTIME: time_command(time)
    }


class TestResourceLimits(unittest.TestCase):
    """
    Test suite for resource limit utilities.
    """

    def _set_soft_limit(self, resource: ProcessResource, soft: int, after_set: Optional[Callable[[int]]]=None):
        """
        Set resource limit, call function, and change limit back.

        Parameters
        ----------
        resource : ProcessResource
            Resource whose limit will be set.
        """
        prev_soft, prev_hard = getrlimit(resource.value)
        rss_map_value_dict: ResourceMapValueDict = {'soft': soft}
        resource.limit_current_process(rss_map_value_dict)
        try:
            if after_set is not None:
                after_set()
        except Exception as exc:
            raise exc
        finally:
            setrlimit(resource.value, (prev_soft, prev_hard))

    def test_limit_set_unchanged(self):
        """
        Test that resource limits can be set without error.
        """
        for resource in ProcessResource:
            with unittest.subtest(resource.name):
                soft, _ = getrlimit(resource.value)
                self._set_soft_limit(resource, soft)

    def test_bash(self):
        """
        Test that resource limits can be set without error.
        """
        limits = get_limits(1, 1000)
        for resource, limit in limits.items():
            with unittest.subtest(resource.name):
                soft, hard = getrlimit(resource.value)
                # Limits resources allowed to be used by bash command
                kwargs = {resource.name: limit}
                limiter = subprocess_resource_limiter(**kwargs)
                kwargs['preexec_fn'] = preexec_fn
                bash.run(command, **kwargs)



if __name__ == '__main__':
    unittest.main()
