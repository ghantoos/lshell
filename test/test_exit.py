"""Functional tests for lshell for exit command"""

import os
import unittest
from getpass import getuser
import pexpect


TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"
LSHELL = f"{TOPDIR}/bin/lshell"
USER = getuser()
PROMPT = f"{USER}:~\\$"


class TestFunctions(unittest.TestCase):
    """Functional tests for lshell"""

    def setUp(self):
        """spawn lshell with pexpect and return the child"""
        self.child = pexpect.spawn(f"{LSHELL} --config {CONFIG} --strict 1")
        self.child.expect(PROMPT)

    def tearDown(self):
        self.child.close()

    def do_exit(self, child):
        """Exit the shell"""
        child.sendline("exit")
        child.expect(pexpect.EOF)

    def test_30_disable_exit(self):
        """F31 | test disabled exit command"""
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG} " "--disable_exit 1 ")
        child.expect(PROMPT)

        expected = ""
        child.sendline("exit")
        child.expect(PROMPT)

        result = child.before.decode("utf8").split("\n")[1]

        self.assertIn(expected, result)

    def test_50_warnings_then_kickout(self):
        """F50 | kicked out after warning counter"""
        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} --strict 1 --warning_counter 0"
        )
        child.sendline("lslsls")
        child.sendline("lslsls")
        child.expect(pexpect.EOF, timeout=10)

        # Assert that the process exited
        self.assertIsNotNone(
            child.exitstatus, "The lshell process did not exit as expected."
        )

        # Optionally, you can assert that the exit code is correct
        self.assertEqual(child.exitstatus, 1, "The process should exit with code 1.")
        self.do_exit(child)
