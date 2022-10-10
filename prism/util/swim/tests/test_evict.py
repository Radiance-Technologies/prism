"""
Test suite for automatic eviction in `SwitchManager`s.
"""

import shutil
import tempfile
import unittest

from prism.util.opam import OpamAPI
from prism.util.opam.formula import PackageFormula
from prism.util.swim.auto import AutoSwitchManager


class TestEvict(unittest.TestCase):
    """
    Unit tests for switch eviction.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Create a temporary OPAM root with empty (for speed) switch.
        """
        cls.root = tempfile.TemporaryDirectory()
        OpamAPI.init_root(cls.root.name)
        OpamAPI.create_switch("test", None, opam_root=cls.root.name)
        # give our shared manager the root+switch to play with
        cls.manager = AutoSwitchManager([cls.root.name], max_pool_size=1)

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Delete the temporary OPAM root.
        """
        shutil.rmtree(cls.root.name)

    def test_eviction(self):
        """
        Verify that the manager's pool size does not exceed its limit.
        """
        sw = self.manager.get_switch(
            PackageFormula.parse("\"conf-python-3-7\""))
        self.assertTrue("conf-python-3-7" in sw.run("opam list").stdout)
        self.manager.release_switch(sw)
        sw = self.manager.get_switch(PackageFormula.parse("\"conf-python-3\""))
        self.assertTrue("conf-python-3" in sw.run("opam list").stdout)
        self.manager.release_switch(sw)

        # one original empty switch + 1 pool switch
        # won't remove original, uncloned switch because then
        # opam won't switch to clones using the parent's name...
        self.assertEqual(len(self.manager.switches), 2)


if __name__ == '__main__':
    unittest.main()
