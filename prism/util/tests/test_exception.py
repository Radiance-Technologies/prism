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
