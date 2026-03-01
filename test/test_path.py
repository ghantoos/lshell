"""Functional tests for lshell path handling"""

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

    def test_05_external_echo_forbidden_syntax(self):
        """F05 | echo forbidden syntax $(bleh)"""
        expected = (
            'lshell: forbidden character: "$("\r\n'
            "lshell: warning: 1 violation remaining before session termination\r\n"
        )
        self.child.sendline("echo $(uptime)")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_09_external_forbidden_path(self):
        """F09 | external command forbidden path - ls /root"""
        expected = (
            'lshell: forbidden path: "/root/"\r\n'
            "lshell: warning: 1 violation remaining before session termination\r\n"
        )
        self.child.sendline("ls ~root")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_10_builtin_cd_forbidden_path(self):
        """F10 | built-in command forbidden path - cd ~root"""
        expected = (
            'lshell: forbidden path: "/root/"\r\n'
            "lshell: warning: 1 violation remaining before session termination\r\n"
        )
        self.child.sendline("cd ~root")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_11_etc_passwd_1(self):
        """F11 | /etc/passwd: empty variable 'ls "$a"/etc/passwd'"""
        expected = (
            'lshell: forbidden path: "/etc/passwd"\r\n'
            "lshell: warning: 1 violation remaining before session termination\r\n"
        )
        self.child.sendline('ls "$a"/etc/passwd')
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_12_etc_passwd_2(self):
        """F12 | /etc/passwd: empty variable 'ls -l .*./.*./etc/passwd'"""
        expected = (
            "ls: cannot access '.*./.*./etc/passwd': No such file or directory\r\n"
        )
        self.child.sendline("ls -l .*./.*./etc/passwd")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_13a_etc_passwd_3(self):
        """F13(a) | /etc/passwd: empty variable 'ls -l .?/.?/etc/passwd'"""
        expected = "ls: cannot access '.?/.?/etc/passwd': No such file or directory\r\n"
        self.child.sendline("ls -l .?/.?/etc/passwd")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_13b_etc_passwd_4(self):
        """F13(b) | /etc/passwd: empty variable 'ls -l ../../etc/passwd'"""
        expected = (
            'lshell: forbidden path: "/etc/passwd"\r\n'
            "lshell: warning: 1 violation remaining before session termination\r\n"
        )
        self.child.sendline("ls -l ../../etc/passwd")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_21_allow_slash(self):
        """F21 | user should able to allow / access minus some directory
        (e.g. /var)
        """
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--path \"['/'] - ['/var']\""
        )
        child.expect(PROMPT)

        expected = 'lshell: forbidden path: "/var/"'
        child.sendline("cd /")
        child.expect(f"{USER}:/\\$")
        child.sendline("cd var")
        child.expect(f"{USER}:/\\$")
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)
