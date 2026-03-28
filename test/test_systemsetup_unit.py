"""Unit tests for lshell setup-system bootstrap command."""

import contextlib
import io
import unittest
from unittest.mock import patch

from lshell import systemsetup


class TestSystemSetup(unittest.TestCase):
    """Validate setup-system argument and workflow handling."""

    def test_setup_system_returns_error_when_not_root(self):
        """Refuse setup operations when command is not run as root."""
        with patch("lshell.systemsetup.os.geteuid", return_value=1000):
            code = systemsetup.main([])
        self.assertEqual(code, 1)

    def test_setup_system_happy_path(self):
        """Run setup steps in sequence when prerequisites are met."""
        with patch("lshell.systemsetup.os.geteuid", return_value=0):
            with patch("lshell.systemsetup._ensure_group", return_value=444):
                with patch("lshell.systemsetup._resolve_uid", return_value=0):
                    with patch("lshell.systemsetup._ensure_log_directory") as logdir:
                        with patch(
                            "lshell.systemsetup._resolve_lshell_path",
                            return_value="/usr/local/bin/lshell",
                        ):
                            with patch("lshell.systemsetup._ensure_shell_entry") as shell_entry:
                                with patch("lshell.systemsetup._set_user_shell") as set_shell:
                                    with patch(
                                        "lshell.systemsetup._add_user_to_group"
                                    ) as add_group:
                                        code = systemsetup.main(
                                            [
                                                "--set-shell-user",
                                                "testuser",
                                                "--add-group-user",
                                                "testuser",
                                            ]
                                        )

        self.assertEqual(code, 0)
        logdir.assert_called_once_with("/var/log/lshell", 0, 444, 0o2770)
        shell_entry.assert_called_once_with("/usr/local/bin/lshell")
        set_shell.assert_called_once_with("testuser", "/usr/local/bin/lshell")
        add_group.assert_called_once_with("testuser", "lshell")

    def test_setup_system_rejects_invalid_mode(self):
        """Invalid octal mode should fail fast with exit code 1."""
        stderr = io.StringIO()
        with patch("lshell.systemsetup.os.geteuid", return_value=0):
            with contextlib.redirect_stderr(stderr):
                code = systemsetup.main(["--mode", "8888"])

        self.assertEqual(code, 1)
        self.assertIn("Invalid mode value", stderr.getvalue())

    def test_resolve_lshell_path_auto_errors_when_binary_missing(self):
        """Auto shell-path resolution should fail when lshell is not in PATH."""
        with patch("lshell.systemsetup.shutil.which", return_value=None):
            with self.assertRaises(RuntimeError) as exc:
                systemsetup._resolve_lshell_path("auto")
        self.assertIn("binary not found", str(exc.exception))
