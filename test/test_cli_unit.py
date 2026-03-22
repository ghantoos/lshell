"""Unit tests for lshell.cli argument handling."""

import os
import unittest
from unittest.mock import MagicMock, patch

from lshell import cli


class _DummyShell:
    """Minimal shell stub that exits loop immediately."""

    def __init__(self, _userconf, _args):
        pass

    def cmdloop(self):
        """Terminate the loop immediately via EOF handling."""
        raise EOFError


class TestCliArgs(unittest.TestCase):
    """Validate CLI argument parsing from environment variables."""

    def _run_main_and_capture_args(self, env_value):
        captured = {}

        class _DummyCheckConfig:
            def __init__(self, args):
                captured["args"] = args

            def returnconf(self):
                """Return the minimal config expected by cli.main()."""
                return {"logpath": MagicMock()}

        env_patch = {}
        if env_value is not None:
            env_patch["LSHELL_ARGS"] = env_value

        with patch.dict(os.environ, env_patch, clear=False):
            with patch("lshell.cli.CheckConfig", _DummyCheckConfig):
                with patch("lshell.cli.ShellCmd", _DummyShell):
                    with patch("lshell.cli.sys.argv", ["lshell", "--quiet=1"]):
                        with patch("lshell.cli.sys.exit", side_effect=SystemExit):
                            with self.assertRaises(SystemExit):
                                cli.main()

        return captured["args"]

    def test_main_appends_valid_lshell_args_from_env(self):
        """Append safely parsed list arguments from LSHELL_ARGS env var."""
        args = self._run_main_and_capture_args("['--config', '/tmp/lshell.conf']")
        self.assertEqual(args, ["--quiet=1", "--config", "/tmp/lshell.conf"])

    def test_main_ignores_invalid_or_unsafe_lshell_args_env(self):
        """Ignore malformed, non-sequence, or non-string entries in LSHELL_ARGS."""
        invalid_values = [
            "__import__('os').system('id')",
            "'--config'",
            "['--config', 123]",
        ]
        for value in invalid_values:
            with self.subTest(value=value):
                args = self._run_main_and_capture_args(value)
                self.assertEqual(args, ["--quiet=1"])

    def test_main_routes_setup_system_subcommand(self):
        """Dispatch setup-system subcommand to dedicated handler."""
        with patch("lshell.cli.system_setup.main", return_value=7) as mock_setup_main:
            with patch("lshell.cli.sys.argv", ["lshell", "setup-system", "--group", "ops"]):
                with patch("lshell.cli.sys.exit", side_effect=SystemExit) as mock_exit:
                    with self.assertRaises(SystemExit):
                        cli.main()
        mock_setup_main.assert_called_once_with(["--group", "ops"])
        mock_exit.assert_called_once_with(7)

    def test_main_routes_harden_init_subcommand(self):
        """Dispatch harden-init subcommand to dedicated handler."""
        with patch("lshell.cli.harden_init.main", return_value=3) as mock_harden_main:
            with patch("lshell.cli.sys.argv", ["lshell", "harden-init", "--list-templates"]):
                with patch("lshell.cli.sys.exit", side_effect=SystemExit) as mock_exit:
                    with self.assertRaises(SystemExit):
                        cli.main()
        mock_harden_main.assert_called_once_with(["--list-templates"])
        mock_exit.assert_called_once_with(3)
