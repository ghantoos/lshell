"""Functional tests for lshell completion"""

import os
import shutil
import tempfile
import unittest
from getpass import getuser
import pexpect  # pylint: disable=wrong-import-order


TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"
LSHELL = f"{TOPDIR}/bin/lshell"
USER = getuser()
PROMPT = f"{USER}:~\\$"
PROMPT_ANY_DIR = f"{USER}:.+\\$"


class TestFunctions(unittest.TestCase):
    """Functional tests for lshell"""

    def _clean_env(self, extra=None):
        """Return a sanitized environment for deterministic child shells."""
        env = os.environ.copy()
        env.pop("LSHELL_ARGS", None)
        env.pop("LPS1", None)
        if extra:
            env.update(extra)
        return env

    def setUp(self):
        """spawn lshell with pexpect and return the child"""
        self.child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} --strict 1",
            env=self._clean_env(),
        )
        self.child.expect(PROMPT)

    def tearDown(self):
        self.child.close()

    def do_exit(self, child):
        """Exit the shell"""
        child.sendline("exit")
        child.expect(pexpect.EOF)

    def _make_home_completion_fixture(self, fixture_name):
        """Create an isolated directory under the user's home for completion tests."""
        home_dir = os.path.expanduser("~")
        root_dir = tempfile.mkdtemp(prefix=f"lshell-{fixture_name}-", dir=home_dir)
        dir1_name = "alpha-dir"
        dir2_name = "beta-dir"
        file1_name = "alpha-file"
        file2_name = "beta-file"
        os.mkdir(os.path.join(root_dir, dir1_name))
        os.mkdir(os.path.join(root_dir, dir2_name))
        open(os.path.join(root_dir, file1_name), "w", encoding="utf-8").close()
        open(os.path.join(root_dir, file2_name), "w", encoding="utf-8").close()
        return {
            "root_dir": root_dir,
            "root_name": os.path.basename(root_dir),
            "dirs": {f"{dir1_name}/", f"{dir2_name}/"},
            "entries": {
                f"{dir1_name}/",
                f"{dir2_name}/",
                file1_name,
                file2_name,
            },
        }

    def test_cmd_completion_tab_tab(self):
        """F15 | command completion: tab to list commands"""
        self.child.sendline("\t\t")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").strip()

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
            "source",
        ]:
            self.assertIn(command, result)

    def test_path_completion_tilda(self):
        """F14 | path completion with ~/"""
        fixture = self._make_home_completion_fixture("completion-dir")
        try:
            self.child.sendline(f"cd ~/{fixture['root_name']}/\t\t")
            self.child.expect(PROMPT_ANY_DIR)
            output = self.child.before.decode("utf8")
            self.assertIn("Allowed directories", output)
            for directory in fixture["dirs"]:
                self.assertIn(directory, output)
        finally:
            shutil.rmtree(fixture["root_dir"])

    def test_file_completion_tilda(self):
        """F15 | file completion ls with ~/"""
        fixture = self._make_home_completion_fixture("completion-file")
        try:
            self.child.sendline(f"ls ~/{fixture['root_name']}/\t\t")
            self.child.expect(PROMPT)
            output = self.child.before.decode("utf8")
            self.assertIn("Allowed paths", output)
            for entry in fixture["entries"]:
                self.assertIn(entry, output)
        finally:
            shutil.rmtree(fixture["root_dir"])

    def test_file_completion_with_arg(self):
        """F15 | file completion ls with ~/"""
        fixture = self._make_home_completion_fixture("completion-arg")
        try:
            self.child.sendline(f"ls -l ~/{fixture['root_name']}/\t\t")
            self.child.expect(PROMPT)
            output = self.child.before.decode("utf8")
            self.assertIn("Allowed paths", output)
            for entry in fixture["entries"]:
                self.assertIn(entry.rstrip("/"), output)
        finally:
            shutil.rmtree(fixture["root_dir"])

    def test_cmd_completion_dot_slash(self):
        """F26 | command completion: tab to list ./foo1 ./foo2"""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--allowed \"+ ['./foo1', './foo2']\"",
            env=self._clean_env(),
        )
        child.expect(PROMPT)

        child.sendline("./\t\t\t")
        child.expect(PROMPT)
        result = child.before.decode("utf8").strip()

        self.assertIn("Allowed commands", result)
        self.assertIn("foo1", result)
        self.assertIn("foo2", result)
        self.do_exit(child)
