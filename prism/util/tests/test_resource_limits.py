"""
Test suite for alignment algorithms and utilities.
"""
import unittest
import os, psutil
import time
from typing import Callable, Optional
from resource import getrlimit, setrlimit
from prism.util.resource_limits import ResourceLimits, ProcessResource, MaxRuntimeError, ResourceMapValueDict


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

    def over_limit(resource: ProcessResource, offset: int = None):
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

    def test_limit_set_max(self):
        """
        Test that resource limits can be set without error.
        """
        for resource in ProcessResource:
            with unittest.subtest(resource.name):
                , _ = getrlimit(resource.value)
                self._set_soft_limit(resource, soft)



if __name__ == '__main__':
    unittest.main()
