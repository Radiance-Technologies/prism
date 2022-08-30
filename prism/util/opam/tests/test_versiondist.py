"""
Test suite for prism.util.opam.
"""
import multiprocessing as mp
import unittest
from datetime import datetime

from prism.util.opam import OpamVersion
from prism.util.opam.versiondist import VersionDistribution


class TestVersion(unittest.TestCase):
    """
    Test suite for `VersionDistribution`.
    """

    def test_basic(self):
        """
        Test simple execution doesn't break.

        Downloads repo behind the scenes.
        """
        VersionDistribution.search("coq")

    def test_threaded(self):
        """
        Test that execution works in threads.

        Since we are managing one repo between many threads, this is
        prone to breakage unless locks handled correctly.
        """
        packages = [
            "coq",
            "coqide",
            "coq-mathcomp-finmap",
            "coq-mathcomp-ssreflect"
        ]
        # git will throw here if locks are mishandled.
        with mp.Pool(4) as p:
            p.map(VersionDistribution.search, packages)

    def test_history(self):
        """
        Test that the content of searches make sense.
        """
        new = VersionDistribution.search("coq", date=datetime(2022, 1, 1))
        old = VersionDistribution.search("coq", date=datetime(2018, 1, 1))

        # coq 8.10.2 came out nov 29th, 2019.
        # people could specify compatibility before it came out
        # by writing a constraint like ">= 8.10", though.

        # so as a sanity check we'll just show the majority changes.
        v = OpamVersion.parse("8.10.2")

        self.assertTrue(new[v] == max(new.values()))
        # "8.10.2" not in top 10 most common keys
        self.assertTrue(v not in list(zip(*old.most_common(10)))[0])


if __name__ == '__main__':
    unittest.main()
