"""Functional integration tests for lshell setup-system command."""

import contextlib
import grp
import io
import os
import pwd
import stat
import tempfile
import unittest
from unittest.mock import patch

from lshell import systemsetup


class TestSystemSetupFunctional(unittest.TestCase):
    """Exercise setup-system with real filesystem side effects."""

    def _current_user_and_group(self):
        """Return current account names for owner/group CLI flags."""
        username = pwd.getpwuid(os.getuid()).pw_name
        group_name = grp.getgrgid(os.getgid()).gr_name
        return username, group_name

    def test_ensure_shell_entry_is_idempotent_with_override_file(self):
        """Register shell path exactly once when called repeatedly."""
        with tempfile.TemporaryDirectory(prefix="lshell-setup-shells-") as tempdir:
            shells_file = os.path.join(tempdir, "shells")
            shell_path = "/usr/local/bin/lshell"
            with open(shells_file, "w", encoding="utf-8") as handle:
                handle.write("/bin/sh\n")

            with patch.dict(
                os.environ, {"LSHELL_SHELLS_FILE": shells_file}, clear=False
            ):
                systemsetup._ensure_shell_entry(shell_path)
                systemsetup._ensure_shell_entry(shell_path)

            with open(shells_file, "r", encoding="utf-8") as handle:
                entries = [line.strip() for line in handle if line.strip()]

            self.assertEqual(entries.count(shell_path), 1)

    def test_main_integration_creates_log_dir_and_registers_shell(self):
        """Run main flow and verify persisted filesystem effects."""
        with tempfile.TemporaryDirectory(prefix="lshell-setup-main-") as tempdir:
            log_dir = os.path.join(tempdir, "var", "log", "lshell")
            shells_file = os.path.join(tempdir, "shells")
            fake_shell = os.path.join(tempdir, "bin", "lshell")
            os.makedirs(os.path.dirname(fake_shell), exist_ok=True)
            with open(fake_shell, "w", encoding="utf-8") as handle:
                handle.write("#!/bin/sh\nexit 0\n")
            os.chmod(fake_shell, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

            owner, group_name = self._current_user_and_group()
            stdout = io.StringIO()
            stderr = io.StringIO()

            with patch("lshell.systemsetup.os.geteuid", return_value=0):
                with patch("lshell.systemsetup.os.chown"):
                    with patch.dict(
                        os.environ, {"LSHELL_SHELLS_FILE": shells_file}, clear=False
                    ):
                        with contextlib.redirect_stdout(stdout):
                            with contextlib.redirect_stderr(stderr):
                                code = systemsetup.main(
                                    [
                                        "--group",
                                        group_name,
                                        "--owner",
                                        owner,
                                        "--log-dir",
                                        log_dir,
                                        "--shell-path",
                                        fake_shell,
                                        "--mode",
                                        "2770",
                                    ]
                                )

            self.assertEqual(code, 0)
            self.assertTrue(os.path.isdir(log_dir))
            mode = stat.S_IMODE(os.stat(log_dir).st_mode)
            self.assertEqual(mode & 0o770, 0o770)
            self.assertIn("lshell setup complete:", stdout.getvalue())
            self.assertEqual(stderr.getvalue(), "")

            with open(shells_file, "r", encoding="utf-8") as handle:
                shells_entries = [line.strip() for line in handle if line.strip()]
            self.assertIn(os.path.realpath(fake_shell), shells_entries)

    def test_main_integration_skip_shell_registration(self):
        """Skip shell registration should not create the shells file."""
        with tempfile.TemporaryDirectory(prefix="lshell-setup-skip-shells-") as tempdir:
            log_dir = os.path.join(tempdir, "var", "log", "lshell")
            shells_file = os.path.join(tempdir, "shells")
            fake_shell = os.path.join(tempdir, "bin", "lshell")
            os.makedirs(os.path.dirname(fake_shell), exist_ok=True)
            with open(fake_shell, "w", encoding="utf-8") as handle:
                handle.write("#!/bin/sh\nexit 0\n")
            os.chmod(fake_shell, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

            owner, group_name = self._current_user_and_group()
            with patch("lshell.systemsetup.os.geteuid", return_value=0):
                with patch("lshell.systemsetup.os.chown"):
                    with patch.dict(
                        os.environ, {"LSHELL_SHELLS_FILE": shells_file}, clear=False
                    ):
                        code = systemsetup.main(
                            [
                                "--group",
                                group_name,
                                "--owner",
                                owner,
                                "--log-dir",
                                log_dir,
                                "--shell-path",
                                fake_shell,
                                "--skip-shell-registration",
                            ]
                        )

            self.assertEqual(code, 0)
            self.assertFalse(os.path.exists(shells_file))


if __name__ == "__main__":
    unittest.main()
