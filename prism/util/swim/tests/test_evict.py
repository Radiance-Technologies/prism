"""
Test suite for the global switch manager.
"""

# disabling test for now--
# very hard to check that it's working without opening
# pstree and examining the concurrent builds.


import unittest
from prism.util.swim.auto import AutoSwitchManager
from prism.util.opam.formula import PackageFormula
from prism.util.opam import OpamAPI, OpamSwitch
import tempfile
from seutil import bash
from multiprocessing import Process
import time
import os


class TestEvict(unittest.TestCase):

    def __init__(self, *args):
        super().__init__(*args)
        self.root = tempfile.TemporaryDirectory()
        # can we do this yet with opam api or does the root need to be set up?
        bash.run(f"OPAMROOT={self.root.name} opam init --bare -y")
        # current defaults install things in the switch, which takes forever.
        # we will do this part manually.
        #self.sw = OpamAPI.create_switch("test","4.07.1",opam_root=self.root.name)
        bash.run(f"OPAMROOT={self.root.name} opam switch create test --empty")
        # give our shared manager the root+switch to play with
        self.manager = AutoSwitchManager([self.root.name], max_pool_size=1)

    def test_eviction(self):
        sw = self.manager.get_switch(PackageFormula.parse("\"conf-python-3-7\""))
        self.assertTrue("conf-python-3-7" in sw.run("opam list").stdout)
        self.manager.release_switch(sw) 
        sw = self.manager.get_switch(PackageFormula.parse("\"conf-python-3\""))
        self.assertTrue("conf-python-3" in sw.run("opam list").stdout)
        self.manager.release_switch(sw)

        # one original empty switch + 1 pool switch
        # won't remove original, uncloned switch because then
        # opam won't switch to clones using the parent's name...
        self.assertEqual(len(self.manager.switches),2)
        
if __name__ == '__main__':
    unittest.main()
