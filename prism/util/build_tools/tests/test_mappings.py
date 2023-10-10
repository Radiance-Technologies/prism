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
Test suite for prism.util.opam.
"""
import unittest

from prism.util.build_tools.mappings import LogicalMappings as LM


class TestLogicalMappings(unittest.TestCase):
    """
    Test suite for `LogicalMappings`.
    """

    def test_concrete(self):
        """
        Test common/expected searches on LogicalMappings.
        """
        self.assertEqual(
            LM.opam.search(prefix="mathcomp",
                           suffix="matrix"),
            {"coq-mathcomp-algebra"})
        self.assertGreater(len(LM.opam.search(suffix="matrix")), 1)  # ambiguous
        self.assertEqual(
            LM.opam.search(suffix="stdpp.namespaces"),
            {"coq-stdpp"})


if __name__ == '__main__':
    unittest.main()
