"""Additional attack-surface unit tests split from part2 for lint size limits."""

import io
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from lshell import utils


class TestAttackSurfacePart3(unittest.TestCase):
    """Focused execution-path hardening tests."""

    @patch("lshell.utils._resolve_trusted_shell", return_value="/bin/dash")
    @patch("lshell.utils.signal.getsignal", return_value=None)
    @patch("lshell.utils.signal.signal")
    @patch("lshell.utils.subprocess.Popen")
    def test_exec_cmd_uses_resolved_trusted_shell_path(
        self,
        mock_popen,
        _mock_signal,
        _mock_getsignal,
        _mock_shell_resolver,
    ):
        """Foreground execution should use trusted absolute shell path."""

        class FakeProc:
            """Minimal successful foreground process stub."""

            def __init__(self):
                self.returncode = 0
                self.pid = 6161
                self.args = ["/bin/dash", "-c", "echo ok"]
                self.lshell_cmd = ""

            def communicate(self):
                """Simulate a successful foreground command run."""
                return None

            def poll(self):
                """Report completed process state."""
                return self.returncode

        mock_popen.return_value = FakeProc()

        ret = utils.exec_cmd("echo ok")

        self.assertEqual(ret, 0)
        popen_args = mock_popen.call_args.args[0]
        self.assertEqual(popen_args, ["/bin/dash", "-c", "echo ok"])

    @patch("lshell.utils._resolve_trusted_shell", return_value=None)
    @patch("lshell.utils.signal.getsignal", return_value=None)
    @patch("lshell.utils.signal.signal")
    @patch("lshell.utils.subprocess.Popen")
    def test_exec_cmd_denies_execution_without_trusted_shell(
        self,
        mock_popen,
        _mock_signal,
        _mock_getsignal,
        _mock_shell_resolver,
    ):
        """Fail closed when no trusted shell interpreter is available."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            ret = utils.exec_cmd("echo ok")

        self.assertEqual(ret, 127)
        self.assertIn(
            "trusted system shell interpreter not found",
            stderr.getvalue(),
        )
        mock_popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
