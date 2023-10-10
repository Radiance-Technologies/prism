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
Test suite for `prism.project.util`.
"""
import unittest

from prism.project.util import extract_name


class TestUtil(unittest.TestCase):
    """
    Test suite for common project utility functions.
    """

    def test_extract_name(self):
        """
        Verify project name extraction works for URLs and paths.
        """
        self.assertEqual(
            "CompCert",
            extract_name("https://github.com/AbsInt/CompCert"))
        # with extension
        self.assertEqual(
            "CompCert",
            extract_name("https://github.com/AbsInt/CompCert.git"))
        self.assertEqual("CompCert", extract_name("path/to/AbsInt/CompCert"))


if __name__ == '__main__':
    unittest.main()
