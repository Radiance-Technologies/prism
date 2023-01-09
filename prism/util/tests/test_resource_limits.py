"""
Test suite for alignment algorithms and utilities.
"""
import re
import unittest
from resource import getrlimit
from typing import Dict, Union

from seutil import bash

from prism.util.resource_limits import (
    ProcessResource,
    subprocess_resource_limiter,
)


def command_usage():
    """
    Return command prefix to output resource usage.
    """
    return "/usr/bin/time -f 'Elapsed time: %es\\nMemory usage: %M KB\\nCPU usage: %P'"


def command_memory(amt: int) -> float:
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
    py_str = f"print([1 for _ in range(int({amt}))])"
    cmd = f"python -c '{py_str}'"
    return f"{command_usage()} {cmd}"


def command_time(amt: int) -> float:
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
    cmd = f"sleep {amt}"
    return f"{command_usage()} {cmd}"


def get_memory(amt: int):
    """
    Get memory usage for command with given argument.
    """
    return parse_memory_output(bash.run(command_memory(amt)).stderr)


def get_time(amt: int):
    """
    Get runtime for command with given argument.
    """
    return parse_time_output(bash.run(command_time(amt)).stderr)


def parse_memory_output(text):
    """
    Extract memory usage from command output.
    """
    subtext = re.findall(r'Memory usage: \d+.*', text)[0]
    return int(re.findall(r'\d+', subtext)[0])


def parse_time_output(text):
    """
    Extract runtime from command output.
    """
    subtext = re.findall(r'Elapsed time: \d+.*', text)[0]
    return float(re.findall(r"\d+\.\d+", subtext)[0])


def get_commands(time: int,
                 memory: int) -> Dict[ProcessResource,
                                      Union[int,
                                            float]]:
    """
    Return commands to get test resources.

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
        ProcessResource.MEMORY: command_memory(memory),
        ProcessResource.RUNTIME: command_time(time)
    }


def get_usage(time: int,
              memory: int) -> Dict[ProcessResource,
                                   Union[int,
                                         float]]:
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
        ProcessResource.MEMORY: get_memory(memory) * 1e3,
        ProcessResource.RUNTIME: get_time(time)
    }


class TestResourceLimits(unittest.TestCase):
    """
    Test suite for resource limit utilities.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Get limits of current process.
        """
        cls.current_limits = {}
        cls.current_limits[ProcessResource.MEMORY] = getrlimit(
            ProcessResource.MEMORY.value)
        cls.current_limits[ProcessResource.RUNTIME] = getrlimit(
            ProcessResource.RUNTIME.value)

    def test_limiter(self):
        """
        Check limiter can be executed.
        """
        ProcessResource.limit_current_process(self.current_limits)
        limiter = subprocess_resource_limiter(
            memory=self.current_limits[ProcessResource.MEMORY],
            runtime=self.current_limits[ProcessResource.RUNTIME])
        limiter()

    def run_subprocess_test(self, resource: ProcessResource):
        """
        Check that subprocess resource limits work.
        """
        usage_limit = get_usage(2, 1e6)[resource]
        limiter_kwargs = {
            resource.name.lower(): int(usage_limit)
        }
        limiter = subprocess_resource_limiter(**limiter_kwargs)
        kwargs = {
            'preexec_fn': limiter
        }
        with self.subTest("Under limit"):
            under_cmd = get_commands(1, 2)[resource]
            under_usage = get_usage(1, 2)[resource]
            self.assertLess(under_usage, usage_limit)
            output = bash.run(under_cmd, **kwargs)
            self.assertEqual(output.returncode, 0)
        with self.subTest("over limit"):
            over_cmd = get_commands(3, 1e9)[resource]
            over_usage = get_usage(3, 1e9)[resource]
            self.assertGreater(over_usage, usage_limit)
            output = bash.run(over_cmd, **kwargs)
            self.assertEqual(output.returncode, 11)

    def test_memory(self):
        """
        Check that memory usage can be limited.
        """
        self.run_subprocess_test(ProcessResource.MEMORY)

    def test_time(self):
        """
        Check that runtime can be limited.
        """
        self.run_subprocess_test(ProcessResource.RUNTIME)


if __name__ == '__main__':
    unittest.main()
    # test = TestResourceLimits()
    # test.setUpClass()
    # test.test_limiter()
    # test.test_memory()
    # test.test_time()
