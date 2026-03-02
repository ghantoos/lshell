"""Functional tests for lshell configuration"""

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

    def do_exit(self, child):
        """Exit the shell"""
        child.sendline("exit")
        child.expect(pexpect.EOF)

    def assert_startup_failure(self, command, expected_fragment):
        """Assert lshell exits during startup with a schema validation error."""
        child = pexpect.spawn(command)
        child.expect(pexpect.EOF)
        output = child.before.decode("utf-8", errors="ignore")
        self.assertIn(expected_fragment, output)

    def test_55_allowed_all_minus_list(self):
        """F55 | allow all commands minus the list"""

        command = "echo 1"
        expected = "lshell: unknown syntax: echo 1"

        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} " '--allowed \'"all" - ["echo"]'
        )
        child.expect(PROMPT)

        child.sendline(command)
        child.expect(PROMPT)
        output = child.before.decode("utf-8").split("\n")[1].strip()
        self.assertEqual(expected, output)
        self.do_exit(child)

    def test_56_path_minus_specific_path(self):
        """F56 | allow paths except for the specified path"""

        command1 = "cd /usr/"
        expected1 = f"{USER}:/usr\\$"
        command2 = "cd /usr/local"
        expected2 = 'lshell: forbidden path: "/usr/local/"'

        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} "
            '--path \'["/var", "/usr"] - ["/usr/local"]\''
        )
        child.expect(PROMPT)

        child.sendline(command1)
        child.expect(expected1)
        child.sendline(command2)
        child.expect(expected1)
        output = child.before.decode("utf-8").split("\n")[1].strip()
        self.assertEqual(expected2, output)
        self.do_exit(child)

    def test_57_overssh_all_minus_list(self):
        """F57 | overssh minus command list"""
        command = "echo 1"
        expected = (
            'lshell: forbidden char/command over SSH: "echo 1"\r\n'
            "This incident has been reported."
        )

        # add SSH_CLIENT to environment
        if not os.environ.get("SSH_CLIENT"):
            os.environ["SSH_CLIENT"] = "random"

        child = pexpect.spawn(
            f"{LSHELL} "
            f"--config {CONFIG} "
            f"--overssh \"['ls','echo'] - ['echo']\" "
            f"-c '{command}'"
        )
        child.expect(pexpect.EOF)

        output = child.before.decode("utf-8").strip()
        self.assertEqual(expected, output)
        self.do_exit(child)

    def test_58_allowed_plus_minus_list(self):
        """F58 | allow plus list minus list"""
        command = "echo 1"
        expected = "lshell: unknown syntax: echo 1"

        child = pexpect.spawn(
            f"{LSHELL} "
            f"--config {CONFIG} "
            f"--allowed \"['ls'] + ['echo'] - ['echo']\" "
        )
        child.expect(PROMPT)

        child.sendline(command)
        child.expect(PROMPT)
        output = child.before.decode("utf-8").split("\n")[1].strip()
        self.assertEqual(expected, output)
        self.do_exit(child)

    def test_59a_forbidden_remove_one(self):
        """F59a | remove all items from forbidden list"""

        command = "echo 1 ; echo 2"
        expected = [" echo 1 ; echo 2\r", "1\r", "2\r", ""]

        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} " '--forbidden \'[";"] - [";"]\''
        )
        child.expect(PROMPT)

        child.sendline(command)
        child.expect(PROMPT)
        output = child.before.decode("utf-8").split("\n")
        self.assertEqual(expected, output)
        self.do_exit(child)

    def test_59b_forbidden_remove_one(self):
        """F59b | fixed forbidden list"""

        command = "echo 1 ; echo 2"
        expected = 'lshell: forbidden character: ";"'

        child = pexpect.spawn(f"{LSHELL} --config {CONFIG} " "--forbidden '[\";\"]'")
        child.expect(PROMPT)

        child.sendline(command)
        child.expect(PROMPT)
        output = child.before.decode("utf-8").split("\n")[1].strip()
        self.assertEqual(expected, output)
        self.do_exit(child)

    def test_59c_forbidden_remove_one(self):
        """F59c | remove an item from forbidden list"""

        command = "echo 1 ; echo 2"
        expected = [" echo 1 ; echo 2\r", "1\r", "2\r", ""]

        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} " '--forbidden \'[";", "|", "%"] - [";"]\''
        )
        child.expect(PROMPT)

        child.sendline(command)
        child.expect(PROMPT)
        output = child.before.decode("utf-8").split("\n")
        self.assertEqual(expected, output)
        self.do_exit(child)

    def test_60_schema_accepts_valid_allowed_list(self):
        """F60 | valid list-based override should start shell and allow command."""
        child = pexpect.spawn(
            f'{LSHELL} --config {CONFIG} --allowed "[\'echo\']" --forbidden "[]"'
        )
        child.expect(PROMPT)
        child.sendline("echo OK")
        child.expect(PROMPT)
        output = child.before.decode("utf-8")
        self.assertIn("OK", output)
        self.do_exit(child)

    def test_61_schema_rejects_non_list_allowed(self):
        """F61 | scalar value for allowed must fail schema validation."""
        self.assert_startup_failure(
            f"{LSHELL} --config {CONFIG} --allowed 1",
            "lshell: config: 'allowed' must be a list",
        )

    def test_62_schema_rejects_non_string_allowed_entries(self):
        """F62 | allowed list entries must be strings."""
        self.assert_startup_failure(
            f"{LSHELL} --config {CONFIG} --allowed \"['echo', 1]\"",
            "lshell: config: 'allowed' list entries must be strings",
        )

    def test_63_schema_rejects_non_dict_aliases(self):
        """F63 | aliases must be a dictionary."""
        self.assert_startup_failure(
            f"{LSHELL} --config {CONFIG} --aliases \"['ll']\"",
            "lshell: config: 'aliases' must be a dictionary",
        )
