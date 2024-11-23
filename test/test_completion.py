"""Functional tests for lshell completion"""

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

    def test_15_cmd_completion_tab_tab(self):
        """F15 | command completion: tab to list commands"""
        expected = (
            "\x07\r\nbg       clear    exit     help     jobs     lpath    lsudo    "
            "\r\ncd       echo     fg       history  ll       ls"
        )
        self.child.sendline("\t\t")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").strip()

        self.assertEqual(expected, result)

    def test_14_path_completion_tilda(self):
        """F14 | path completion with ~/"""
        p = subprocess.Popen(
            "ls -F ~/", shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE
        )
        # Create two random files in the home directory
        file1 = os.path.join("random_file_1.txt")
        file2 = os.path.join("random_file_2.txt")
        with open(file1, "w") as f:
            f.write("This is a random file 1.")
        with open(file2, "w") as f:
            f.write("This is a random file 2.")
        cout = p.stdout
        expected = cout.read().decode("utf8").strip().split()
        self.child.sendline("cd \t\t")
        self.child.expect(PROMPT)
        output = (
            self.child.before.decode("utf8").strip().split("\n", 1)[1].strip().split()
        )
        output = [
            item
            for item in output
            if not item.startswith("--More--") and not item.startswith("\x1b")
        ]
        self.assertEqual(len(expected), len(output))

        # cleanup
        os.remove(file1)
        os.remove(file2)

    def test_26_cmd_completion_dot_slash(self):
        """F26 | command completion: tab to list ./foo1 ./foo2"""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--allowed \"+ ['./foo1', './foo2']\""
        )
        child.expect(PROMPT)

        expected = "./\x07foo\x07\r\nfoo1  foo2"
        child.sendline("./\t\t\t")
        child.expect(PROMPT)
        result = child.before.decode("utf8").strip()

        self.assertEqual(expected, result)
        self.do_exit(child)
