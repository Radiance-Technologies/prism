"""
Test suite for prism.util.opam.
"""
import unittest
from pathlib import Path
from subprocess import CalledProcessError

from prism.util.opam import OpamAPI, OpamSwitch

TEST_DIR = Path(__file__).parent


class TestOpamAPI(unittest.TestCase):
    """
    Test suite for `OpamAPI`.
    """

    test_switch_name = "test_switch"
    ocaml_version = "4.07.1"

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
        with cls.assertRaises(TestOpamAPI(), CalledProcessError):
            OpamAPI.remove_switch(cls.test_switch)
        with cls.assertRaises(TestOpamAPI(), CalledProcessError):
            OpamAPI.remove_switch(cls.test_switch_name)


if __name__ == '__main__':
    unittest.main()
