"""Test package bootstrap.

This package intentionally does not maintain a hand-written module list.
Use discovery-based runners (pytest or unittest discovery) to collect tests.
"""

import os
import unittest


def run_discovery():
    """Run unittest discovery from the test package directory."""
    start_dir = os.path.dirname(os.path.realpath(__file__))
    suite = unittest.defaultTestLoader.discover(start_dir=start_dir, pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    return 0 if runner.run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(run_discovery())
