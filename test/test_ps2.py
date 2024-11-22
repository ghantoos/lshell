"""Functional tests for lshell"""

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
            "bg  cd  clear  echo  exit  fg  help  history  jobs  ll  lpath  ls  lsudo"
        )
        child.sendline("help")
        child.expect(PROMPT)
        help_output = child.before.decode("utf8").split("\n", 2)[1].strip()

        self.assertEqual(expected_help_output, help_output)

        # Step 2: Enter `echo FREEDOM! && help () sh && help`
        expected_output = (
            "1\r\nFREEDOM!\r\n"
            "bg  cd  clear  echo  exit  fg  help  history  jobs  ll  lpath  ls  lsudo\r\n"
            "bg  cd  clear  echo  exit  fg  help  history  jobs  ll  lpath  ls  lsudo"
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
