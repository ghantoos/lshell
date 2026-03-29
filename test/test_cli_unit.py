"""Unit tests for lshell.cli argument handling."""

import io
import os
import unittest
from types import SimpleNamespace
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

    def test_main_routes_policy_show_subcommand(self):
        """Dispatch policy-show subcommand to diagnostics handler."""
        with patch("lshell.cli.policy_mode.main", return_value=5) as mock_policy_main:
            with patch("lshell.cli.sys.argv", ["lshell", "policy-show", "--user", "alice"]):
                with patch("lshell.cli.sys.exit", side_effect=SystemExit) as mock_exit:
                    with self.assertRaises(SystemExit):
                        cli.main()
        mock_policy_main.assert_called_once_with(["--user", "alice"])
        mock_exit.assert_called_once_with(5)

    def test_main_logs_and_exits_when_session_limit_denied(self):
        """Containment denial at startup should be audited and returned as exit 1."""
        denied = cli.containment.ContainmentViolation(
            reason_code="runtime_limit.max_sessions_per_user_exceeded",
            user_message="lshell: session denied: max_sessions_per_user=1 reached",
            log_message="lshell: runtime containment denied session start",
        )

        class _DummyCheckConfig:
            def __init__(self, _args):
                pass

            def returnconf(self):
                """Return minimal runtime config for startup-path tests."""
                return {"logpath": MagicMock()}

        stderr = io.StringIO()
        with patch("lshell.cli.CheckConfig", _DummyCheckConfig):
            with patch("lshell.cli.ShellCmd", _DummyShell):
                with patch("lshell.cli.sys.argv", ["lshell", "--quiet=1"]):
                    with patch("lshell.cli.sys.stderr", stderr):
                        with patch(
                            "lshell.cli.containment.SessionAccountant"
                        ) as mock_accountant:
                            with patch("lshell.cli.audit.log_security_event") as mock_audit:
                                with patch(
                                    "lshell.cli.sys.exit", side_effect=SystemExit
                                ) as mock_exit:
                                    mock_accountant.return_value.acquire.side_effect = denied
                                    with self.assertRaises(SystemExit):
                                        cli.main()

        userconf = mock_accountant.call_args[0][0]
        userconf["logpath"].critical.assert_called_once_with(denied.log_message)
        self.assertIn(denied.user_message, stderr.getvalue())
        mock_audit.assert_called_once()
        self.assertEqual(
            mock_audit.call_args.kwargs["reason"],
            "runtime_limit.max_sessions_per_user_exceeded",
        )
        mock_exit.assert_called_once_with(1)

    def test_main_retries_after_keyboard_interrupt_then_exits_on_eof(self):
        """Main loop should recover from Ctrl+C outside command handlers."""

        class _InterruptThenEOF:
            calls = 0

            def __init__(self, _userconf, _args):
                pass

            def cmdloop(self):
                """Raise Ctrl+C once, then EOF to terminate retry loop."""
                type(self).calls += 1
                if type(self).calls == 1:
                    raise KeyboardInterrupt
                raise EOFError

        class _DummyCheckConfig:
            def __init__(self, _args):
                pass

            def returnconf(self):
                """Return minimal runtime config for retry-loop tests."""
                return {"logpath": MagicMock()}

        with patch("lshell.cli.CheckConfig", _DummyCheckConfig):
            with patch("lshell.cli.ShellCmd", _InterruptThenEOF):
                with patch("lshell.cli.sys.argv", ["lshell", "--quiet=1"]):
                    with patch(
                        "lshell.cli.sys.exit", side_effect=SystemExit
                    ) as mock_exit:
                        with self.assertRaises(SystemExit):
                            cli.main()

        self.assertEqual(_InterruptThenEOF.calls, 2)
        mock_exit.assert_called_once_with(0)

    def test_main_preserves_existing_session_id_and_releases_accountant(self):
        """Existing LSHELL_SESSION_ID should be reused and accountant released."""
        captured = {}

        class _DummyCheckConfig:
            def __init__(self, _args):
                pass

            def returnconf(self):
                """Return minimal runtime config for session-id tests."""
                return {"logpath": MagicMock()}

        class _EOFShell:
            def __init__(self, userconf, _args):
                captured["session_id"] = userconf["session_id"]

            def cmdloop(self):
                """Terminate main loop via EOF."""
                raise EOFError

        accountant = MagicMock()
        exported_session_id = None
        with patch.dict(os.environ, {"LSHELL_SESSION_ID": "fixed-session"}, clear=False):
            with patch("lshell.cli.CheckConfig", _DummyCheckConfig):
                with patch("lshell.cli.ShellCmd", _EOFShell):
                    with patch(
                        "lshell.cli.containment.SessionAccountant",
                        return_value=accountant,
                        ):
                            with patch("lshell.cli.sys.argv", ["lshell", "--quiet=1"]):
                                with patch("lshell.cli.sys.exit", side_effect=SystemExit):
                                    with self.assertRaises(SystemExit):
                                        cli.main()
                            exported_session_id = os.environ["LSHELL_SESSION_ID"]

        self.assertEqual(captured["session_id"], "fixed-session")
        self.assertEqual(exported_session_id, "fixed-session")
        accountant.acquire.assert_called_once()
        accountant.release.assert_called_once()

    def test_main_generates_session_id_when_missing(self):
        """Missing LSHELL_SESSION_ID should generate and export a new value."""
        captured = {}

        class _DummyCheckConfig:
            def __init__(self, _args):
                pass

            def returnconf(self):
                """Return minimal runtime config for generated session-id tests."""
                return {"logpath": MagicMock()}

        class _EOFShell:
            def __init__(self, userconf, _args):
                captured["session_id"] = userconf["session_id"]

            def cmdloop(self):
                """Terminate main loop via EOF."""
                raise EOFError

        accountant = MagicMock()
        exported_session_id = None
        with patch.dict(os.environ, {}, clear=True):
            with patch("lshell.cli.uuid.uuid4", return_value=SimpleNamespace(hex="generated-id")):
                with patch("lshell.cli.CheckConfig", _DummyCheckConfig):
                    with patch("lshell.cli.ShellCmd", _EOFShell):
                        with patch(
                            "lshell.cli.containment.SessionAccountant",
                            return_value=accountant,
                        ):
                            with patch("lshell.cli.sys.argv", ["lshell", "--quiet=1"]):
                                with patch("lshell.cli.sys.exit", side_effect=SystemExit):
                                    with self.assertRaises(SystemExit):
                                        cli.main()
                            exported_session_id = os.environ["LSHELL_SESSION_ID"]

        self.assertEqual(captured["session_id"], "generated-id")
        self.assertEqual(exported_session_id, "generated-id")
        accountant.release.assert_called_once()

    def test_main_handles_timer_timeout_path(self):
        """LshellTimeOut should log timer expiry and still release accountant."""

        class _DummyCheckConfig:
            def __init__(self, _args):
                pass

            def returnconf(self):
                """Return minimal runtime config for timeout-path tests."""
                return {"logpath": MagicMock()}

        class _TimeoutShell:
            def __init__(self, _userconf, _args):
                pass

            def cmdloop(self):
                """Simulate session timeout raised from shell loop."""
                raise cli.LshellTimeOut()

        accountant = MagicMock()
        stdout = io.StringIO()
        with patch("lshell.cli.CheckConfig", _DummyCheckConfig):
            with patch("lshell.cli.ShellCmd", _TimeoutShell):
                with patch(
                    "lshell.cli.containment.SessionAccountant",
                    return_value=accountant,
                ) as mock_accountant_class:
                    with patch("lshell.cli.sys.argv", ["lshell", "--quiet=1"]):
                        with patch("lshell.cli.sys.stdout", stdout):
                            cli.main()

        accountant.release.assert_called_once()
        userconf = mock_accountant_class.call_args[0][0]
        userconf["logpath"].error.assert_called_once_with("Timer expired")
        self.assertIn("Time is up.", stdout.getvalue())
