"""
Script to test timeouts.
"""
import sys
import time

start = time.time()


def _runtime():
    """
    Compute current runtime.
    """
    runtime = time.time() - start
    return runtime


if __name__ == "__main__":
    amt = int(sys.argv[1])
    while _runtime() < amt:
        continue
