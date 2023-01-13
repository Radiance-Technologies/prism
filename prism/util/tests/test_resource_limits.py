"""
Test suite for alignment algorithms and utilities.
"""
import logging
import resource
import unittest
import warnings
from resource import getrlimit
from subprocess import TimeoutExpired

from prism.tests.resource import ResourceTestTool
from prism.util.resource_limits import (
    ProcessLimiterContext,
    ProcessResource,
    get_resource_limiter_callable,
)

warnings.filterwarnings("ignore")

logger = logging.getLogger()


class TestResourceLimits(unittest.TestCase):
    """
    Test suite for resource limit utilities.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Get limits of current process.
        """
        cls.tool = {
            ProcessResource.MEMORY: ResourceTestTool.run_memory_cmd,
            ProcessResource.RUNTIME: ResourceTestTool.run_runtime_cmd,
        }
        cls.key = {
            ProcessResource.MEMORY: ResourceTestTool.MEMORY_KEY,
            ProcessResource.RUNTIME: ResourceTestTool.RUNTIME_KEY,
        }
        # Factor to add between limits(under, at, over).
        cls.fudge_Factor = {
            ProcessResource.MEMORY: int(100e6),  # 100 MB
            ProcessResource.RUNTIME: 2,  # 2 seconds
        }

        cls.current_limits = {}
        cls.offset = {}
        cls.limit = {}
        cls.under_limit = {}
        cls.over_limit = {}
        for rss, tool in cls.tool.items():
            fudge_factor = cls.fudge_Factor[rss]
            output, usage = tool(0)
            logger.info("STDOUT: ", output.stdout)
            logger.info("STDERR: ", output.stderr)
            logger.info("RETURNCODE: ", output.returncode)
            offset = int(usage[cls.key[rss]])  # smallest value
            under_limit = offset + fudge_factor
            limit = under_limit + fudge_factor
            over_limit = limit + fudge_factor
            cls.offset[rss] = offset
            cls.under_limit[rss] = under_limit
            cls.limit[rss] = limit
            cls.over_limit[rss] = over_limit
            cls.current_limits[rss] = getrlimit(rss.value)

    def test_limiter(self):
        """
        Check limiter can be executed.
        """
        ProcessResource.limit_current_process(self.current_limits)
        limiter = get_resource_limiter_callable(
            memory=self.current_limits[ProcessResource.MEMORY],
            runtime=self.current_limits[ProcessResource.RUNTIME])
        limiter()
        soft_, _ = resource.getrlimit(ProcessResource.MEMORY.value)
        with ProcessLimiterContext(memory=int(1e10),
                                   subprocess=False) as limiter:
            limiter()
            soft, _ = resource.getrlimit(ProcessResource.MEMORY.value)
            self.assertEqual(soft, int(1e10))
        soft, _ = resource.getrlimit(ProcessResource.MEMORY.value)
        self.assertEqual(soft, soft_)

    def run_subprocess_test(
            self,
            rss: ProcessResource,
            returncode: int,
            exception: Exception):
        """
        Check that subprocess resource limits work.
        """
        TOOL = self.tool[rss]
        KEY = self.key[rss]
        LIMIT = self.limit[rss]
        kwargs = {
            rss.name.lower(): LIMIT
        }
        with self.subTest("Under Limit"):
            subtest_limit = self.under_limit[rss]
            output, usage = TOOL(subtest_limit)
            subtest_usage = usage[KEY]
            self.assertLess(subtest_usage, LIMIT)
            with ProcessLimiterContext(subprocess=True, **kwargs) as limiter:
                output, usage = TOOL(subtest_limit, preexec_fn=limiter)
                self.assertEqual(output.returncode, 0)
        with self.subTest("Over limit"):
            subtest_limit = self.over_limit[rss]
            output, usage = TOOL(subtest_limit)
            subtest_usage = usage[KEY]
            self.assertGreater(subtest_usage, self.limit[rss])
            with ProcessLimiterContext(subprocess=True, **kwargs) as limiter:
                if exception is not None:
                    self.assertRaises(
                        exception,
                        TOOL,
                        subtest_limit,
                        preexec_fn=limiter)
                else:
                    output, usage = TOOL(subtest_limit, preexec_fn=limiter)
                    self.assertEqual(output.returncode, returncode)
            kwargs['start_alarm'] = True
            kwargs['alarm_offset'] = 0
            limiter = get_resource_limiter_callable(**kwargs)
            output, usage = TOOL(subtest_limit, preexec_fn=limiter)
            self.assertEqual(output.returncode, returncode)

    def test_memory(self):
        """
        Check that memory usage can be limited.
        """
        self.run_subprocess_test(ProcessResource.MEMORY, 1, None)

    def test_time(self):
        """
        Check that runtime can be limited.
        """
        self.run_subprocess_test(ProcessResource.RUNTIME, -14, TimeoutExpired)


if __name__ == '__main__':
    unittest.main()
