"""Functional tests for lshell"""

import os
import unittest
import inspect
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

    def test_51_grep_valid_log_entry(self):
        """F51 | Test that grep matches a valid log entry format."""
        pattern = (
            r"\[\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}\s+(?:-|\+)\d{4}\].+UID=[\w.]+"
        )
        f_name = inspect.currentframe().f_code.co_name
        log_file = f"{TOPDIR}/test/testfiles/{f_name}.log"
        command = f"grep -P '{pattern}' {log_file}"

        child = pexpect.spawn(
            (
                f"{LSHELL} --config {CONFIG} "
                f'--allowed "+ [\'grep\']" --forbidden "[]"'
            )
        )
        child.expect(PROMPT)

        child.sendline(command)
        child.expect(PROMPT)
        output = child.before.decode("utf-8")
        self.assertIn("user123", output)
        self.do_exit(child)

    def test_52_grep_invalid_date_format(self):
        """F52 | Test that grep matches a valid log entry format."""
        pattern = (
            r"\[\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}\s+(?:-|\+)\d{4}\].+UID=[\w.]+"
        )
        f_name = inspect.currentframe().f_code.co_name
        log_file = f"{TOPDIR}/test/testfiles/{f_name}.log"
        command = f"grep -P '{pattern}' {log_file}"

        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} " '--allowed "+ [\'grep\']" --forbidden "[]"'
        )
        child.expect(PROMPT)

        child.sendline(command)
        child.expect(PROMPT)
        output = child.before.decode("utf-8")
        self.assertNotIn("user123", output)
        self.do_exit(child)

    def test_53_grep_missing_uid(self):
        """F53 | Test that grep matches a valid log entry format."""
        pattern = (
            r"\[\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}\s+(?:-|\+)\d{4}\].+UID=[\w.]+"
        )
        f_name = inspect.currentframe().f_code.co_name
        log_file = f"{TOPDIR}/test/testfiles/{f_name}.log"
        command = f"grep -P '{pattern}' {log_file}"

        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} " '--allowed "+ [\'grep\']" --forbidden "[]"'
        )
        child.expect(PROMPT)

        child.sendline(command)
        child.expect(PROMPT)
        output = child.before.decode("utf-8")
        self.assertNotIn("user123", output)
        self.do_exit(child)

    def test_54_grep_special_characters_in_uid(self):
        """F54 | Test that grep matches a valid log entry format."""
        pattern = (
            r"\[\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}\s+(?:-|\+)\d{4}\].+UID=[\w.]+"
        )
        f_name = inspect.currentframe().f_code.co_name
        log_file = f"{TOPDIR}/test/testfiles/{f_name}.log"
        command = f"grep -P '{pattern}' {log_file}"

        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} " '--allowed "+ [\'grep\']" --forbidden "[]"'
        )
        child.expect(PROMPT)

        child.sendline(command)
        child.expect(PROMPT)
        output = child.before.decode("utf-8")
        self.assertIn("user.name", output)
        self.do_exit(child)

    def test_55_allowed_all_minus_list(self):
        """F55 | allow all commands minus the list"""

        command = "echo 1"
        expected = "*** forbidden command: echo"

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
        expected2 = "*** forbidden path: /usr/local/"

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
            '*** forbidden char/command over SSH: "echo 1"\r\n'
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
        expected = "*** forbidden command: echo"

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
        expected = "*** forbidden character: ;"

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

    def test_60_allowed_extension_success(self):
        """F60 | allow extension and cat file with similar extension"""

        f_name = inspect.currentframe().f_code.co_name
        log_file = f"{TOPDIR}/test/testfiles/{f_name}.log"
        command = f"cat {log_file}"
        expected = "Hello world!"

        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} "
            "--allowed \"+ ['cat']\" "
            "--allowed_file_extensions \"['.log']\""
        )
        child.expect(PROMPT)

        child.sendline(command)
        child.expect(PROMPT)
        output = child.before.decode("utf-8").split("\n")[1].strip()
        self.assertEqual(expected, output)
        self.do_exit(child)

    def test_61_allowed_extension_fail(self):
        """F61 | allow extension and cat file with different extension"""

        command = f"cat {CONFIG}"
        expected = f"*** forbidden file extension ['.conf']: cat {CONFIG}"

        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} "
            "--allowed \"+ ['cat']\" "
            "--allowed_file_extensions \"['.log']\""
        )
        child.expect(PROMPT)

        child.sendline(command)
        child.expect(PROMPT)
        output = child.before.decode("utf-8").split("\n")[1].strip()
        self.assertEqual(expected, output)
        self.do_exit(child)

    def test_62_allowed_extension_empty(self):
        """F62 | allow extension empty and cat any file extension"""

        command = f"cat {CONFIG}"
        expected = "[global]"

        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} "
            "--allowed \"+ ['cat']\" "
            '--allowed_file_extensions "[]"'
        )
        child.expect(PROMPT)

        child.sendline(command)
        child.expect(PROMPT)
        output = child.before.decode("utf-8").split("\n")[1].strip()
        self.assertEqual(expected, output)
        self.do_exit(child)

    def test_63_multi_line_command(self):
        """F63 | Test multi-line command execution using line continuation"""

        # Start the shell process with lshell config
        child = pexpect.spawn(f"{LSHELL} --config {CONFIG} ")
        child.expect(PROMPT)

        # Send a multi-line command using line continuation
        child.sendline("echo 'First line' \\")
        child.sendline("'and second line'")
        child.expect(PROMPT)

        output = child.before.decode("utf-8").split("\n")[2].strip()
        expected_output = "First line and second line"
        assert (
            output == expected_output
        ), f"Expected '{expected_output}', got '{output}'"

        # Send an exit command to end the shell session
        self.do_exit(child)

    def test_64_multi_line_command_with_two_echos(self):
        """F64 | Test multi-line command execution with two echo commands"""

        # Start the shell process with lshell config
        child = pexpect.spawn(f"{LSHELL} --config {CONFIG} --forbidden \"-[';']\"")
        child.expect(PROMPT)

        # Send two echo commands on two lines
        child.sendline("echo 'First line'; echo \\")
        child.sendline("'Second line';")
        child.expect(PROMPT)

        output = child.before.decode("utf-8").split("\n")[2:4]
        expected_output = ["First line\r", "Second line\r"]
        assert (
            output == expected_output
        ), f"Expected '{expected_output}', got '{output}'"

        # Send an exit command to end the shell session
        self.do_exit(child)

    def test_65_multi_line_command_security_echo(self):
        """F65 | test help, then echo FREEDOM! && help () sh && help"""
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG}  --forbidden \"-[';']\"")
        child.expect(PROMPT)

        # Step 1: Enter `help` command
        expected_help_output = (
            "cd  clear  echo  exit  help  history  ll  lpath  ls  lsudo"
        )
        child.sendline("help")
        child.expect(PROMPT)
        help_output = child.before.decode("utf8").split("\n", 2)[1].strip()

        self.assertEqual(expected_help_output, help_output)

        # Step 2: Enter `echo FREEDOM! && help () sh && help`
        expected_output = (
            "1\r\nFREEDOM!\r\ncd  clear  echo  exit  help  history  ll  lpath  ls  lsudo\r\n"
            "cd  clear  echo  exit  help  history  ll  lpath  ls  lsudo"
        )
        child.sendline("echo 1; \\")
        child.expect(">")
        child.sendline("echo FREEDOM! && help () sh && help")
        child.expect(PROMPT)

        result = child.before.decode("utf8").strip().split("\n", 1)[1]

        # Verify the combined output
        self.assertEqual(expected_output, result)
        self.do_exit(child)

    def test_66_multi_line_command_ctrl_c(self):
        """F66 | Test multi-line command then ctrl-c to cancel"""

        # Start the shell process with lshell config
        child = pexpect.spawn(f"{LSHELL} --config {CONFIG} ")
        child.expect(PROMPT)

        # Send a multi-line command using line continuation
        child.sendline("echo 1 \\")
        child.expect(">")
        child.sendcontrol("c")
        child.expect(PROMPT)

        output = child.before.decode("utf-8").split("\n")[1].strip()
        expected_output = ""
        assert (
            output == expected_output
        ), f"Expected '{expected_output}', got '{output}'"

        # Send an exit command to end the shell session
        self.do_exit(child)

    def test_67_unclosed_quotes_traceback(self):
        """F67 | Test that unclsed quotes do not cause a traceback"""

        # Start the shell process with lshell config
        child = pexpect.spawn(f"{LSHELL} --config {CONFIG} ")
        child.expect(PROMPT)

        # Send a multi-line command using line continuation
        child.sendline('echo "OK""')
        child.expect("> ")
        child.sendline('OK"')
        child.expect(PROMPT)

        output = child.before.decode("utf-8").split("\n")[1].strip()
        expected_output = "OKOK"
        assert (
            output == expected_output
        ), f"Expected '{expected_output}', got '{output}'"

        # Send an exit command to end the shell session
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
        expected_output = f"test_value"

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
        expected_output = f"new_value"

        assert (
            output == expected_output
        ), f"Expected '{expected_output}', got '{output}'"

        # Clean up and end session
        self.do_exit(child)
