"""Functional tests for lshell"""

import os
import unittest
import inspect
from getpass import getuser
import pexpect

TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"
LSHELL = f"{TOPDIR}/bin/lshell"


class TestFunctions(unittest.TestCase):
    """Functional tests for lshell"""

    user = getuser()

    def setUp(self):
        """spawn lshell with pexpect and return the child"""
        self.child = pexpect.spawn(f"{LSHELL} --config {CONFIG} --strict 1")
        self.child.expect(f"{self.user}:~\\$")

    def tearDown(self):
        self.child.close()

    def test_51_grep_valid_log_entry(self):
        """F51 | Test that grep matches a valid log entry format."""
        pattern = (
            r"\[\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}\s+(?:-|\+)\d{4}\].+UID=[\w.]+"
        )
        f_name = inspect.currentframe().f_code.co_name
        log_file = f"{TOPDIR}/test/testfiles/{f_name}.log"
        command = f"grep -P '{pattern}' {log_file}"

        self.child = pexpect.spawn(
            (
                f"{LSHELL} --config {CONFIG} "
                f'--allowed "+ [\'grep\']" --forbidden "[]"'
            )
        )
        self.child.expect(f"{self.user}:~\\$")

        self.child.sendline(command)
        self.child.expect(f"{self.user}:~\\$")
        output = self.child.before.decode("utf-8")
        self.assertIn("user123", output)

    def test_52_grep_invalid_date_format(self):
        """F52 | Test that grep matches a valid log entry format."""
        pattern = (
            r"\[\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}\s+(?:-|\+)\d{4}\].+UID=[\w.]+"
        )
        f_name = inspect.currentframe().f_code.co_name
        log_file = f"{TOPDIR}/test/testfiles/{f_name}.log"
        command = f"grep -P '{pattern}' {log_file}"

        self.child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} " '--allowed "+ [\'grep\']" --forbidden "[]"'
        )
        self.child.expect(f"{self.user}:~\\$")

        self.child.sendline(command)
        self.child.expect(f"{self.user}:~\\$")
        output = self.child.before.decode("utf-8")
        self.assertNotIn("user123", output)

    def test_53_grep_missing_uid(self):
        """F53 | Test that grep matches a valid log entry format."""
        pattern = (
            r"\[\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}\s+(?:-|\+)\d{4}\].+UID=[\w.]+"
        )
        f_name = inspect.currentframe().f_code.co_name
        log_file = f"{TOPDIR}/test/testfiles/{f_name}.log"
        command = f"grep -P '{pattern}' {log_file}"

        self.child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} " '--allowed "+ [\'grep\']" --forbidden "[]"'
        )
        self.child.expect(f"{self.user}:~\\$")

        self.child.sendline(command)
        self.child.expect(f"{self.user}:~\\$")
        output = self.child.before.decode("utf-8")
        self.assertNotIn("user123", output)

    def test_54_grep_special_characters_in_uid(self):
        """F54 | Test that grep matches a valid log entry format."""
        pattern = (
            r"\[\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}\s+(?:-|\+)\d{4}\].+UID=[\w.]+"
        )
        f_name = inspect.currentframe().f_code.co_name
        log_file = f"{TOPDIR}/test/testfiles/{f_name}.log"
        command = f"grep -P '{pattern}' {log_file}"

        self.child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} " '--allowed "+ [\'grep\']" --forbidden "[]"'
        )
        self.child.expect(f"{self.user}:~\\$")

        self.child.sendline(command)
        self.child.expect(f"{self.user}:~\\$")
        output = self.child.before.decode("utf-8")
        self.assertIn("user.name", output)

    def test_55_allowed_all_minus_list(self):
        """F55 | allow all commands minus the list"""

        command = "echo 1"
        expected = "*** forbidden command: echo"

        self.child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} " '--allowed \'"all" - ["echo"]'
        )
        self.child.expect(f"{self.user}:~\\$")

        self.child.sendline(command)
        self.child.expect(f"{self.user}:~\\$")
        output = self.child.before.decode("utf-8").split("\n")[1].strip()
        self.assertEqual(expected, output)

    def test_56_path_minus_specific_path(self):
        """F56 | allow paths except for the specified path"""

        command1 = "cd /usr/"
        expected1 = f"{self.user}:/usr\\$"
        command2 = "cd /usr/local"
        expected2 = "*** forbidden path: /usr/local/"

        self.child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} "
            '--path \'["/var", "/usr"] - ["/usr/local"]\''
        )
        self.child.expect(f"{self.user}:~\\$")

        self.child.sendline(command1)
        self.child.expect(expected1)
        self.child.sendline(command2)
        self.child.expect(expected1)
        output = self.child.before.decode("utf-8").split("\n")[1].strip()
        self.assertEqual(expected2, output)

    def test_57_overssh_all_minus_list(self):
        """F57 | overssh minus command list"""
        command = "echo 1"
        expected = (
            '*** forbidden char/command over SSH: "echo 1"\r\n'
            "This incident has been reported."
        )

        # add SSH_CLIENT to environment
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

    def test_58_allowed_plus_minus_list(self):
        """F58 | allow plus list minus list"""
        command = "echo 1"
        expected = "*** forbidden command: echo"

        self.child = pexpect.spawn(
            f"{LSHELL} "
            f"--config {CONFIG} "
            f"--allowed \"['ls'] + ['echo'] - ['echo']\" "
        )
        self.child.expect(f"{self.user}:~\\$")

        self.child.sendline(command)
        self.child.expect(f"{self.user}:~\\$")
        output = self.child.before.decode("utf-8").split("\n")[1].strip()
        self.assertEqual(expected, output)

    def test_59a_forbidden_remove_one(self):
        """F59a | remove all items from forbidden list"""

        command = "echo 1 ; echo 2"
        expected = [" echo 1 ; echo 2\r", "1\r", "2\r", ""]

        self.child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} " '--forbidden \'[";"] - [";"]\''
        )
        self.child.expect(f"{self.user}:~\\$")

        self.child.sendline(command)
        self.child.expect(f"{self.user}:~\\$")
        output = self.child.before.decode("utf-8").split("\n")
        self.assertEqual(expected, output)

    def test_59b_forbidden_remove_one(self):
        """F59b | fixed forbidden list"""

        command = "echo 1 ; echo 2"
        expected = "*** forbidden character: ;"

        self.child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} " "--forbidden '[\";\"]'"
        )
        self.child.expect(f"{self.user}:~\\$")

        self.child.sendline(command)
        self.child.expect(f"{self.user}:~\\$")
        output = self.child.before.decode("utf-8").split("\n")[1].strip()
        self.assertEqual(expected, output)

    def test_59c_forbidden_remove_one(self):
        """F59c | remove an item from forbidden list"""

        command = "echo 1 ; echo 2"
        expected = [" echo 1 ; echo 2\r", "1\r", "2\r", ""]

        self.child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} " '--forbidden \'[";", "|", "%"] - [";"]\''
        )
        self.child.expect(f"{self.user}:~\\$")

        self.child.sendline(command)
        self.child.expect(f"{self.user}:~\\$")
        output = self.child.before.decode("utf-8").split("\n")
        self.assertEqual(expected, output)

    def test_60_allowed_extension_success(self):
        """F60 | allow extension and cat file with similar extension"""

        f_name = inspect.currentframe().f_code.co_name
        log_file = f"{TOPDIR}/test/testfiles/{f_name}.log"
        command = f"cat {log_file}"
        expected = "Hello world!"

        self.child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} "
            "--allowed \"+ ['cat']\" "
            "--allowed_file_extensions \"['.log']\""
        )
        self.child.expect(f"{self.user}:~\\$")

        self.child.sendline(command)
        self.child.expect(f"{self.user}:~\\$")
        output = self.child.before.decode("utf-8").split("\n")[1].strip()
        self.assertEqual(expected, output)

    def test_61_allowed_extension_fail(self):
        """F61 | allow extension and cat file with different extension"""

        command = f"cat {CONFIG}"
        expected = f"*** forbidden file extension ['.conf']: cat {CONFIG}"

        self.child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} "
            "--allowed \"+ ['cat']\" "
            "--allowed_file_extensions \"['.log']\""
        )
        self.child.expect(f"{self.user}:~\\$")

        self.child.sendline(command)
        self.child.expect(f"{self.user}:~\\$")
        output = self.child.before.decode("utf-8").split("\n")[1].strip()
        self.assertEqual(expected, output)

    def test_62_allowed_extension_empty(self):
        """F61 | allow extension empty and cat any file extension"""

        command = f"cat {CONFIG}"
        expected = "[global]"

        self.child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} "
            "--allowed \"+ ['cat']\" "
            '--allowed_file_extensions "[]"'
        )
        self.child.expect(f"{self.user}:~\\$")

        self.child.sendline(command)
        self.child.expect(f"{self.user}:~\\$")
        output = self.child.before.decode("utf-8").split("\n")[1].strip()
        self.assertEqual(expected, output)
