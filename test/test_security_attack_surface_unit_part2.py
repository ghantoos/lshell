"""Continuation of attack-surface unit tests.

NOTE FOR MAINTAINERS:
Add all new tests related to `test_security_attack_surface_unit.py` in this file.
`test_security_attack_surface_unit.py` is intentionally kept around ~800 lines.
"""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from lshell.checkconfig import CheckConfig
from lshell import sec
from lshell.shellcmd import ShellCmd
from lshell import utils

TOPDIR = f"{os.path.dirname(os.path.realpath(__file__))}/../"
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"


class DummyLog:
    """Lightweight logger used by parser execution tests."""

    def __init__(self):
        self.messages = []

    def warn(self, message):
        """Record warning-level messages."""
        self.messages.append(("warn", message))

    def info(self, message):
        """Record info-level messages."""
        self.messages.append(("info", message))

    def critical(self, message):
        """Record critical-level messages."""
        self.messages.append(("critical", message))

    def error(self, message):
        """Record error-level messages."""
        self.messages.append(("error", message))


class DummyShellContext:
    """Minimal shell context consumed by utils.cmd_parse_execute."""

    def __init__(self, conf):
        self.conf = conf
        self.log = DummyLog()


class DummySSHWarnContext:
    """Minimal object supporting ShellCmd.ssh_warn."""

    def __init__(self, conf):
        self.conf = conf
        self.log = DummyLog()


class TestAttackSurfacePart2(unittest.TestCase):
    """Continuation tests for parser/auth attack-surface scenarios."""

    args = [f"--config={CONFIG}", "--quiet=1"]

    @patch("lshell.utils.os.killpg")
    @patch("lshell.utils.os.kill")
    @patch("lshell.utils.signal.getsignal", return_value=None)
    @patch("lshell.utils.signal.signal")
    @patch("lshell.utils.subprocess.Popen")
    def test_exec_cmd_keyboard_interrupt_sudo_signals_pid_not_process_group(
        self,
        mock_popen,
        _mock_signal,
        _mock_getsignal,
        mock_kill,
        mock_killpg,
    ):
        """On Ctrl+C, sudo command should receive SIGINT directly by PID."""

        class FakeProc:
            """Simulate a running foreground process interrupted by Ctrl+C."""

            def __init__(self):
                self.returncode = None
                self.pid = 4242
                self.args = ["sudo", "ls"]
                self.lshell_cmd = ""

            def communicate(self):
                """Raise keyboard interrupt while waiting for process I/O."""
                raise KeyboardInterrupt

            def poll(self):
                """Report process still running to trigger signal handling."""
                return None

        mock_popen.return_value = FakeProc()

        ret = utils.exec_cmd("sudo ls")

        self.assertEqual(ret, 130)
        mock_kill.assert_called_once_with(4242, utils.signal.SIGINT)
        mock_killpg.assert_not_called()

    @patch("lshell.utils.os.getpgid", return_value=7777)
    @patch("lshell.utils.os.killpg")
    @patch("lshell.utils.os.kill")
    @patch("lshell.utils.signal.getsignal", return_value=None)
    @patch("lshell.utils.signal.signal")
    @patch("lshell.utils.subprocess.Popen")
    def test_exec_cmd_keyboard_interrupt_non_sudo_signals_process_group(
        self,
        mock_popen,
        _mock_signal,
        _mock_getsignal,
        _mock_kill,
        mock_killpg,
        _mock_getpgid,
    ):
        """On Ctrl+C, regular commands should receive SIGINT at process-group level."""

        class FakeProc:
            """Simulate a detached foreground process interrupted by Ctrl+C."""

            def __init__(self):
                self.returncode = None
                self.pid = 5252
                self.args = ["bash", "-c", "sleep 60"]
                self.lshell_cmd = ""

            def communicate(self):
                """Raise keyboard interrupt while waiting for process I/O."""
                raise KeyboardInterrupt

            def poll(self):
                """Report process still running to trigger signal handling."""
                return None

        mock_popen.return_value = FakeProc()

        ret = utils.exec_cmd("sleep 60")

        self.assertEqual(ret, 130)
        mock_killpg.assert_called_once_with(7777, utils.signal.SIGINT)

    def test_cmd_parse_execute_should_block_forbidden_env_assignment_via_assignment_only(
        self,
    ):
        """Security expectation: assignment-only should not bypass env blacklist."""
        conf = CheckConfig(self.args + ["--forbidden=[]", "--strict=0"]).returnconf()
        shell = DummyShellContext(conf)
        original = os.environ.get("LD_PRELOAD")
        try:
            ret = utils.cmd_parse_execute(
                "LD_PRELOAD=/tmp/evil.so", shell_context=shell
            )
            self.assertNotEqual(
                ret,
                0,
                msg="assignment-only LD_PRELOAD should be rejected in hardened behavior",
            )
            self.assertNotEqual(os.environ.get("LD_PRELOAD"), "/tmp/evil.so")
        finally:
            if original is None:
                os.environ.pop("LD_PRELOAD", None)
            else:
                os.environ["LD_PRELOAD"] = original

    @patch("lshell.utils.sec.check_forbidden_chars")
    @patch("lshell.utils.exec_cmd")
    def test_cmd_parse_execute_forbidden_chars_short_circuits_execution(
        self, mock_exec, mock_forbidden
    ):
        """Stop execution immediately when forbidden-char checks fail."""
        conf = CheckConfig(self.args + ["--strict=0"]).returnconf()
        shell = DummyShellContext(conf)
        mock_forbidden.side_effect = lambda line, conf, strict=None: (1, conf)
        ret = utils.cmd_parse_execute("echo should_not_run", shell_context=shell)
        self.assertEqual(ret, 126)
        mock_exec.assert_not_called()

    @patch("lshell.utils.exec_cmd", return_value=0)
    def test_cmd_parse_execute_allows_full_bash_script_command_for_login_script(
        self, mock_exec
    ):
        """Authorize and execute bash script invocation when full command is allowlisted."""
        conf = CheckConfig(
            self.args
            + [
                "--allowed=['bash test/testfiles/login_script.sh']",
                "--forbidden=[]",
                "--strict=0",
            ]
        ).returnconf()
        shell = DummyShellContext(conf)

        ret = utils.cmd_parse_execute(
            "bash test/testfiles/login_script.sh", shell_context=shell
        )

        self.assertEqual(ret, 0)
        self.assertEqual(mock_exec.call_count, 1)
        self.assertEqual(
            mock_exec.call_args.args[0], "bash test/testfiles/login_script.sh"
        )

    @patch("lshell.utils.exec_cmd")
    def test_cmd_parse_execute_trusted_protocol_blocks_non_protocol_chained_command(
        self, mock_exec
    ):
        """Trusted SSH protocol mode must reject non-protocol chained commands."""
        conf = CheckConfig(self.args + ["--strict=0"]).returnconf()
        shell = DummyShellContext(conf)

        ret = utils.cmd_parse_execute(
            "sftp-server || id",
            shell_context=shell,
            trusted_protocol=True,
        )

        self.assertEqual(ret, 126)
        mock_exec.assert_not_called()

    @patch("lshell.utils.exec_cmd", return_value=0)
    def test_cmd_parse_execute_trusted_protocol_allows_single_sftp_server_command(
        self, mock_exec
    ):
        """Trusted SSH protocol mode should execute a single sftp-server command."""
        conf = CheckConfig(self.args + ["--strict=0"]).returnconf()
        shell = DummyShellContext(conf)

        ret = utils.cmd_parse_execute(
            "/usr/libexec/sftp-server",
            shell_context=shell,
            trusted_protocol=True,
        )

        self.assertEqual(ret, 0)
        mock_exec.assert_called_once_with(
            "/usr/libexec/sftp-server",
            background=False,
            extra_env=unittest.mock.ANY,
        )

    @patch("lshell.utils.exec_cmd", side_effect=[1, 0])
    def test_cmd_parse_execute_trusted_protocol_allows_chained_sftp_server_commands(
        self, mock_exec
    ):
        """Trusted SSH protocol mode should allow chained sftp-server commands."""
        conf = CheckConfig(self.args + ["--strict=0"]).returnconf()
        shell = DummyShellContext(conf)

        ret = utils.cmd_parse_execute(
            "sftp-server || /usr/libexec/sftp-server",
            shell_context=shell,
            trusted_protocol=True,
        )

        self.assertEqual(ret, 0)
        self.assertEqual(mock_exec.call_count, 2)
        self.assertEqual(mock_exec.call_args_list[0].args[0], "sftp-server")
        self.assertEqual(mock_exec.call_args_list[1].args[0], "/usr/libexec/sftp-server")

    def test_check_allowed_file_extensions_allows_existing_directory_target(self):
        """Directory targets should not fail extension checks (e.g. SCP -t <dir>)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            allowed, blocked = sec.check_allowed_file_extensions(
                f"scp -t {tmpdir}", [".txt"]
            )
        self.assertTrue(allowed)
        self.assertIsNone(blocked)

    def test_config_rejects_message_override_with_unknown_placeholder(self):
        """Fail closed when a custom message references unsupported placeholders."""
        with self.assertRaises(SystemExit):
            CheckConfig(
                self.args
                + ["--messages={'warning_remaining': 'warning {unknown_placeholder}'}"]
            ).returnconf()

    def test_warn_count_uses_custom_warning_message_template(self):
        """Allow warning text customization through the messages config dict."""
        conf = CheckConfig(
            self.args
            + [
                "--strict=0",
                (
                    "--messages={'warning_remaining': "
                    "'*** You have {remaining} warning(s) left, before getting kicked out.'}"
                ),
            ]
        ).returnconf()

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            ret, updated_conf = sec.warn_count("command", "id", conf)

        self.assertEqual(ret, 1)
        self.assertEqual(updated_conf["warning_counter"], 1)
        self.assertEqual(
            stderr.getvalue(),
            "*** You have 1 warning(s) left, before getting kicked out.\n",
        )

    def test_ssh_warn_uses_custom_incident_message_template(self):
        """Allow SSH incident text customization through the messages config dict."""
        conf = CheckConfig(
            self.args + ["--messages={'incident_reported': 'Custom incident message.'}"]
        ).returnconf()
        context = DummySSHWarnContext(conf)
        stderr = io.StringIO()

        with self.assertRaises(SystemExit) as cm:
            with redirect_stderr(stderr):
                ShellCmd.ssh_warn(context, "command over SSH", "id")

        self.assertEqual(cm.exception.code, 1)
        self.assertEqual(stderr.getvalue(), "Custom incident message.\n")
        self.assertIn(
            ("critical", 'lshell: forbidden command over SSH: "id"'),
            context.log.messages,
        )


if __name__ == "__main__":
    unittest.main()
