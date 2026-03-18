"""Unit tests for shell signal-related control flow in ShellCmd."""

import io
import os
import unittest
from unittest.mock import patch

from lshell.checkconfig import CheckConfig
from lshell.shellcmd import ShellCmd

TOPDIR = f"{os.path.dirname(os.path.realpath(__file__))}/../"
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"


class TestShellCmdSignalUnit(unittest.TestCase):
    """Validate ShellCmd behavior for Ctrl+C and Ctrl+D/EOF flows."""

    args = [f"--config={CONFIG}", "--quiet=1"]

    def _make_shell(self):
        conf = CheckConfig(self.args + ["--strict=0"]).returnconf()
        shell = ShellCmd(
            conf,
            args=[],
            stdin=io.StringIO(),
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        shell.use_rawinput = False
        return shell

    def test_cmdloop_recovers_from_keyboard_interrupt_during_job_check(self):
        """Keep cmdloop alive when Ctrl+C races outside input() handling."""
        shell = self._make_shell()
        shell.cmdqueue = ["exit"]

        with patch(
            "lshell.shellcmd.builtincmd.check_background_jobs",
            side_effect=[KeyboardInterrupt, None],
        ) as mock_jobs:
            with patch(
                "lshell.shellcmd.utils.updateprompt",
                return_value="unit-prompt$ ",
            ) as mock_prompt:
                with patch("lshell.shellcmd.readline.write_history_file"):
                    with patch("lshell.shellcmd.sys.exit", side_effect=SystemExit):
                        with self.assertRaises(SystemExit):
                            shell.cmdloop()

        self.assertGreaterEqual(mock_jobs.call_count, 2)
        mock_prompt.assert_called_once_with(os.getcwd(), shell.conf)
        self.assertEqual(shell.conf["promptprint"], "unit-prompt$ ")

    def test_do_eof_delegates_to_exit(self):
        """Route EOF (Ctrl+D) through unified exit behavior."""
        shell = self._make_shell()
        with patch.object(shell, "do_exit", return_value=123) as mock_exit:
            self.assertEqual(shell.do_EOF(), 123)
        mock_exit.assert_called_once_with(None)

    def test_do_quit_delegates_to_exit(self):
        """Route quit through unified exit behavior."""
        shell = self._make_shell()
        with patch.object(shell, "do_exit", return_value=456) as mock_exit:
            self.assertEqual(shell.do_quit(), 456)
        mock_exit.assert_called_once_with(None)


if __name__ == "__main__":
    unittest.main()
