"""Functional tests for lshell completion"""

import os
import unittest
import subprocess
from getpass import getuser
import pexpect  # pylint: disable=wrong-import-order

from test.test_utils import is_alpine_linux


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
            "\r\ncd       echo     fg       history  ll       ls       source"
        )
        self.child.sendline("\t\t")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").strip()

        self.assertEqual(expected, result)

    def test_14_path_completion_tilda(self):
        """F14 | path completion with ~/"""
        # Create two random directories in the home directory
        home_dir = f"/home/{USER}"
        test_num = 14
        dir1 = f"{home_dir}/test_{test_num}_dir_1"
        dir2 = f"{home_dir}/test_{test_num}_dir_2"
        file1 = f"{home_dir}/test_{test_num}_file_1"
        file2 = f"{home_dir}/test_{test_num}_file_2"
        os.mkdir(dir1)
        os.mkdir(dir2)
        open(file1, "w").close()
        open(file2, "w").close()

        # test dir list
        if is_alpine_linux():
            command = "ls -a -d ~/*/"
        else:
            command = "find . -maxdepth 1 -type d -printf '%f/\n'"
        p_dir_list = subprocess.Popen(
            command,
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        stdout_p_dir_list = p_dir_list.stdout
        expected = stdout_p_dir_list.read().decode("utf8").strip().split()
        # Normalize expected to relative paths
        if is_alpine_linux():
            # Remove the `/home/<user>/` prefix for Alpine Linux
            expected = {os.path.basename(path.rstrip("/")) + "/" for path in expected}
        else:
            expected = set(expected)
        expected = set(expected)
        expected.discard("./")

        self.child.sendline("cd ~/\t\t")
        self.child.expect(PROMPT)
        output = (
            self.child.before.decode("utf8").strip().split("\n", 1)[1].strip().split()
        )
        output = set(output)
        # github action hackish-fix...
        output.discard(".ghcup/")

        self.assertEqual(expected, output)

        # cleanup
        os.rmdir(dir1)
        os.rmdir(dir2)
        os.remove(file1)
        os.remove(file2)

    def test_15_file_completion_tilda(self):
        """F15 | file completion ls with ~/"""
        # Create two random directories in the home directory
        home_dir = f"/home/{USER}"
        test_num = 15
        dir1 = f"{home_dir}/test_{test_num}_dir_1"
        dir2 = f"{home_dir}/test_{test_num}_dir_2"
        file1 = f"{home_dir}/test_{test_num}_file_1"
        file2 = f"{home_dir}/test_{test_num}_file_2"
        os.mkdir(dir1)
        os.mkdir(dir2)
        open(file1, "w").close()
        open(file2, "w").close()

        # test file list
        if is_alpine_linux():
            command = "ls -a -p ~/"
        else:
            command = "find . -maxdepth 1 -printf '%P%y\n' | sed 's|d$|/|;s|f$||'"
        p_file_list = subprocess.Popen(
            command,
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        stdout_p_file_list = p_file_list.stdout
        expected = stdout_p_file_list.read().decode("utf8").strip().split()
        expected = set(expected)
        expected.discard("/")
        # alpine specific because of `ls -a -p`
        if is_alpine_linux():
            expected.discard("./")
            expected.discard("../")

        self.child.sendline("ls ~/\t\t")
        self.child.expect(PROMPT)
        output = (
            self.child.before.decode("utf8").strip().split("\n", 1)[1].strip().split()
        )
        output = set(output)
        # github action hackish-fix...
        output.discard(".ghcup/")
        if ".ghcupl" in expected:
            output.add(".ghcupl")

        self.assertEqual(expected, output)

        # cleanup
        os.rmdir(dir1)
        os.rmdir(dir2)
        os.remove(file1)
        os.remove(file2)

    def test_16_file_completion_with_arg(self):
        """F15 | file completion ls with ~/"""
        # Create two random directories in the home directory
        home_dir = f"/home/{USER}"
        test_num = 16
        dir1 = f"{home_dir}/test_{test_num}_dir_1"
        dir2 = f"{home_dir}/test_{test_num}_dir_2"
        file1 = f"{home_dir}/test_{test_num}_file_1"
        file2 = f"{home_dir}/test_{test_num}_file_2"
        os.mkdir(dir1)
        os.mkdir(dir2)
        open(file1, "w").close()
        open(file2, "w").close()

        # test file list
        if is_alpine_linux():
            command = "ls -a -p ~/"
        else:
            command = "find . -maxdepth 1 -printf '%P%y\n' | sed 's|d$|/|;s|f$||'"
        p_file_list = subprocess.Popen(
            command,
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        stdout_p_file_list = p_file_list.stdout
        expected = stdout_p_file_list.read().decode("utf8").strip().split()
        expected = set(expected)
        expected.discard("/")
        # alpine specific because of `ls -a -p`
        if is_alpine_linux():
            expected.discard("./")
            expected.discard("../")

        self.child.sendline("ls -l ~/\t\t")
        self.child.expect(PROMPT)
        output = (
            self.child.before.decode("utf8").strip().split("\n", 1)[1].strip().split()
        )
        output = set(output)
        # github action hackish-fix...
        output.discard(".ghcup/")
        if ".ghcupl" in expected:
            output.add(".ghcupl")

        self.assertEqual(expected, output)

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
