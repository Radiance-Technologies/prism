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
Module for tool to help run commands get resource usage.
"""
import re
from subprocess import CompletedProcess
from typing import Dict, Optional, Tuple, Union

from seutil import bash

from prism.tests import _MEMORY_SCRIPT_PATH, _TIMEOUT_SCRIPT_PATH


class ResourceTestTool:
    """
    Helper tool to run bash commands to test resource usage.
    """

    COMMAND_MEMORY: str = f"python {_MEMORY_SCRIPT_PATH}"
    """
    Script that allocates byte array. First argument is
    size of the array.
    """

    COMMAND_RUNTIME: str = f"python {_TIMEOUT_SCRIPT_PATH}"
    """
    Script that sleeps and sends signal.SIGXCPU if runtime
    limit is expired.
    """

    PREFIX: str = (
        "/usr/bin/time -f"
        "'Elapsed time: %es\\n"
        "Memory usage: %M KB\\n"
        "CPU usage: %P'")
    """
    A shell command that returns memory, runtime,
    and cpu usage information of commands that follow
    it. Should be prepended and executed with a command.
    """

    RE_MEMORY_USAGE: str = r'Memory usage: (?P<memory>\d+(?:\.\d+)?)'
    """
    REGEX pattern to extract memory from output of `PREFIX`.
    """

    RE_RUNTIME_USAGE: str = r'Elapsed time: (?P<runtime>\d+(?:\.\d+)?)'
    """
    REGEX pattern to extract runtime from output of `PREFIX`.
    """

    MEMORY_KEY: str = "MEMORY"
    """
    Key used get memory usage from parsed output of `PREFIX` command.
    """

    RUNTIME_KEY: str = "RUNTIME"
    """
    Key used get runtime from parsed output of `PREFIX` command.
    """

    @classmethod
    def _make_command(cls, cmd: str, amt: int) -> str:
        """
        Create resource testing command.

        Parameters
        ----------
        cmd : str
            Bash command that will be monitored
            for resource usage.
        amt : int
            Argument to resource testing script.

        Returns
        -------
        str
            Command that runs and returns resource
            usage to STDERR.
        """
        return f"{cls.PREFIX} {cmd} {amt}"

    @classmethod
    def _command_memory(cls, amt: int) -> str:
        """
        Return command to allocate bytearray with `amt` bytes.

        This will consume more memory for larger values.

        Parameters
        ----------
        amt : int
            Number of bytes to allocate in command.
            This does not equal to memory usage running the command.

        Returns
        -------
        str
            Command to allocate `amt` bytes of memory within a
            process.
        """
        return cls._make_command(cls.COMMAND_MEMORY, amt)

    @classmethod
    def _command_runtime(cls, amt: int) -> str:
        """
        Run sleep command for `amt` seconds.

        Parameters
        ----------
        amt : int
            Number of seconds to sleep.

        Returns
        -------
        str
            Command to sleep in process for `amt`
            seconds.
        """
        return cls._make_command(cls.COMMAND_RUNTIME, amt)

    @classmethod
    def _parse_resource_usage(cls,
                              text: str) -> Dict[str,
                                                 Optional[Union[float,
                                                                int]]]:
        """
        Extract resource used values from text.

        Parameters
        ----------
        text : str
            The standard error output of a
            ``subprocess.CompletedProcess`` run with
            `cls.PREFIX`.


        Returns
        -------
        Dict[str, Optional[Union[float, int]]]
            Mapping of resource usage to resource names
            extracted from `text`. If a value is None,
            then the resource amount was not found in
            the text.
        """
        usage = {}
        match = re.search(cls.RE_RUNTIME_USAGE, text)
        if match is not None:
            usage[cls.RUNTIME_KEY] = float(match['runtime'])
        match = re.search(cls.RE_MEMORY_USAGE, text)
        if match is not None:
            usage[cls.MEMORY_KEY] = int(match['memory']) * 1000
        return usage

    @classmethod
    def run_cmd(
        cls,
        cmd: str,
        **kwargs,
    ) -> Tuple[CompletedProcess,
               Dict[str,
                    int]]:
        """
        Run `cmd` and parse resource usage from output.

        Parameters
        ----------
        cmd : str
            A bash command.

        Returns
        -------
        CompletedProcess
            The completed process object returned by
            subprocess.
        Dict[str, Optional[int]]
            The resource usage from running the command.
        """
        output = bash.run(cmd, **kwargs)
        usage = cls._parse_resource_usage(output.stderr)
        return output, usage

    @classmethod
    def run_memory_cmd(
        cls,
        amt: int,
        **kwargs,
    ) -> Tuple[CompletedProcess,
               Dict[str,
                    Optional[int]]]:
        """
        Run command to allocate bytearray with `amt` bytes.

        Parameters
        ----------
        amt : int
            Number of bytes to allocate in command.
            This does not equal to memory usage running the command.

        Returns
        -------
        CompletedProcess
            The completed process object returned by
            subprocess.
        Dict[str, Optional[int]]
            The resource usage from running the command.
        """
        return cls.run_cmd(cls._command_memory(amt), **kwargs)

    @classmethod
    def run_runtime_cmd(
        cls,
        amt: int,
        **kwargs,
    ) -> Tuple[CompletedProcess,
               Dict[str,
                    Optional[int]]]:
        """
        Run sleep command for `amt` seconds.

        Parameters
        ----------
        amt : int
            Number of seconds to sleep.

        Returns
        -------
        CompletedProcess
            The completed process object returned by
            subprocess.
        Dict[str, Optional[int]]
            The resource usage from running the command.
        """
        return cls.run_cmd(cls._command_runtime(amt), **kwargs)
