"""
Test suite for prism.util.opam.
"""
import multiprocessing as mp
import unittest
from datetime import datetime
from pathlib import Path

import prism.util.opam.versiondist as versiondist
from prism.util.opam import OpamVersion
from prism.util.opam.versiondist import VersionDistribution


class TestVersionDist(unittest.TestCase):
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

    def test_explicit_versions(self):
        """
        Check that we can find versions specified as "package.version".
        """
        # force a checkout of recent date for test
        VersionDistribution.search("coq", date=datetime(2022, 9, 10))

        p = Path(
            versiondist.REPO_DIRECTORY.name
        ) / "released/packages/coq-ltac2/coq-ltac2.999999"

        p.mkdir()

        # depending on the order the tests are run in,
        # this can show up in other test, which isn't great
        # but shouldn't negatively affect them
        (p / "opam").write_text(
            """
opam-version: "2.0"
name: "coq-ltac2"
maintainer: "Pierre-Marie Pédrot <pierre-marie.pedrot@irif.fr>"
license: "LGPL 2.1"
homepage: "https://github.com/coq/ltac2"
dev-repo: "git+https://github.com/coq/ltac2.git"
bug-reports: "https://github.com/coq/ltac2/issues"
build: [
  [make "COQBIN=\"\"" "-j%{jobs}%"]
]
install: [make "install"]
depends: [
  "ocaml"
  "coq.not.a.real.version"
]
synopsis: "A tactic language for Coq"
authors: "Pierre-Marie Pédrot <pierre-marie.pedrot@irif.fr>"
url {
  src: "https://github.com/coq/ltac2/archive/0.3.tar.gz"
  checksum: "sha256=e759198cd7bf1145f822bc7dfad7f47a4c682b28bdd67376026276ae88d55feb"
}
        """)

        # have to use unique date so caching doesn't ruin the test.
        search = VersionDistribution.search("coq", date=datetime(2022, 9, 17))
        self.assertTrue(OpamVersion.parse("not.a.real.version") in search)


if __name__ == '__main__':
    unittest.main()
