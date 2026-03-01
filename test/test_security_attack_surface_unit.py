"""Security-focused unit tests for parser/auth edge cases."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from lshell.checkconfig import CheckConfig
from lshell.shellcmd import ShellCmd
from lshell import sec
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


class DummyShellContext:
    """Minimal shell context consumed by utils.cmd_parse_execute."""

    def __init__(self, conf):
        self.conf = conf
        self.log = DummyLog()

    def do_help(self, _arg):
        """Emulate a successful help command."""
        return 0

    def do_exit(self, _arg=None):
        """Emulate a successful exit command."""
        return 0


class TestAttackSurface(unittest.TestCase):
    """Tests aimed at command-injection/bypass style edge cases."""

    args = [f"--config={CONFIG}", "--quiet=1"]

    def _without_ssh_env(self):
        saved = {}
        for key in ("SSH_CLIENT", "SSH_TTY", "SSH_ORIGINAL_COMMAND"):
            saved[key] = os.environ.get(key)
            os.environ.pop(key, None)
        return saved

    def _restore_ssh_env(self, saved):
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _with_forced_ssh_env(self):
        saved = {}
        for key in ("SSH_CLIENT", "SSH_TTY", "SSH_ORIGINAL_COMMAND"):
            saved[key] = os.environ.get(key)
        os.environ["SSH_CLIENT"] = "127.0.0.1 22 22"
        os.environ.pop("SSH_TTY", None)
        return saved

    def test_split_command_sequence_does_not_split_escaped_pipe(self):
        """Treat escaped pipes as literal text in a command token."""
        line = r"echo a\|b | wc -c"
        self.assertEqual(utils.split_command_sequence(line), [r"echo a\|b", "|", "wc -c"])

    def test_split_command_sequence_allows_trailing_background(self):
        """Allow a trailing background operator as a separate token."""
        self.assertEqual(utils.split_command_sequence("sleep 1 &"), ["sleep 1", "&"])

    def test_split_command_sequence_rejects_operator_smuggling(self):
        """Reject malformed operator chains that should fail closed."""
        self.assertIsNone(utils.split_command_sequence("echo ok ||| echo pwn"))

    def test_check_forbidden_chars_allows_double_ampersand_when_single_forbidden(self):
        """Permit && when only single & is forbidden by policy."""
        conf = CheckConfig(self.args + ["--forbidden=['&']", "--strict=0"]).returnconf()
        ret, _conf = sec.check_forbidden_chars("echo ok && echo still_ok", conf)
        self.assertEqual(ret, 0)

    def test_check_forbidden_chars_blocks_single_ampersand(self):
        """Block single & when forbidden characters include ampersand."""
        conf = CheckConfig(self.args + ["--forbidden=['&']", "--strict=0"]).returnconf()
        starting_counter = conf["warning_counter"]
        ret, _conf = sec.check_forbidden_chars("echo ok &", conf)
        self.assertEqual(ret, 1)
        self.assertEqual(_conf["warning_counter"], starting_counter - 1)

    def test_check_path_forbidden_decrements_counter_even_when_not_strict(self):
        """Forbidden path should consume warning counter regardless of strict mode."""
        conf = CheckConfig(
            self.args + ["--path=['/home', '/var']", "--strict=0"]
        ).returnconf()
        starting_counter = conf["warning_counter"]
        ret, _conf = sec.check_path("cd /tmp", conf, strict=0)
        self.assertEqual(ret, 1)
        self.assertEqual(_conf["warning_counter"], starting_counter - 1)

    def test_checkconfig_rejects_allowed_shell_escape_all(self):
        """Reject allowed_shell_escape=all to avoid bypassing noexec globally."""
        with self.assertRaises(SystemExit):
            CheckConfig(self.args + ["--allowed_shell_escape='all'"]).returnconf()

    def test_shell_escape_c_runs_allowed_command_when_not_over_ssh(self):
        """Allow local -c shell escape for commands already authorized by policy."""
        saved_env = self._without_ssh_env()
        try:
            conf = CheckConfig(self.args + ["--allowed=['ls']", "--strict=0"]).returnconf()
            conf["ssh"] = "ls"
            with patch("lshell.shellcmd.utils.cmd_parse_execute", return_value=0) as mock_exec:
                with self.assertRaises(SystemExit) as cm:
                    ShellCmd(
                        conf,
                        args=[],
                        stdin=io.StringIO(),
                        stdout=io.StringIO(),
                        stderr=io.StringIO(),
                    )
            self.assertEqual(cm.exception.code, 0)
            mock_exec.assert_called_once_with("ls", shell_context=unittest.mock.ANY)
        finally:
            self._restore_ssh_env(saved_env)

    def test_shell_escape_c_blocks_disallowed_command_when_not_over_ssh(self):
        """Block local -c shell escape when the command is not in allowed policy."""
        saved_env = self._without_ssh_env()
        try:
            conf = CheckConfig(self.args + ["--allowed=['ls']", "--strict=0"]).returnconf()
            conf["ssh"] = "tail /etc/passwd"
            with patch("lshell.shellcmd.utils.cmd_parse_execute") as mock_exec:
                with self.assertRaises(SystemExit) as cm:
                    ShellCmd(
                        conf,
                        args=[],
                        stdin=io.StringIO(),
                        stdout=io.StringIO(),
                        stderr=io.StringIO(),
                    )
            self.assertEqual(cm.exception.code, 1)
            mock_exec.assert_not_called()
        finally:
            self._restore_ssh_env(saved_env)

    def test_run_overssh_allows_command_present_in_overssh(self):
        """Execute forced SSH command when it is explicitly in overssh list."""
        saved_env = self._with_forced_ssh_env()
        try:
            conf = CheckConfig(
                self.args + ["--allowed=['echo']", "--overssh=['ls']", "--strict=0"]
            ).returnconf()
            conf["ssh"] = "ls"
            with patch("lshell.shellcmd.utils.cmd_parse_execute", return_value=0) as mock_exec:
                with self.assertRaises(SystemExit) as cm:
                    ShellCmd(
                        conf,
                        args=[],
                        stdin=io.StringIO(),
                        stdout=io.StringIO(),
                        stderr=io.StringIO(),
                    )
            self.assertEqual(cm.exception.code, 0)
            mock_exec.assert_called_once_with("ls", shell_context=unittest.mock.ANY)
        finally:
            self._restore_ssh_env(saved_env)

    def test_run_overssh_rejects_command_not_in_overssh(self):
        """Deny forced SSH command even when it is present in normal allowed list."""
        saved_env = self._with_forced_ssh_env()
        try:
            conf = CheckConfig(
                self.args + ["--allowed=['ls']", "--overssh=['echo']", "--strict=0"]
            ).returnconf()
            conf["ssh"] = "ls"
            with patch("lshell.shellcmd.utils.cmd_parse_execute") as mock_exec:
                with self.assertRaises(SystemExit) as cm:
                    ShellCmd(
                        conf,
                        args=[],
                        stdin=io.StringIO(),
                        stdout=io.StringIO(),
                        stderr=io.StringIO(),
                    )
            self.assertEqual(cm.exception.code, 1)
            mock_exec.assert_not_called()
        finally:
            self._restore_ssh_env(saved_env)

    def test_run_overssh_rejects_forbidden_chars(self):
        """Deny forced SSH command containing forbidden separators."""
        saved_env = self._with_forced_ssh_env()
        try:
            conf = CheckConfig(
                self.args + ["--allowed=['ls']", "--overssh=['ls']", "--strict=0"]
            ).returnconf()
            conf["ssh"] = "ls; echo pwned"
            with patch("lshell.shellcmd.utils.cmd_parse_execute") as mock_exec:
                with self.assertRaises(SystemExit) as cm:
                    ShellCmd(
                        conf,
                        args=[],
                        stdin=io.StringIO(),
                        stdout=io.StringIO(),
                        stderr=io.StringIO(),
                    )
            self.assertEqual(cm.exception.code, 1)
            mock_exec.assert_not_called()
        finally:
            self._restore_ssh_env(saved_env)

    def test_run_overssh_rejects_sftp_when_disabled(self):
        """Deny sftp-server sessions when sftp flag is disabled."""
        saved_env = self._with_forced_ssh_env()
        try:
            conf = CheckConfig(self.args + ["--sftp=0", "--strict=0"]).returnconf()
            conf["ssh"] = "/usr/libexec/sftp-server"
            with patch("lshell.shellcmd.utils.cmd_parse_execute") as mock_exec:
                with self.assertRaises(SystemExit) as cm:
                    ShellCmd(
                        conf,
                        args=[],
                        stdin=io.StringIO(),
                        stdout=io.StringIO(),
                        stderr=io.StringIO(),
                    )
            self.assertEqual(cm.exception.code, 1)
            mock_exec.assert_not_called()
        finally:
            self._restore_ssh_env(saved_env)

    def test_run_overssh_allows_sftp_when_enabled(self):
        """Execute sftp-server sessions when sftp flag is enabled."""
        saved_env = self._with_forced_ssh_env()
        try:
            conf = CheckConfig(self.args + ["--sftp=1", "--strict=0"]).returnconf()
            conf["ssh"] = "/usr/libexec/sftp-server"
            with patch("lshell.shellcmd.utils.cmd_parse_execute", return_value=0) as mock_exec:
                with self.assertRaises(SystemExit) as cm:
                    ShellCmd(
                        conf,
                        args=[],
                        stdin=io.StringIO(),
                        stdout=io.StringIO(),
                        stderr=io.StringIO(),
                    )
            self.assertEqual(cm.exception.code, 0)
            mock_exec.assert_called_once_with(
                "/usr/libexec/sftp-server", shell_context=unittest.mock.ANY
            )
        finally:
            self._restore_ssh_env(saved_env)

    def test_run_overssh_rejects_scp_when_disabled_and_not_in_overssh(self):
        """Deny scp transfer when global scp flag is disabled."""
        saved_env = self._with_forced_ssh_env()
        try:
            conf = CheckConfig(
                self.args + ["--scp=0", "--overssh=[]", "--strict=0"]
            ).returnconf()
            conf["ssh"] = f"scp -f {conf['home_path']}/artifact"
            with patch("lshell.shellcmd.utils.cmd_parse_execute") as mock_exec:
                with self.assertRaises(SystemExit) as cm:
                    ShellCmd(
                        conf,
                        args=[],
                        stdin=io.StringIO(),
                        stdout=io.StringIO(),
                        stderr=io.StringIO(),
                    )
            self.assertEqual(cm.exception.code, 1)
            mock_exec.assert_not_called()
        finally:
            self._restore_ssh_env(saved_env)

    def test_run_overssh_allows_scp_from_overssh_even_if_scp_flag_disabled(self):
        """Allow scp transfer when scp is present in overssh allowlist."""
        saved_env = self._with_forced_ssh_env()
        try:
            conf = CheckConfig(
                self.args
                + ["--scp=0", "--overssh=['scp']", "--scp_download=1", "--strict=0"]
            ).returnconf()
            conf["ssh"] = f"scp -f {conf['home_path']}/artifact"
            with patch("lshell.shellcmd.utils.cmd_parse_execute", return_value=0) as mock_exec:
                with self.assertRaises(SystemExit) as cm:
                    ShellCmd(
                        conf,
                        args=[],
                        stdin=io.StringIO(),
                        stdout=io.StringIO(),
                        stderr=io.StringIO(),
                    )
            self.assertEqual(cm.exception.code, 0)
            mock_exec.assert_called_once_with(
                f"scp -f {conf['home_path']}/artifact", shell_context=unittest.mock.ANY
            )
        finally:
            self._restore_ssh_env(saved_env)

    def test_run_overssh_rejects_scp_download_when_scp_download_disabled(self):
        """Deny scp -f when scp_download flag is disabled."""
        saved_env = self._with_forced_ssh_env()
        try:
            conf = CheckConfig(
                self.args + ["--scp=1", "--scp_download=0", "--strict=0"]
            ).returnconf()
            conf["ssh"] = f"scp -f {conf['home_path']}/artifact"
            with patch("lshell.shellcmd.utils.cmd_parse_execute") as mock_exec:
                with self.assertRaises(SystemExit) as cm:
                    ShellCmd(
                        conf,
                        args=[],
                        stdin=io.StringIO(),
                        stdout=io.StringIO(),
                        stderr=io.StringIO(),
                    )
            self.assertEqual(cm.exception.code, 1)
            mock_exec.assert_not_called()
        finally:
            self._restore_ssh_env(saved_env)

    def test_run_overssh_rejects_scp_upload_when_scp_upload_disabled(self):
        """Deny scp -t when scp_upload flag is disabled."""
        saved_env = self._with_forced_ssh_env()
        try:
            conf = CheckConfig(
                self.args + ["--scp=1", "--scp_upload=0", "--strict=0"]
            ).returnconf()
            conf["ssh"] = f"scp -t {conf['home_path']}"
            with patch("lshell.shellcmd.utils.cmd_parse_execute") as mock_exec:
                with self.assertRaises(SystemExit) as cm:
                    ShellCmd(
                        conf,
                        args=[],
                        stdin=io.StringIO(),
                        stdout=io.StringIO(),
                        stderr=io.StringIO(),
                    )
            self.assertEqual(cm.exception.code, 1)
            mock_exec.assert_not_called()
        finally:
            self._restore_ssh_env(saved_env)

    def test_run_overssh_applies_scpforce_to_upload_target(self):
        """Rewrite scp -t target path to configured scpforce directory."""
        saved_env = self._with_forced_ssh_env()
        try:
            with tempfile.TemporaryDirectory(prefix="lshell_scpforce_") as forced_dir:
                conf = CheckConfig(
                    self.args
                    + [
                        "--scp=1",
                        "--scp_upload=1",
                        f"--scpforce='{forced_dir}'",
                        "--strict=0",
                    ]
                ).returnconf()
                conf["ssh"] = f"scp -t {conf['home_path']}"
                with patch("lshell.shellcmd.utils.cmd_parse_execute", return_value=0) as mock_exec:
                    with self.assertRaises(SystemExit) as cm:
                        ShellCmd(
                            conf,
                            args=[],
                            stdin=io.StringIO(),
                            stdout=io.StringIO(),
                            stderr=io.StringIO(),
                        )
                self.assertEqual(cm.exception.code, 0)
                mock_exec.assert_called_once_with(
                    f"scp -t {os.path.realpath(forced_dir)}",
                    shell_context=unittest.mock.ANY,
                )
        finally:
            self._restore_ssh_env(saved_env)

    def test_cmdloop_executes_login_script_with_bash_script_invocation(self):
        """Run configured login_script at shell startup, including 'bash <script>' syntax."""
        conf = CheckConfig(self.args + ["--strict=0"]).returnconf()
        conf["login_script"] = "bash test/testfiles/login_script.sh"
        shell = ShellCmd(
            conf,
            args=[],
            stdin=io.StringIO(),
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        shell.cmdqueue = ["exit"]

        with patch("lshell.shellcmd.utils.cmd_parse_execute", return_value=0) as mock_exec:
            with patch("lshell.shellcmd.sys.exit", side_effect=SystemExit):
                with self.assertRaises(SystemExit):
                    shell.cmdloop()

        mock_exec.assert_called_once_with(
            "bash test/testfiles/login_script.sh", shell_context=shell
        )

    def test_check_secure_assignment_prefix_keeps_exact_command_matching(self):
        """Enforce command allowlist even when prefixed by variable assignments."""
        conf = CheckConfig(
            self.args + ["--allowed=['echo ok']", "--forbidden=[]", "--strict=0"]
        ).returnconf()
        self.assertEqual(sec.check_secure("A=1 echo ok", conf)[0], 0)
        self.assertEqual(sec.check_secure("A=1 echo nope", conf)[0], 1)

    def test_check_secure_unknown_command_does_not_decrement_counter_when_not_strict(self):
        """Treat disallowed commands as unknown syntax when strict mode is disabled."""
        conf = CheckConfig(
            self.args
            + ["--allowed=['echo']", "--forbidden=[]", "--strict=0", "--quiet=0"]
        ).returnconf()
        starting_counter = conf["warning_counter"]
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            ret, conf = sec.check_secure("no_such_allowed_command", conf, strict=0)
        self.assertEqual(ret, 1)
        self.assertEqual(conf["warning_counter"], starting_counter)
        self.assertIn("lshell: unknown syntax: no_such_allowed_command", stderr.getvalue())

    def test_check_secure_unknown_command_decrements_counter_when_strict(self):
        """Count disallowed commands as forbidden actions when strict mode is enabled."""
        conf = CheckConfig(
            self.args
            + ["--allowed=['echo']", "--forbidden=[]", "--strict=1", "--quiet=0"]
        ).returnconf()
        starting_counter = conf["warning_counter"]
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            ret, conf = sec.check_secure("no_such_allowed_command", conf, strict=1)
        self.assertEqual(ret, 1)
        self.assertEqual(conf["warning_counter"], starting_counter - 1)
        self.assertIn("lshell: warning:", stderr.getvalue())

    def test_check_secure_assignment_prefix_with_sudo_still_checks_subcommand(self):
        """Validate sudo subcommands after assignment prefixes."""
        conf = CheckConfig(
            self.args
            + ["--allowed=['sudo']", "--sudo_commands=['ls']", "--forbidden=[]", "--strict=0"]
        ).returnconf()
        self.assertEqual(sec.check_secure("A=1 sudo ls", conf)[0], 0)
        self.assertEqual(sec.check_secure("A=1 sudo cat /etc/passwd", conf)[0], 1)

    def test_check_secure_sudo_u_with_assignment_prefix_is_authorized(self):
        """Allow authorized sudo -u command with an assignment prefix."""
        conf = CheckConfig(
            self.args
            + ["--allowed=['sudo']", "--sudo_commands=['ls']", "--forbidden=[]", "--strict=0"]
        ).returnconf()
        self.assertEqual(sec.check_secure("A=1 sudo -u root ls", conf)[0], 0)

    def test_check_secure_sudo_u_missing_command_fails_closed(self):
        """Reject sudo -u when no subcommand is provided."""
        conf = CheckConfig(
            self.args
            + ["--allowed=['sudo']", "--sudo_commands=['ls']", "--forbidden=[]", "--strict=0"]
        ).returnconf()
        self.assertEqual(sec.check_secure("sudo -u root", conf)[0], 1)

    def test_check_secure_rejects_control_char_in_line(self):
        """Reject control characters embedded in command input."""
        conf = CheckConfig(self.args + ["--strict=0"]).returnconf()
        # Literal vertical-tab control char.
        self.assertEqual(sec.check_secure("echo\x0btest", conf)[0], 1)

    def test_check_secure_rejects_disallowed_command_substitution(self):
        """Reject substitution constructs that invoke disallowed commands."""
        conf = CheckConfig(
            self.args + ["--allowed=['echo']", "--forbidden=[';','&','|','>','<']", "--strict=0"]
        ).returnconf()
        self.assertEqual(sec.check_secure("echo $(cat /etc/passwd)", conf)[0], 1)
        self.assertEqual(sec.check_secure("echo `cat /etc/passwd`", conf)[0], 1)

    def test_cmd_parse_execute_rejects_unbalanced_syntax(self):
        """Return an error when parser input has unbalanced syntax."""
        conf = CheckConfig(self.args + ["--strict=0"]).returnconf()
        shell = DummyShellContext(conf)
        starting_counter = conf["warning_counter"]
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            ret = utils.cmd_parse_execute('echo "oops', shell_context=shell)
        self.assertEqual(ret, 1)
        self.assertEqual(conf["warning_counter"], starting_counter)
        self.assertIn("lshell: unknown syntax:", stderr.getvalue())

    def test_cmd_parse_execute_unbalanced_syntax_decrements_counter_in_strict_mode(self):
        """In strict mode, unknown syntax should consume warning counter."""
        conf = CheckConfig(self.args + ["--strict=1", "--quiet=0"]).returnconf()
        shell = DummyShellContext(conf)
        starting_counter = conf["warning_counter"]
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            ret = utils.cmd_parse_execute('echo "oops', shell_context=shell)
        self.assertEqual(ret, 126)
        self.assertEqual(conf["warning_counter"], starting_counter - 1)
        self.assertIn("lshell: warning:", stderr.getvalue())

    def test_cmd_parse_execute_malformed_operator_decrements_counter_in_strict_mode(self):
        """In strict mode, malformed operators should consume warning counter."""
        conf = CheckConfig(self.args + ["--strict=1", "--quiet=0"]).returnconf()
        shell = DummyShellContext(conf)
        starting_counter = conf["warning_counter"]
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            ret = utils.cmd_parse_execute("echo ok ||| echo pwn", shell_context=shell)
        self.assertEqual(ret, 126)
        self.assertEqual(conf["warning_counter"], starting_counter - 1)
        self.assertIn("lshell: warning:", stderr.getvalue())

    @patch("lshell.utils.sec.check_forbidden_chars")
    @patch("lshell.utils.sec.check_secure")
    @patch("lshell.utils.sec.check_path")
    @patch("lshell.utils.exec_cmd")
    def test_cmd_parse_execute_short_circuit_skips_failed_and_branch(
        self, mock_exec, mock_path, mock_secure, mock_forbidden
    ):
        """Skip right-hand commands after failed && and execute || recovery."""
        conf = CheckConfig(
            self.args
            + [
                "--allowed=['false','skip1','skip2','echo']",
                "--forbidden=[]",
                "--strict=0",
            ]
        ).returnconf()
        shell = DummyShellContext(conf)

        mock_forbidden.side_effect = lambda line, conf, strict=None: (0, conf)
        mock_secure.side_effect = lambda line, conf, strict=None: (0, conf)
        mock_path.side_effect = lambda line, conf, strict=None: (0, conf)

        def exec_side_effect(command, background=False, extra_env=None):
            if command == "false":
                return 1
            if command == "echo recovered":
                return 0
            return 99

        mock_exec.side_effect = exec_side_effect

        ret = utils.cmd_parse_execute(
            "false && skip1 | skip2 || echo recovered", shell_context=shell
        )

        self.assertEqual(ret, 0)
        executed = [call.args[0] for call in mock_exec.call_args_list]
        self.assertEqual(executed, ["false", "echo recovered"])

    @patch("lshell.utils.sec.check_forbidden_chars")
    @patch("lshell.utils.sec.check_secure")
    @patch("lshell.utils.sec.check_path")
    @patch("lshell.utils.exec_cmd")
    def test_cmd_parse_execute_assignment_only_updates_parent_env_without_exec(
        self, mock_exec, mock_path, mock_secure, mock_forbidden
    ):
        """Apply assignment-only input to parent env without spawning a command."""
        conf = CheckConfig(self.args + ["--forbidden=[]", "--strict=0"]).returnconf()
        shell = DummyShellContext(conf)

        mock_forbidden.side_effect = lambda line, conf, strict=None: (0, conf)
        mock_secure.side_effect = lambda line, conf, strict=None: (0, conf)
        mock_path.side_effect = lambda line, conf, strict=None: (0, conf)

        original = os.environ.get("LSHELL_ATTACK_SURFACE")
        try:
            ret = utils.cmd_parse_execute(
                "LSHELL_ATTACK_SURFACE=present", shell_context=shell
            )
            self.assertEqual(ret, 0)
            self.assertEqual(os.environ.get("LSHELL_ATTACK_SURFACE"), "present")
            mock_exec.assert_not_called()
        finally:
            if original is None:
                os.environ.pop("LSHELL_ATTACK_SURFACE", None)
            else:
                os.environ["LSHELL_ATTACK_SURFACE"] = original

    @patch("lshell.utils.sec.check_forbidden_chars")
    @patch("lshell.utils.sec.check_secure")
    @patch("lshell.utils.sec.check_path")
    @patch("lshell.utils.exec_cmd")
    def test_cmd_parse_execute_allowed_shell_escape_skips_ld_preload(
        self, mock_exec, mock_path, mock_secure, mock_forbidden
    ):
        """allowed_shell_escape commands should execute without LD_PRELOAD wrapping."""
        conf = CheckConfig(
            self.args
            + [
                "--allowed=['sudo']",
                "--sudo_commands=['ls']",
                "--allowed_shell_escape=['sudo']",
                "--forbidden=[]",
                "--strict=0",
            ]
        ).returnconf()
        conf["path_noexec"] = "/tmp/fake_noexec.so"
        shell = DummyShellContext(conf)

        mock_forbidden.side_effect = lambda line, conf, strict=None: (0, conf)
        mock_secure.side_effect = lambda line, conf, strict=None: (0, conf)
        mock_path.side_effect = lambda line, conf, strict=None: (0, conf)
        mock_exec.return_value = 0

        ret = utils.cmd_parse_execute("sudo ls", shell_context=shell)

        self.assertEqual(ret, 0)
        self.assertEqual(mock_exec.call_count, 1)
        self.assertEqual(mock_exec.call_args.args[0], "sudo ls")
        self.assertIsNone(
            mock_exec.call_args.kwargs.get("extra_env"),
            msg="allowed_shell_escape should bypass LD_PRELOAD injection",
        )

    @patch("lshell.utils.signal.getsignal", return_value=None)
    @patch("lshell.utils.signal.signal")
    @patch("lshell.utils.subprocess.Popen")
    def test_exec_cmd_sudo_not_wrapped_in_bash_c(
        self, mock_popen, _mock_signal, _mock_getsignal
    ):
        """sudo commands should be executed directly, not through 'bash -c'."""

        class FakeProc:
            """Minimal subprocess fake for exec_cmd foreground path."""

            def __init__(self):
                self.returncode = 0
                self.pid = 12345
                self.args = ["sudo", "ls"]
                self.lshell_cmd = ""

            def communicate(self):
                """Simulate foreground process I/O completion."""
                return None

            def poll(self):
                """Simulate an already-finished subprocess."""
                return 0

        mock_popen.return_value = FakeProc()

        ret = utils.exec_cmd("sudo ls")

        self.assertEqual(ret, 0)
        popen_args = mock_popen.call_args.args[0]
        self.assertEqual(popen_args[0], "sudo")
        self.assertNotEqual(popen_args[:2], ["bash", "-c"])

    @patch("lshell.utils.signal.getsignal", return_value=None)
    @patch("lshell.utils.signal.signal")
    @patch("lshell.utils.subprocess.Popen")
    def test_exec_cmd_sudo_keeps_foreground_terminal(
        self, mock_popen, _mock_signal, _mock_getsignal
    ):
        """sudo should not be detached from the controlling terminal."""

        class FakeProc:
            """Minimal subprocess fake for exec_cmd foreground path."""

            def __init__(self):
                self.returncode = 0
                self.pid = 12345
                self.args = ["sudo", "ls"]
                self.lshell_cmd = ""

            def communicate(self):
                """Simulate foreground process I/O completion."""
                return None

            def poll(self):
                """Simulate an already-finished subprocess."""
                return 0

        mock_popen.return_value = FakeProc()

        ret = utils.exec_cmd("sudo ls")

        self.assertEqual(ret, 0)
        popen_kwargs = mock_popen.call_args.kwargs
        self.assertNotIn(
            "preexec_fn",
            popen_kwargs,
            msg="sudo should run in the current foreground session to keep tty access",
        )

    @patch("lshell.utils.signal.getsignal", return_value=None)
    @patch("lshell.utils.signal.signal")
    @patch("lshell.utils.subprocess.Popen")
    def test_exec_cmd_su_not_wrapped_in_bash_c(
        self, mock_popen, _mock_signal, _mock_getsignal
    ):
        """su commands should be executed directly, not through 'bash -c'."""

        class FakeProc:
            """Minimal subprocess fake for exec_cmd foreground path."""

            def __init__(self):
                self.returncode = 0
                self.pid = 12345
                self.args = ["su", "-"]
                self.lshell_cmd = ""

            def communicate(self):
                """Simulate foreground process I/O completion."""
                return None

            def poll(self):
                """Simulate an already-finished subprocess."""
                return 0

        mock_popen.return_value = FakeProc()

        ret = utils.exec_cmd("su -")

        self.assertEqual(ret, 0)
        popen_args = mock_popen.call_args.args[0]
        self.assertEqual(popen_args[0], "su")
        self.assertNotEqual(popen_args[:2], ["bash", "-c"])

    @patch("lshell.utils.signal.getsignal", return_value=None)
    @patch("lshell.utils.signal.signal")
    @patch("lshell.utils.subprocess.Popen")
    def test_exec_cmd_su_keeps_foreground_terminal(
        self, mock_popen, _mock_signal, _mock_getsignal
    ):
        """su should not be detached from the controlling terminal."""

        class FakeProc:
            """Minimal subprocess fake for exec_cmd foreground path."""

            def __init__(self):
                self.returncode = 0
                self.pid = 12345
                self.args = ["su", "-"]
                self.lshell_cmd = ""

            def communicate(self):
                """Simulate foreground process I/O completion."""
                return None

            def poll(self):
                """Simulate an already-finished subprocess."""
                return 0

        mock_popen.return_value = FakeProc()

        ret = utils.exec_cmd("su -")

        self.assertEqual(ret, 0)
        popen_kwargs = mock_popen.call_args.kwargs
        self.assertNotIn(
            "preexec_fn",
            popen_kwargs,
            msg="su should run in the current foreground session to keep tty access",
        )

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

    def test_cmd_parse_execute_should_block_forbidden_env_assignment_via_assignment_only(self):
        """Security expectation: assignment-only should not bypass env blacklist."""
        conf = CheckConfig(self.args + ["--forbidden=[]", "--strict=0"]).returnconf()
        shell = DummyShellContext(conf)
        original = os.environ.get("LD_PRELOAD")
        try:
            ret = utils.cmd_parse_execute("LD_PRELOAD=/tmp/evil.so", shell_context=shell)
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
