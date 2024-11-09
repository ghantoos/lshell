""" Utils for the test suite. """

import os


def is_alpine_linux():
    """Check if the system is running Alpine Linux."""
    if os.path.exists("/etc/os-release"):
        with open("/etc/os-release") as f:
            return any("ID=alpine" in line for line in f)
    return False
