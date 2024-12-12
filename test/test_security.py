"""Functional tests for lshell security features"""

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

    def test_31_security_echo_freedom_and_help(self):
        """F31 | test help, then echo FREEDOM! && help () sh && help"""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} --forbidden \"-[';','&']\" "
        )
        child.expect(PROMPT)

        # Step 1: Enter `help` command
        expected_help_output = "bg  cd  clear  echo  exit  fg  help  history  jobs  ll  lpath  ls  lsudo  source"
        child.sendline("help")
        child.expect(PROMPT)
        help_output = child.before.decode("utf8").split("\n", 1)[1].strip()

        self.assertEqual(expected_help_output, help_output)

        # Step 2: Enter `echo FREEDOM! && help () sh && help`
        expected_output = (
            "FREEDOM!\r\nbg  cd  clear  echo  exit  fg  help  history  "
            "jobs  ll  lpath  ls  lsudo  source\r\n"
            "bg  cd  clear  echo  exit  fg  help  history  jobs  ll  lpath  ls  lsudo  source"
        )
        child.sendline("echo FREEDOM! && help () sh && help")
        child.expect(PROMPT)

        result = child.before.decode("utf8").strip().split("\n", 1)[1].strip()

        # Verify the combined output
        self.assertEqual(expected_output, result)
        self.do_exit(child)

    def test_32_security_echo_freedom_and_cd(self):
        """F32 | test echo FREEDOM! && cd () bash && cd ~/"""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} --forbidden \"-[';','&']\" "
        )
        child.expect(PROMPT)

        # Step 1: Enter `help` command
        expected_help_output = "bg  cd  clear  echo  exit  fg  help  history  jobs  ll  lpath  ls  lsudo  source"
        child.sendline("help")
        child.expect(PROMPT)
        help_output = child.before.decode("utf8").split("\n", 1)[1].strip()

        self.assertEqual(expected_help_output, help_output)

        # Step 2: Enter `echo FREEDOM! && help () sh && help`
        expected_output = "FREEDOM!\r\nlshell: () bash: No such file or directory"
        child.sendline("echo FREEDOM! && cd () bash && cd ~/")
        child.expect(PROMPT)

        result = child.before.decode("utf8").strip().split("\n", 1)[1].strip()

        # Verify the combined output
        self.assertEqual(expected_output, result)
        self.do_exit(child)

    def test_27_checksecure_awk(self):
        """F27 | checksecure awk script with /bin/sh"""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--allowed \"+ ['awk']\""
        )
        child.expect(PROMPT)

        if test_utils.is_alpine_linux():
            command = "awk 'BEGIN {system(\"/bin/sh\")}'"
            expected = "*** forbidden path: /bin/busybox"
        else:
            command = "awk 'BEGIN {system(\"/usr/bin/bash\")}'"
            expected = "*** forbidden path: /usr/bin/bash"
        child.sendline(command)
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()

        self.assertEqual(expected, result)
        self.do_exit(child)
