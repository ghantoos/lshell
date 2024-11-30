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
        # Create two random directories in the home directory
        home_dir = f"/home/{USER}"
        dir1 = f"{home_dir}/test_14_dir_1"
        dir2 = f"{home_dir}/test_14_dir_2"
        file1 = f"{home_dir}/test_14_file_1"
        file2 = f"{home_dir}/test_14_file_2"
        os.mkdir(dir1)
        os.mkdir(dir2)
        open(file1, "w").close()
        open(file2, "w").close()

        # test dir list
        p_dir_list = subprocess.Popen(
            "ls -d ~/*/", shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE
        )
        stdout_p_dir_list = p_dir_list.stdout
        expected_dir = stdout_p_dir_list.read().decode("utf8").strip().split()
        # Normalize expected to relative paths
        expected_dir = [f"{os.path.relpath(path, home_dir)}/" for path in expected_dir]

        self.child.sendline("cd ~/\t\t")
        self.child.expect(PROMPT)
        dir_list_output = (
            self.child.before.decode("utf8").strip().split("\n", 1)[1].strip().split()
        )
        self.assertEqual(expected_dir, dir_list_output)

        # cleanup
        os.rmdir(dir1)
        os.rmdir(dir2)
        os.remove(file1)
        os.remove(file2)

    def test_15_file_completion_tilda(self):
        """F15 | file completion ls with ~/"""
        # Create two random directories in the home directory
        home_dir = f"/home/{USER}"
        dir1 = f"{home_dir}/test_14_dir_1"
        dir2 = f"{home_dir}/test_14_dir_2"
        file1 = f"{home_dir}/test_14_file_1"
        file2 = f"{home_dir}/test_14_file_2"
        os.mkdir(dir1)
        os.mkdir(dir2)
        open(file1, "w").close()
        open(file2, "w").close()

        # test file list
        p_file_list = subprocess.Popen(
            "ls --indicator-style=slash ~/",
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        stdout_p_file_list = p_file_list.stdout
        expected_file = stdout_p_file_list.read().decode("utf8").strip().split()

        self.child.sendline("ls ~/\t\t")
        self.child.expect(PROMPT)
        file_list_output = (
            self.child.before.decode("utf8").strip().split("\n", 1)[1].strip().split()
        )
        self.assertEqual(set(expected_file), set(file_list_output))

        # cleanup
        os.rmdir(dir1)
        os.rmdir(dir2)
        os.remove(file1)
        os.remove(file2)

    def test_16_file_completion_with_arg(self):
        """F15 | file completion ls with ~/"""
        # Create two random directories in the home directory
        home_dir = f"/home/{USER}"
        dir1 = f"{home_dir}/test_14_dir_1"
        dir2 = f"{home_dir}/test_14_dir_2"
        file1 = f"{home_dir}/test_14_file_1"
        file2 = f"{home_dir}/test_14_file_2"
        os.mkdir(dir1)
        os.mkdir(dir2)
        open(file1, "w").close()
        open(file2, "w").close()

        # test file list
        p_file_list = subprocess.Popen(
            "ls --indicator-style=slash ~/",
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        stdout_p_file_list = p_file_list.stdout
        expected_file = stdout_p_file_list.read().decode("utf8").strip().split()

        self.child.sendline("ls -l ~/\t\t")
        self.child.expect(PROMPT)
        file_list_output = (
            self.child.before.decode("utf8").strip().split("\n", 1)[1].strip().split()
        )
        self.assertEqual(set(expected_file), set(file_list_output))

        # cleanup
        os.rmdir(dir1)
        os.rmdir(dir2)
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
