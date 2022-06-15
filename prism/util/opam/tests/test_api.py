"""
Test suite for prism.util.opam.
"""
import re
import unittest
from pathlib import Path
from subprocess import CalledProcessError
from typing import Dict

from seutil import bash

from prism.util.opam import OCamlVersion, OpamAPI, Version, VersionConstraint

TEST_DIR = Path(__file__).parent


class TestOpamAPI(unittest.TestCase):
    """
    Test suite for `OpamAPI`.
    """

    test_switch = "test_switch"
    ocaml_version = "4.07.1"

    def test_create_switch(self):
        """
        Verify that switches can be created and not overwritten.
        """
        with self.assertWarns(UserWarning):
            OpamAPI.create_switch(self.test_switch, self.ocaml_version)

    def test_get_available_versions(self):
        """
        Test retrieval of available versions for a single package.

        Indirectly test by comparing a pretty-printed version of the
        retrieved versions with the command-line output.
        """
        pkg = 'ocaml'
        r = bash.run(f"opam show -f all-versions {pkg}")
        r.check_returncode()
        expected = re.sub(r"\s+", " ", r.stdout).strip()
        actual = OpamAPI.get_available_versions(pkg)
        self.assertIsInstance(actual[0], Version)
        self.assertEqual(" ".join(str(v) for v in actual), expected)

    def test_get_dependencies(self):
        """
        Test retrieval of dependencies for a single package.
        """
        actual = OpamAPI.get_dependencies("coq", "8.10.2")
        expected: Dict[str, VersionConstraint]
        expected = {
            "ocaml":
                VersionConstraint(
                    OCamlVersion(4,
                                 '05',
                                 0),
                    OCamlVersion(4,
                                 10),
                    True,
                    False),
            "ocamlfind":
                VersionConstraint(),
            "num":
                VersionConstraint(),
            "conf-findutils":
                VersionConstraint()
        }
        self.assertEqual(actual, expected)

    def test_repo_add_remove(self):
        """
        Test the addition and removal of an opam repository.

        Test success by searching in output of `opam repo list`
        """
        repo_name = 'coq-released'
        repo_addr = 'https://coq.inria.fr/opam/released'

        r = bash.run(f"opam repo list")
        r.check_returncode()
        returned = r.stdout
        self.assertFalse("coq-released " \
                         "https://coq.inria.fr/opam/released" in returned)

        OpamAPI.add_repo(repo_name, repo_addr)

        r = bash.run(f"opam repo list")
        r.check_returncode()
        returned = r.stdout
        self.assertTrue("coq-released " \
                        "https://coq.inria.fr/opam/released" in returned)

        OpamAPI.remove_repo(repo_name)

        r = bash.run(f"opam repo list")
        r.check_returncode()
        returned = r.stdout
        self.assertFalse("coq-released " \
                         "https://coq.inria.fr/opam/released" in returned)

    def test_set_switch(self):
        """
        Verify that a switch may be temporarily set.
        """
        previous_switch = OpamAPI.show_switch()
        with OpamAPI.switch(self.test_switch):
            current_switch = OpamAPI.show_switch()
            self.assertIn("OPAM_SWITCH_PREFIX", OpamAPI.opam_env)
            self.assertEqual(current_switch, self.test_switch)
            self.assertNotEqual(current_switch, previous_switch)
        self.assertEqual(OpamAPI.show_switch(), previous_switch)

    @classmethod
    def setUpClass(cls):
        """
        Set up a test switch.
        """
        OpamAPI.create_switch(cls.test_switch, cls.ocaml_version)

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Remove the test switch.
        """
        OpamAPI.remove_switch(cls.test_switch)
        with cls.assertRaises(TestOpamAPI(), CalledProcessError):
            OpamAPI.remove_switch(cls.test_switch)


if __name__ == '__main__':
    unittest.main()
