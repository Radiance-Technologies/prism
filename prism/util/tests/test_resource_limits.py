#
# Copyright (c) 2023 Radiance Technologies, Inc.
#
# This file is part of PRISM
# (see https://github.com/orgs/Radiance-Technologies/prism).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program. If not, see
# <http://www.gnu.org/licenses/>.
#
"""
Test suite for alignment algorithms and utilities.
"""
import logging
import resource
import unittest
import warnings
from resource import getrlimit
from subprocess import TimeoutExpired
from typing import Callable, Dict, Tuple

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

    tool: Dict[ProcessResource, Callable]
    key: Dict[ProcessResource, str]
    fudge_factor: Dict[ProcessResource, int]
    current_limits: Dict[ProcessResource, Tuple[int, int]]
    offset: Dict[ProcessResource, int]
    limit: Dict[ProcessResource, int]
    under_limit: Dict[ProcessResource, int]
    over_limit: Dict[ProcessResource, int]

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
        cls.fudge_factor = {
            ProcessResource.MEMORY: int(100e6),  # 100 MB
            ProcessResource.RUNTIME: 1,  # 2 seconds
        }

        cls.current_limits = {}
        cls.offset = {}
        cls.limit = {}
        cls.under_limit = {}
        cls.over_limit = {}
        for rss, tool in cls.tool.items():
            fudge_factor = cls.fudge_factor[rss]
            output, usage = tool(0)
            logger.info("STDOUT: %s", output.stdout)
            logger.info("STDERR: %s", output.stderr)
            logger.info("RETURNCODE: %s", output.returncode)
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
            exception: bool):
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
                if exception:
                    with self.assertRaises(TimeoutExpired):
                        TOOL(subtest_limit, preexec_fn=limiter)
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
        self.run_subprocess_test(ProcessResource.MEMORY, 1, False)

    def test_time(self):
        """
        Check that runtime can be limited.
        """
        self.run_subprocess_test(ProcessResource.RUNTIME, -14, True)


if __name__ == '__main__':
    unittest.main()
