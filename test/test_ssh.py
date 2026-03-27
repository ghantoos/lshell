"""Functional tests for lshell SSH handling"""

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

    def test_45_overssh_allowed_command_exit_0(self):
        """F44 | Test 'ssh -c ls' command should exit 0"""
        # add SSH_CLIENT to environment
        if not os.environ.get("SSH_CLIENT"):
            os.environ["SSH_CLIENT"] = "random"

        self.child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " f"--overssh \"['ls']\" " f"-c 'ls'"
        )
        self.child.expect(pexpect.EOF, timeout=10)
        self.child.close()

        # Assert that the process exited
        self.assertIsNotNone(
            self.child.exitstatus,
            f"The lshell process did not exit as expected: {self.child.exitstatus}",
        )

        # Optionally, you can assert that the exit code is correct
        self.assertEqual(
            self.child.exitstatus,
            0,
            f"The process should exit with code 0, got {self.child.exitstatus}.",
        )

    def test_46_overssh_allowed_command_exit_1(self):
        """F44 | Test 'ssh -c ls' command should exit 1"""
        # add SSH_CLIENT to environment
        if not os.environ.get("SSH_CLIENT"):
            os.environ["SSH_CLIENT"] = "random"

        self.child = pexpect.spawn(
            f"{LSHELL} "
            f"--config {CONFIG} "
            f"--overssh \"['ls']\" "
            f"-c 'ls /random'"
        )
        self.child.expect(pexpect.EOF, timeout=10)
        self.child.close()

        # Assert that the process exited
        self.assertIsNotNone(
            self.child.exitstatus, "The lshell process did not exit as expected."
        )

        # Optionally, you can assert that the exit code is correct
        self.assertEqual(
            self.child.exitstatus,
            1,
            f"The process should exit with code 1, got {self.child.exitstatus}.",
        )

    def test_46_overssh_not_allowed_command_exit_1(self):
        """F44 | Test 'ssh -c lss' command should succeed"""
        # add SSH_CLIENT to environment
        if not os.environ.get("SSH_CLIENT"):
            os.environ["SSH_CLIENT"] = "random"

        self.child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " f"--overssh \"['ls']\" " f"-c 'lss'"
        )
        self.child.expect(pexpect.EOF, timeout=10)
        self.child.close()

        # Assert that the process exited
        self.assertIsNotNone(
            self.child.exitstatus, "The lshell process did not exit as expected."
        )

        # Optionally, you can assert that the exit code is correct
        self.assertEqual(
            self.child.exitstatus,
            1,
            f"The process should exit with code 1, got {self.child.exitstatus}.",
        )

    def test_57_overssh_all_minus_list(self):
        """F57 | overssh minus command list."""
        command = "echo 1"
        expected = (
            'lshell: forbidden char/command over SSH: "echo 1"\r\n'
            "This incident has been reported."
        )

        if not os.environ.get("SSH_CLIENT"):
            os.environ["SSH_CLIENT"] = "random"

        self.child = pexpect.spawn(
            f"{LSHELL} "
            f"--config {CONFIG} "
            f"--overssh \"['ls','echo'] - ['echo']\" "
            f"-c '{command}'"
        )
        self.child.expect(pexpect.EOF)

        output = self.child.before.decode("utf-8").strip()
        self.assertEqual(expected, output)

    def test_58_overssh_plus_minus_chain_controls_warning_and_allow(self):
        """F58 | overssh +/- chain should deny removed command and allow added one."""
        if not os.environ.get("SSH_CLIENT"):
            os.environ["SSH_CLIENT"] = "random"

        denied = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} "
            "--overssh \"['ls'] + ['echo'] - ['ls']\" "
            "-c 'ls'"
        )
        denied.expect(pexpect.EOF)
        denied_output = denied.before.decode("utf-8").strip()
        self.assertIn('lshell: forbidden char/command over SSH: "ls"', denied_output)
        self.assertIn("This incident has been reported.", denied_output)

        allowed = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} "
            "--overssh \"['ls'] + ['echo'] - ['ls']\" "
            "-c 'echo 1'"
        )
        allowed.expect(pexpect.EOF, timeout=10)
        allowed_output = allowed.before.decode("utf-8")
        self.assertIn("1", allowed_output)
