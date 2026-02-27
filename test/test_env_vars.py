"""Test environment variables in lshell"""

import os
import unittest
from getpass import getuser
import tempfile
import pexpect

# import lshell specifics
from lshell import utils

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

    def test_22_expand_env_variables(self):
        """F22 | expanding of environment variables"""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--allowed \"+ ['export']\""
        )
        child.expect(PROMPT)

        expected = f"{os.path.expanduser('~')}/test"
        child.sendline("export A=test")
        child.expect(PROMPT)
        child.sendline("echo $HOME/$A")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_23_expand_env_variables_cd(self):
        """F23 | expanding of environment variables when using cd"""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--allowed \"+ ['export']\""
        )
        child.expect(PROMPT)

        random = utils.random_string(32)

        expected = f"lshell: {os.path.expanduser('~')}/random_{random}: No such file or directory"
        child.sendline(f"export A=random_{random}")
        child.expect(PROMPT)
        child.sendline("cd $HOME/$A")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_37_env_vars_file_not_found(self):
        """Test missing environment variable file"""
        missing_file_path = "/path/to/missing/file"

        # Inject the environment variable file path
        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} "
            f"--env_vars_files \"['{missing_file_path}']\""
        )

        # Expect the prompt after shell startup
        child.expect(PROMPT)

        # Simulate what happens when the environment variable file is missing
        expected = (
            f"ERROR: Unable to read environment file: {missing_file_path}\r\n"
            "You are in a limited shell.\r\n"
            "Type '?' or 'help' to get the list of allowed commands\r\n"
        )

        # Check the error message in the output
        self.assertIn(expected, child.before.decode("utf8"))
        self.do_exit(child)

    def test_38_load_env_vars_from_file(self):
        """Test loading environment variables from file"""

        # Create a temporary file to store environment variables
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, dir="/tmp"
        ) as temp_env_file:
            temp_env_file.write("export bar=helloworld\n")
            temp_env_file.flush()  # Ensure data is written to disk
            temp_env_file_path = temp_env_file.name

        # Set the temp env file path in the config
        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} "
            f"--env_vars_files \"['{temp_env_file_path}']\""
        )
        child.expect(PROMPT)

        # Test if the environment variable was loaded
        child.sendline("echo $bar")
        child.expect(PROMPT)

        result = child.before.decode("utf8").strip().split("\n", 1)[1].strip()
        self.assertEqual(result, "helloworld")

        # Cleanup the temporary file
        os.remove(temp_env_file_path)
        self.do_exit(child)

    def test_47_backticks(self):
        """F47 | Forbidden backticks should be reported"""
        expected = (
            '*** forbidden character -> "`"\r\n'
            "*** You have 1 warning(s) left, before getting kicked out.\r\n"
            "This incident has been reported.\r\n"
        )
        self.child.sendline("echo `uptime`")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_48_replace_backticks_with_dollar_parentheses(self):
        """F48 | Forbidden syntax $(command) should be reported"""
        expected = (
            '*** forbidden character -> "$("\r\n'
            "*** You have 1 warning(s) left, before getting kicked out.\r\n"
            "This incident has been reported.\r\n"
        )
        self.child.sendline("echo $(uptime)")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_49_env_variable_with_dollar_braces(self):
        """F49 | Syntax ${command} should replace with the variable"""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--env_vars \"{'foo':'OK'}\""
        )
        child.expect(PROMPT)

        child.sendline("echo ${foo}")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n", 1)[1]
        expected = "OK\r\n"
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_50_single_quotes_do_not_expand_variables(self):
        """F50 | Single-quoted variables should not be expanded."""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--allowed \"+ ['export']\""
        )
        child.expect(PROMPT)

        child.sendline("export A=VALUE")
        child.expect(PROMPT)
        child.sendline("echo '$A'")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n", 1)[1].strip()
        self.assertEqual("$A", result)
        self.do_exit(child)

    def test_51_inline_assignment_is_command_scoped(self):
        """F51 | VAR=... cmd should not persist in parent shell."""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--allowed \"+ ['printenv']\""
        )
        child.expect(PROMPT)

        child.sendline("A=INLINE printenv A")
        child.expect(PROMPT)
        inline_result = child.before.decode("utf8").split("\n", 1)[1].strip()
        self.assertEqual("INLINE", inline_result)

        child.sendline("printenv A")
        child.expect(PROMPT)
        persisted_result = child.before.decode("utf8").split("\n", 1)[1].strip()
        self.assertEqual("", persisted_result)
        self.do_exit(child)
