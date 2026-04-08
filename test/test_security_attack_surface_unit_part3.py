"""Additional attack-surface unit tests split from part2 for lint size limits."""

import errno
import io
import os
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from lshell import utils


class TestAttackSurfacePart3(unittest.TestCase):
    """Focused execution-path hardening tests."""

    @patch("lshell.utils.signal.getsignal", return_value=None)
    @patch("lshell.utils.signal.signal")
    @patch("lshell.utils.subprocess.Popen")
    def test_exec_cmd_runs_with_shell_false_argv_parsing(
        self,
        mock_popen,
        _mock_signal,
        _mock_getsignal,
    ):
        """Foreground execution should pass parsed argv directly to subprocess."""

        class FakeProc:
            """Minimal successful foreground process stub."""

            def __init__(self):
                self.returncode = 0
                self.pid = 6161
                self.args = ["echo", "ok"]
                self.lshell_cmd = ""

            def poll(self):
                """Report completed process state."""
                return self.returncode

            def wait(self, timeout=None):  # pylint: disable=unused-argument
                """Simulate a successful foreground command run."""
                return self.returncode

        mock_popen.return_value = FakeProc()

        ret = utils.exec_cmd("echo ok")

        self.assertEqual(ret, 0)
        popen_args = mock_popen.call_args.args[0]
        self.assertEqual(popen_args, ["echo", "ok"])

    @patch("lshell.utils.signal.getsignal", return_value=None)
    @patch("lshell.utils.signal.signal")
    @patch("lshell.utils.subprocess.Popen")
    def test_exec_cmd_pipeline_wires_subprocess_stdio_without_shell(
        self,
        mock_popen,
        _mock_signal,
        _mock_getsignal,
    ):
        """Pipeline execution should connect stdout/stdin directly between stages."""

        class FakePipe:
            """Minimal file-like pipe placeholder used for mocked stdio wiring."""

            def close(self):
                """Match close() calls performed by exec_cmd."""
                return None

        class FakeProc:
            """Minimal successful foreground subprocess fake."""

            def __init__(self, pid, args, stdout=None):
                self.returncode = 0
                self.pid = pid
                self.args = args
                self.stdout = stdout
                self.lshell_cmd = ""

            def poll(self):
                """Report completed process state."""
                return self.returncode

            def wait(self, timeout=None):  # pylint: disable=unused-argument
                """Simulate a successful foreground command run."""
                return self.returncode

        first_pipe = FakePipe()
        popen_calls = []

        def _popen_side_effect(args, **kwargs):
            index = len(popen_calls)
            if index == 0:
                proc = FakeProc(7001, args, stdout=first_pipe)
            else:
                proc = FakeProc(7002, args, stdout=None)
            popen_calls.append({"args": args, "kwargs": kwargs, "proc": proc})
            return proc

        mock_popen.side_effect = _popen_side_effect

        ret = utils.exec_cmd("printf foo | wc -c")

        self.assertEqual(ret, 0)
        self.assertEqual(len(popen_calls), 2)
        self.assertEqual(popen_calls[0]["args"], ["printf", "foo"])
        self.assertEqual(popen_calls[1]["args"], ["wc", "-c"])
        self.assertEqual(popen_calls[0]["kwargs"]["stdout"], utils.subprocess.PIPE)
        self.assertIs(popen_calls[1]["kwargs"]["stdin"], first_pipe)

    @patch("lshell.utils.signal.getsignal", return_value=None)
    @patch("lshell.utils.signal.signal")
    @patch("lshell.utils.os.getpgid", return_value=7001)
    @patch("lshell.utils.os.killpg")
    @patch("lshell.utils.subprocess.Popen")
    def test_exec_cmd_pipeline_spawn_failure_kills_and_reaps_started_members(
        self,
        mock_popen,
        mock_killpg,
        _mock_getpgid,
        _mock_signal,
        _mock_getsignal,
    ):
        """If a later stage fails to spawn, already started members must be killed/reaped."""

        class FakePipe:
            """Minimal pipe placeholder compatible with close() calls."""

            def close(self):
                """Match close() usage inside pipeline setup."""
                return None

        class RunningProc:
            """Mock process that only exits after receiving a kill signal."""

            def __init__(self):
                self.pid = 7001
                self.args = ["sleep", "60"]
                self.stdout = FakePipe()
                self.returncode = None
                self.killed = False
                self.wait_called = False

            def poll(self):
                """Report running until the test marks this process as killed."""
                return self.returncode

            def wait(self, timeout=None):  # pylint: disable=unused-argument
                """Only return once the process has been killed by cleanup logic."""
                self.wait_called = True
                if not self.killed:
                    raise utils.subprocess.TimeoutExpired(self.args, timeout or 0)
                return self.returncode

        first_stage = RunningProc()

        def _popen_side_effect(args, **kwargs):  # pylint: disable=unused-argument
            if args[0] == "sleep":
                return first_stage
            raise FileNotFoundError(
                errno.ENOENT,
                "No such file or directory",
                "missing_stage",
            )

        def _killpg_side_effect(pgid, signum):
            self.assertEqual(signum, utils.signal.SIGKILL)
            self.assertEqual(pgid, first_stage.pid)
            first_stage.killed = True
            first_stage.returncode = -9

        mock_popen.side_effect = _popen_side_effect
        mock_killpg.side_effect = _killpg_side_effect

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            ret = utils.exec_cmd("sleep 60 | missing_stage")

        self.assertEqual(ret, 127)
        self.assertIn('lshell: command not found: "missing_stage"', stderr.getvalue())
        self.assertTrue(first_stage.killed)
        self.assertTrue(first_stage.wait_called)

    @patch("lshell.utils.signal.getsignal", return_value=None)
    @patch("lshell.utils.signal.signal")
    @patch("lshell.utils.subprocess.Popen")
    def test_exec_cmd_rejects_command_substitution_without_shell_execution(
        self,
        mock_popen,
        _mock_signal,
        _mock_getsignal,
    ):
        """Fail closed when command relies on shell command substitution syntax."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            ret = utils.exec_cmd("echo $(printf ok)")

        self.assertEqual(ret, 126)
        self.assertIn(
            "unsupported shell syntax in command execution: command substitution ($(...))",
            stderr.getvalue(),
        )
        mock_popen.assert_not_called()

    @patch("lshell.utils.signal.getsignal", return_value=None)
    @patch("lshell.utils.signal.signal")
    @patch("lshell.utils.subprocess.Popen")
    def test_exec_cmd_rejects_redirection_syntax_without_shell_execution(
        self,
        mock_popen,
        _mock_signal,
        _mock_getsignal,
    ):
        """Fail closed when command relies on shell-only redirection syntax."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            ret = utils.exec_cmd("echo ok > /tmp/lshell-redir")

        self.assertEqual(ret, 126)
        self.assertIn(
            "unsupported shell syntax in command execution: redirection operators",
            stderr.getvalue(),
        )
        mock_popen.assert_not_called()

    @patch("lshell.utils.signal.getsignal", return_value=None)
    @patch("lshell.utils.signal.signal")
    @patch("lshell.utils.resolve_trusted_bash_path", return_value="/bin/bash")
    @patch("lshell.utils.subprocess.Popen")
    def test_exec_cmd_bash_compat_uses_trusted_bash_and_scrubs_env(
        self,
        mock_popen,
        _mock_resolve_bash,
        _mock_signal,
        _mock_getsignal,
    ):
        """bash_compat execution must use trusted bash path and hardened child env."""

        class FakeProc:
            """Minimal successful foreground process stub."""

            def __init__(self):
                self.returncode = 0
                self.pid = 8181
                self.args = ["/bin/bash", "-c", "echo ok"]
                self.lshell_cmd = ""

            def poll(self):
                """Report completed process state."""
                return self.returncode

            def wait(self, timeout=None):  # pylint: disable=unused-argument
                """Simulate a successful foreground command run."""
                return self.returncode

        mock_popen.return_value = FakeProc()

        with patch.dict(
            os.environ,
            {
                "BASH_ENV": "/tmp/inject",
                "ENV": "/tmp/inject",
                "BASH_FUNC_echo%%": "() { id; }",
                "LSHELL_SAFE_ENV": "ok",
            },
            clear=True,
        ):
            ret = utils.exec_cmd("echo ok", conf={"runtime_executor": "bash_compat"})

        self.assertEqual(ret, 0)
        self.assertEqual(
            mock_popen.call_args.args[0], ["/bin/bash", "-c", "echo ok"]
        )
        child_env = mock_popen.call_args.kwargs["env"]
        self.assertNotIn("BASH_ENV", child_env)
        self.assertNotIn("ENV", child_env)
        self.assertNotIn("BASH_FUNC_echo%%", child_env)
        self.assertEqual(child_env.get("LSHELL_SAFE_ENV"), "ok")

    @patch("lshell.utils.signal.getsignal", return_value=None)
    @patch("lshell.utils.signal.signal")
    @patch("lshell.utils.resolve_trusted_bash_path", return_value=None)
    @patch("lshell.utils.subprocess.Popen")
    def test_exec_cmd_bash_compat_fails_closed_when_no_trusted_bash(
        self,
        mock_popen,
        _mock_resolve_bash,
        _mock_signal,
        _mock_getsignal,
    ):
        """bash_compat should fail closed if no trusted absolute bash path is present."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            ret = utils.exec_cmd("echo ok", conf={"runtime_executor": "bash_compat"})

        self.assertEqual(ret, 126)
        self.assertIn(
            "runtime_executor=bash_compat requires a trusted absolute bash path",
            stderr.getvalue(),
        )
        mock_popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
