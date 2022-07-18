"""
Test suite for prism.util.opam.
"""
import unittest

from prism.util.opam import OpamAPI, OpamSwitch
from prism.util.opam.switch import _allow_unsafe_clone


class TestOpamAPI(unittest.TestCase):
    """
    Test suite for `OpamAPI`.
    """

    test_switch_name = "test_switch"
    ocaml_version = "4.07.1"
    clone = None

    def test_clone_switch(self):
        """
        Verify that switches can be cloned and used.
        """
        _allow_unsafe_clone.append(True)
        clone = OpamAPI.clone_switch(
            self.test_switch_name,
            "test_cloned_switch")
        with self.subTest("install"):
            self.assertIsNone(clone.get_installed_version("coq-shell"))
            clone.install("coq-shell", version='1', yes=True)
            version = clone.get_installed_version("coq-shell")
            self.assertEqual(version, "1")
            version = clone.get_installed_version("ocaml")
            self.assertEqual(version, self.ocaml_version)
        with self.subTest("sandbox-install-forward"):
            # verify that the original switch is isolated from the clone
            self.assertIsNone(
                self.test_switch.get_installed_version("coq-shell"))
            self.test_switch.install("coq-shell", version='1', yes=True)
            version = self.test_switch.get_installed_version("coq-shell")
            self.assertEqual(version, "1")
        with self.subTest("sandbox-install-backward"):
            # verify that the clone is isolated from the original switch
            self.test_switch.install("conf-dpkg", version='1', yes=True)
            self.assertIsNone(clone.get_installed_version("conf-dpkg"))
            clone.install("conf-dpkg", version='1', yes=True)
            version = clone.get_installed_version("conf-dpkg")
            self.assertEqual(version, "1")
        with self.subTest("remove"):
            clone.remove_pkg("coq-shell")
            self.assertIsNone(clone.get_installed_version("coq-shell"))
            self.test_switch.remove_pkg("conf-dpkg")
            self.assertIsNone(
                self.test_switch.get_installed_version("conf-dpkg"))
        with self.subTest("sandbox-remove"):
            self.assertIsNotNone(clone.get_installed_version("conf-dpkg"))
            self.assertIsNotNone(
                self.test_switch.get_installed_version("coq-shell"))
        with self.subTest("sandbox-repo-forward"):
            # verify that the original switch is isolated from the clone
            clone.add_repo("coq-released", "https://coq.inria.fr/opam/released")
            r = self.test_switch.run("opam repo list")
            r.check_returncode()
            returned = r.stdout
            self.assertFalse(
                "coq-released "
                "https://coq.inria.fr/opam/released" in returned)
            clone.remove_repo("coq-released")
        with self.subTest("sandbox-repo-backward"):
            # verify that the clone is isolated from the original switch
            self.test_switch.add_repo(
                "coq-released",
                "https://coq.inria.fr/opam/released")
            r = clone.run("opam repo list")
            r.check_returncode()
            returned = r.stdout
            self.assertFalse(
                "coq-released "
                "https://coq.inria.fr/opam/released" in returned)
            self.test_switch.remove_repo("coq-released")
        _allow_unsafe_clone.pop()

    def test_create_switch(self):
        """
        Verify that switches can be created and not overwritten.
        """
        with self.assertWarns(UserWarning):
            test_switch = OpamAPI.create_switch(
                self.test_switch_name,
                self.ocaml_version)
        self.assertEqual(test_switch, self.test_switch)

    def test_set_switch(self):
        """
        Verify that a switch may be temporarily set.
        """
        previous_switch = OpamAPI.show_switch()
        with OpamAPI.switch(self.test_switch_name):
            current_switch = OpamAPI.show_switch()
            self.assertIn("OPAM_SWITCH_PREFIX", OpamAPI.active_switch.env)
            self.assertEqual(current_switch, self.test_switch_name)
            self.assertNotEqual(current_switch, previous_switch)
        self.assertEqual(OpamAPI.show_switch(), previous_switch)

    @classmethod
    def setUpClass(cls):
        """
        Set up a test switch.

        Doubles as part of test for switch creation.
        """
        cls.test_switch = OpamAPI.create_switch(
            cls.test_switch_name,
            cls.ocaml_version)
        cls.assertEqual(
            TestOpamAPI(),
            cls.test_switch,
            OpamSwitch(cls.test_switch_name,
                       None))

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Remove the test switch.

        Doubles as test for switch removal.
        """
        OpamAPI.remove_switch(cls.test_switch)
        with cls.assertRaises(TestOpamAPI(), ValueError):
            OpamAPI.remove_switch(cls.test_switch)
        with cls.assertRaises(TestOpamAPI(), ValueError):
            OpamAPI.remove_switch(cls.test_switch_name)
        OpamAPI.remove_switch("test_cloned_switch")


if __name__ == '__main__':
    unittest.main()
