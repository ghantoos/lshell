"""Functional tests for lshell command execution"""

import os
import unittest
from getpass import getuser
import pexpect

# pylint: disable=C0411
from test import test_utils

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

    def test_03_external_echo_command_num(self):
        """F03 | external echo number"""
        expected = "32"
        self.child.sendline("echo 32")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split()[2]
        self.assertEqual(expected, result)

    def test_04_external_echo_command_string(self):
        """F04 | external echo random string"""
        expected = "bla blabla  32 blibli! plop."
        self.child.sendline(f'echo "{expected}"')
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1].strip()
        self.assertEqual(expected, result)

    def test_16a_exitcode_with_separator_external_cmd(self):
        """F16(a) | external command exit codes with separator"""
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG} " '--forbidden "[]"')
        child.expect(PROMPT)

        if test_utils.is_alpine_linux():
            expected_1 = "ls: nRVmmn8RGypVneYIp8HxyVAvaEaD55: No such file or directory"
        else:
            expected_1 = (
                "ls: cannot access 'nRVmmn8RGypVneYIp8HxyVAvaEaD55': "
                "No such file or directory"
            )
        expected_2 = "blabla"
        expected_3 = "0"
        child.sendline("ls nRVmmn8RGypVneYIp8HxyVAvaEaD55; echo blabla; echo $?")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")
        result_1 = result[1].strip()
        result_2 = result[2].strip()
        result_3 = result[3].strip()
        self.assertEqual(expected_1, result_1)
        self.assertEqual(expected_2, result_2)
        self.assertEqual(expected_3, result_3)
        self.do_exit(child)

    def test_16b_exitcode_with_separator_external_cmd(self):
        """F16(b) | external command exit codes with separator"""
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG} " '--forbidden "[]"')
        child.expect(PROMPT)

        if test_utils.is_alpine_linux():
            expected_1 = "ls: nRVmmn8RGypVneYIp8HxyVAvaEaD55: No such file or directory"
            expected_2 = "1"
        else:
            expected_1 = (
                "ls: cannot access 'nRVmmn8RGypVneYIp8HxyVAvaEaD55': "
                "No such file or directory"
            )
            expected_2 = "2"
        child.sendline("ls nRVmmn8RGypVneYIp8HxyVAvaEaD55; echo $?")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")
        result_1 = result[1].strip()
        result_2 = result[2].strip()
        self.assertEqual(expected_1, result_1)
        self.assertEqual(expected_2, result_2)
        self.do_exit(child)

    def test_17_exitcode_without_separator_external_cmd(self):
        """F17 | external command exit codes without separator"""
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG} " '--forbidden "[]"')
        child.expect(PROMPT)

        if test_utils.is_alpine_linux():
            expected = "1"
        else:
            expected = "2"
        child.sendline("ls nRVmmn8RGypVneYIp8HxyVAvaEaD55")
        child.expect(PROMPT)
        child.sendline("echo $?")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_24_cd_and_command(self):
        """F24 | cd && command should not be interpreted by internal function"""
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG}")
        child.expect(PROMPT)

        expected = "OK"
        child.sendline('cd ~ && echo "OK"')
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_33_ls_non_existing_directory_and_echo(self):
        """Test: ls non_existing_directory && echo nothing"""
        child = pexpect.spawn(f"{LSHELL} --config {CONFIG}")
        child.expect(PROMPT)

        child.sendline("ls non_existing_directory && echo nothing")
        child.expect(PROMPT)

        output = child.before.decode("utf8").split("\n", 1)[1].strip()
        # Since ls fails, echo nothing shouldn't run
        self.assertNotIn("nothing", output)
        self.do_exit(child)

    def test_34_ls_and_echo_ok(self):
        """Test: ls && echo OK"""
        child = pexpect.spawn(f"{LSHELL} --config {CONFIG}")
        child.expect(PROMPT)

        child.sendline("ls && echo OK")
        child.expect(PROMPT)

        output = child.before.decode("utf8").split("\n", 1)[1].strip()
        # ls succeeds, echo OK should run
        self.assertIn("OK", output)
        self.do_exit(child)

    def test_35_ls_non_existing_directory_or_echo_ok(self):
        """Test: ls non_existing_directory || echo OK"""
        child = pexpect.spawn(f"{LSHELL} --config {CONFIG}")
        child.expect(PROMPT)

        child.sendline("ls non_existing_directory || echo OK")
        child.expect(PROMPT)

        output = child.before.decode("utf8").split("\n", 1)[1].strip()
        # ls fails, echo OK should run
        self.assertIn("OK", output)
        self.do_exit(child)

    def test_36_ls_or_echo_nothing(self):
        """Test: ls || echo nothing"""
        child = pexpect.spawn(f"{LSHELL} --config {CONFIG}")
        child.expect(PROMPT)

        child.sendline("ls || echo nothing")
        child.expect(PROMPT)

        output = child.before.decode("utf8").split("\n", 1)[1].strip()
        # ls succeeds, echo nothing should not run
        self.assertNotIn("nothing", output)
        self.do_exit(child)

    def test_41_multicmd_with_wrong_arg_should_fail(self):
        """F20 | Allowing 'echo asd': Test 'echo qwe' should fail"""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--allowed \"['echo asd']\""
        )
        child.expect(PROMPT)

        expected = "*** forbidden command: echo"

        child.sendline("echo qwe")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_42_multicmd_with_near_exact_arg_should_fail(self):
        """F41 | Allowing 'echo asd': Test 'echo asds' should fail"""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--allowed \"['echo asd']\""
        )
        child.expect(PROMPT)

        expected = "*** forbidden command: echo"

        child.sendline("echo asds")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_43_multicmd_without_arg_should_fail(self):
        """F42 | Allowing 'echo asd': Test 'echo' should fail"""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--allowed \"['echo asd']\""
        )
        child.expect(PROMPT)

        expected = "*** forbidden command: echo"

        child.sendline("echo")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_44_multicmd_asd_should_pass(self):
        """F43 | Allowing 'echo asd': Test 'echo asd' should pass"""

        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--allowed \"['echo asd']\""
        )
        child.expect(PROMPT)

        expected = "asd"

        child.sendline("echo asd")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)
