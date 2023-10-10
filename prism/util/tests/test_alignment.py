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
import random
import unittest

from prism.util.alignment import fast_edit_distance, lazy_align


class TestAlignment(unittest.TestCase):
    """
    Test suite for alignment algorithms and utilities.
    """

    def test_lazy_align(self):
        """
        Test the core parametric alignment algorithm.

        Defines the standard edit distance in terms of the core
        algorithm and asserts various properties of it for random
        inputs.
        """
        alpha = [chr(x) for x in range(ord('A'), ord('z') + 1)]

        # define edit distance using the alignment factory.
        def edit_distance(x, y):
            return lazy_align(
                x,
                y,
                lambda x,
                y: x != y,
                lambda _: 1,
                return_cost=True)

        for _ in range(25):
            a = random.choices(alpha, k=1000)
            cost = random.randint(1, 10)
            b = a.copy()
            for _ in range(cost):
                # pick a random index
                index = random.randint(0, len(b) - 1)
                # and mutate that spot.
                if (random.random() > 0.5):
                    # delete the char
                    del b[index]
                else:
                    # change the char
                    b[index] = 'a' if b[index] == 'z' else 'z'
            cost_measured, alignment = edit_distance("".join(a), "".join(b))
            # ensure that the alignment is the same
            # even in the accelerated version of the algorithm
            self.assertEqual(
                (cost_measured,
                 alignment),
                fast_edit_distance(
                    "".join(a),
                    "".join(b),
                    return_alignment=True))

            # assert that the found alignment
            # is no worse than the mutations we caused.
            self.assertGreaterEqual(cost, cost_measured)

            a_recons, b_recons = list(zip(*alignment))

            # assert that a and b can be reconstructed
            # from the alignment.
            self.assertEqual(list(filter(None, a_recons)), a)
            self.assertEqual(list(filter(None, b_recons)), b)

            # assert that the cost is equal to sum
            # of errors in the alignment.
            self.assertEqual(cost_measured, sum(x != y for x, y in alignment))


if __name__ == '__main__':
    unittest.main()
