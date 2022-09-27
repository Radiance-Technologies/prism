"""
Synchronization helpers for multiprocessing.
"""


def critical(*args, lock_name="_lock"):
    """
    Wrap a method in a mutex lock/unlock.

    Guesses that the class's lock is called "_lock".

    If it isn't called that, can be invoked thusly:

    @critical(lock_name="actual_lock")
    """

    def inner(f):

        def g(self, *args, **kwargs):
            lock = getattr(self, lock_name)
            lock.acquire()
            ret = f(self, *args, **kwargs)
            lock.release()
            return ret

        return g

    if (len(args) > 0):
        return inner(args[0])

    # no args passed, must have been
    # keyword configuration.

    return inner
