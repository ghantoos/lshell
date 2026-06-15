"""Functional tests for lshell completion"""

import os
import tempfile
import unittest
from getpass import getuser
import pexpect  # pylint: disable=wrong-import-order

from lshell import completion
from lshell.config.runtime import CheckConfig


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
        self.child.setwinsize(2000, 200)

    def tearDown(self):
        self.child.close()

    def do_exit(self, child):
        """Exit the shell"""
        child.sendline("exit")
        child.expect(pexpect.EOF)

    def test_cmd_completion_tab_tab(self):
        """F15 | command completion: tab to list commands"""
        conf = CheckConfig([f"--config={CONFIG}", "--quiet=1"]).returnconf()
        result = completion.completenames(conf, "", "")

        for command in [
            "bg",
            "cd",
            "clear",
            "echo",
            "exit",
            "help",
            "history",
            "jobs",
            "lshow",
        ]:
            self.assertIn(command, result)

    def test_path_completion_tilda(self):
        """F14 | path completion with ~/"""
        home_dir = f"/home/{USER}"
        conf = CheckConfig([f"--config={CONFIG}", "--quiet=1"]).returnconf()
        prefix = next(tempfile._get_candidate_names())
        dir1 = os.path.join(home_dir, f"{prefix}_dir_1")
        dir2 = os.path.join(home_dir, f"{prefix}_dir_2")
        os.mkdir(dir1)
        os.mkdir(dir2)

        try:
            output = set(
                completion.complete_change_dir(
                    conf,
                    prefix,
                    f"cd ~/{prefix}",
                    0,
                    len(f"cd ~/{prefix}"),
                )
            )
            self.assertIn(f"{prefix}_dir_1/", output)
            self.assertIn(f"{prefix}_dir_2/", output)
        finally:
            os.rmdir(dir1)
            os.rmdir(dir2)

    def test_file_completion_tilda(self):
        """F15 | file completion ls with ~/"""
        home_dir = f"/home/{USER}"
        conf = CheckConfig([f"--config={CONFIG}", "--quiet=1"]).returnconf()
        prefix = next(tempfile._get_candidate_names())
        dir1 = os.path.join(home_dir, f"{prefix}_dir_1")
        dir2 = os.path.join(home_dir, f"{prefix}_dir_2")
        file1 = os.path.join(home_dir, f"{prefix}_file_1")
        file2 = os.path.join(home_dir, f"{prefix}_file_2")
        os.mkdir(dir1)
        os.mkdir(dir2)
        open(file1, "w", encoding="utf-8").close()
        open(file2, "w", encoding="utf-8").close()

        try:
            output = set(
                completion.complete_list_dir(
                    conf,
                    prefix,
                    f"ls ~/{prefix}",
                    0,
                    len(f"ls ~/{prefix}"),
                )
            )
            self.assertIn(f"{prefix}_dir_1/", output)
            self.assertIn(f"{prefix}_dir_2/", output)
            self.assertIn(f"{prefix}_file_1 ", output)
            self.assertIn(f"{prefix}_file_2 ", output)
        finally:
            os.rmdir(dir1)
            os.rmdir(dir2)
            os.remove(file1)
            os.remove(file2)

    def test_file_completion_with_arg(self):
        """F15 | file completion ls with ~/"""
        home_dir = f"/home/{USER}"
        conf = CheckConfig([f"--config={CONFIG}", "--quiet=1"]).returnconf()
        prefix = next(tempfile._get_candidate_names())
        dir1 = os.path.join(home_dir, f"{prefix}_dir_1")
        dir2 = os.path.join(home_dir, f"{prefix}_dir_2")
        file1 = os.path.join(home_dir, f"{prefix}_file_1")
        file2 = os.path.join(home_dir, f"{prefix}_file_2")
        os.mkdir(dir1)
        os.mkdir(dir2)
        open(file1, "w", encoding="utf-8").close()
        open(file2, "w", encoding="utf-8").close()

        try:
            output = set(
                completion.complete_list_dir(
                    conf,
                    prefix,
                    f"ls -l ~/{prefix}",
                    0,
                    len(f"ls -l ~/{prefix}"),
                )
            )
            self.assertIn(f"{prefix}_dir_1/", output)
            self.assertIn(f"{prefix}_dir_2/", output)
            self.assertIn(f"{prefix}_file_1 ", output)
            self.assertIn(f"{prefix}_file_2 ", output)
        finally:
            os.rmdir(dir1)
            os.rmdir(dir2)
            os.remove(file1)
            os.remove(file2)

    def test_cmd_completion_dot_slash(self):
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
