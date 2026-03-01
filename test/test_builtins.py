"""Functional tests for lshell built-in commands"""

import os
import unittest
import subprocess
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

    def test_01_welcome_message(self):
        """F01 | lshell welcome message"""
        expected = (
            "You are in a limited shell.\r\nType '?' or 'help' to get"
            " the list of allowed commands\r\n"
        )
        result = self.child.before.decode("utf8")
        self.assertEqual(expected, result)

    def test_02_builtin_ls_command(self):
        """F02 | built-in ls command"""
        p = subprocess.Popen(
            "ls ~", shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE
        )
        cout = p.stdout
        expected = cout.read(-1)
        self.child.sendline("ls")
        self.child.expect(PROMPT)
        output = self.child.before.decode("utf8").split("ls\r", 1)[1]
        self.assertEqual(len(expected.strip().split()), len(output.strip().split()))

    def test_06_builtin_cd_change_dir(self):
        """F06 | built-in cd - change directory"""
        expected = ""
        home = os.path.expanduser("~")
        dirpath = None
        for path in os.listdir(home):
            dirpath = os.path.join(home, path)
            if os.path.isdir(dirpath):
                break
        if dirpath:
            self.child.sendline(f"cd {path}")
            self.child.expect(f"{USER}:~/{path}\\$")
            self.child.sendline("cd ..")
            self.child.expect(PROMPT)
            result = self.child.before.decode("utf8").split("\n", 1)[1]
            self.assertEqual(expected, result)

    def test_07_builtin_cd_tilda(self):
        """F07 | built-in cd - tilda bug"""
        expected = (
            'lshell: forbidden path: "/etc/passwd"\r\n'
            "lshell: warning: 1 violation remaining before session termination\r\n"
        )
        self.child.sendline("ls ~/../../etc/passwd")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_08_builtin_cd_quotes(self):
        """F08 | built-in - quotes in cd "/" """
        expected = (
            'lshell: forbidden path: "/"\r\n'
            "lshell: warning: 1 violation remaining before session termination\r\n"
        )
        self.child.sendline('ls -ld "/"')
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_18_cd_exitcode_with_separator_internal_cmd(self):
        """F18 | built-in command exit codes with separator"""
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG} " '--forbidden "[]"')
        child.expect(PROMPT)

        expected = "2"
        child.sendline("cd nRVmmn8RGypVneYIp8HxyVAvaEaD55; echo $?")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[2].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_19_cd_exitcode_without_separator_external_cmd(self):
        """F19 | built-in exit codes without separator"""
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG} " '--forbidden "[]"')
        child.expect(PROMPT)

        expected = "2"
        child.sendline("cd nRVmmn8RGypVneYIp8HxyVAvaEaD55")
        child.expect(PROMPT)
        child.sendline("echo $?")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_20_cd_with_cmd_unknwon_dir(self):
        """F20 | test built-in cd with command when dir does not exist
        Should be returning error, not executing cmd
        """
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG} " '--forbidden "[]"')
        child.expect(PROMPT)

        expected = (
            "lshell: nRVmmn8RGypVneYIp8HxyVAvaEaD55: No such file or " "directory"
        )

        child.sendline("cd nRVmmn8RGypVneYIp8HxyVAvaEaD55; echo $?")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_68_source_nonexistent_file(self):
        """F68 | Test sourcing a nonexistent environment file shows an error"""

        # Define a nonexistent file path
        env_file = "does_not_exist"

        # Start lshell and attempt to source the nonexistent file
        child = pexpect.spawn(f"{LSHELL} --config {CONFIG} --allowed \"+['source']\"")
        child.expect(PROMPT)

        # Source the nonexistent file and check for an error message
        child.sendline(f"source {env_file}")
        child.expect(PROMPT)

        output = child.before.decode("utf-8").split("\n")[1].strip()
        expected_output = f"ERROR: Unable to read environment file: {env_file}"

        assert (
            output == expected_output
        ), f"Expected '{expected_output}', got '{output}'"

        # Clean up and end session
        self.do_exit(child)

    def test_69_source_valid_file(self):
        """F69 | Test sourcing a valid environment file sets variables"""

        # Write a sample environment file
        env_file = "random_test_env"
        with open(env_file, "w") as file:
            file.write("export TEST_VAR='test_value'\n")

        # Start lshell and source the environment file
        child = pexpect.spawn(f"{LSHELL} --config {CONFIG} --allowed \"+['source']\"")
        child.expect(PROMPT)

        # Source the file and check if the variable is set
        child.sendline(f"source {env_file}")
        child.expect(PROMPT)
        child.sendline("echo $TEST_VAR")
        child.expect(PROMPT)

        output = child.before.decode("utf-8").split("\n")[1].strip()
        expected_output = "test_value"

        assert (
            output == expected_output
        ), f"Expected '{expected_output}', got '{output}'"

        # Clean up and end session
        self.do_exit(child)

    def test_70_source_overwrite_variable(self):
        """F70 | Test sourcing a file overwrites existing environment variables"""

        # Write a sample environment file
        env_file = "test_env_overwrite"
        with open(env_file, "w") as file:
            file.write("export TEST_VAR='new_value'\n")

        # Start lshell, set initial variable, and source file to overwrite it
        child = pexpect.spawn(f"{LSHELL} --config {CONFIG} --allowed \"+['source']\"")
        child.expect(PROMPT)

        # Set initial variable and source the file
        child.sendline("export TEST_VAR='initial_value'")
        child.expect(PROMPT)
        child.sendline(f"source {env_file}")
        child.expect(PROMPT)
        child.sendline("echo $TEST_VAR")
        child.expect(PROMPT)

        output = child.before.decode("utf-8").split("\n")[1].strip()
        expected_output = "new_value"

        assert (
            output == expected_output
        ), f"Expected '{expected_output}', got '{output}'"

        # Clean up and end session
        self.do_exit(child)
