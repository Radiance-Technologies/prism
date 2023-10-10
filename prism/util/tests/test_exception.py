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
Test suite for `prism.util.exception`.
"""
import gc
import unittest
import weakref

from prism.util.exception import Except


class TestExcept(unittest.TestCase):
    """
    Test suite for Excepts.
    """

    def test_delete_traceback(self):
        """
        Check that Except disposes of tracebacks.
        """

        class test:
            pass

        obj = test()
        ref = weakref.ref(obj)

        def f(x):
            try:
                raise Exception()
            except Exception as e:
                return Except(0, e, "")

        e = f(obj)
        del obj

        gc.collect()

        self.assertEqual(ref(), None)
        self.assertEqual(e.exception.__traceback__, None)


if __name__ == '__main__':
    unittest.main()
