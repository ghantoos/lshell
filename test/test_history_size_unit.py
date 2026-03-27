"""Unit tests for history_size parsing and runtime behavior."""

import io
import os
import unittest
from unittest.mock import mock_open, patch

from lshell.config.runtime import CheckConfig
from lshell.shellcmd import ShellCmd

TOPDIR = f"{os.path.dirname(os.path.realpath(__file__))}/../"
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"


class TestHistorySizeUnit(unittest.TestCase):
    """Tests for config parsing and cmdloop history-size handling."""

    args = [f"--config={CONFIG}", "--quiet=1"]

    def test_history_size_defaults_to_minus_one(self):
        """Default history_size should keep readline unlimited (-1)."""
        userconf = CheckConfig(self.args).returnconf()
        self.assertEqual(userconf["history_size"], -1)

    def test_history_size_accepts_integer_override(self):
        """Parse --history_size integer values from command-line overrides."""
        userconf = CheckConfig(self.args + ["--history_size=25"]).returnconf()
        self.assertEqual(userconf["history_size"], 25)

    def test_history_size_rejects_non_integer(self):
        """Reject non-integer history_size values at config-parse time."""
        with self.assertRaises(SystemExit) as exc:
            CheckConfig(self.args + ["--history_size='abc'"]).returnconf()
        self.assertEqual(exc.exception.code, 1)

    def test_cmdloop_applies_history_size_when_history_file_exists(self):
        """Apply readline history length when history file is readable."""
        conf = CheckConfig(self.args + ["--history_size=25", "--strict=0"]).returnconf()
        shell = ShellCmd(
            conf,
            args=[],
            stdin=io.StringIO(),
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        shell.cmdqueue = ["exit"]

        with patch("lshell.shellcmd.readline.read_history_file") as mock_read:
            with patch("lshell.shellcmd.readline.set_history_length") as mock_len:
                with patch(
                    "lshell.shellcmd.readline.get_completer_delims",
                    return_value=" \t\n",
                ):
                    with patch("lshell.shellcmd.readline.set_completer_delims"):
                        with patch("lshell.shellcmd.readline.get_completer", return_value=None):
                            with patch("lshell.shellcmd.readline.set_completer"):
                                with patch("lshell.shellcmd.readline.parse_and_bind"):
                                    with patch("lshell.shellcmd.readline.write_history_file"):
                                        with patch(
                                            "lshell.shellcmd.sys.exit",
                                            side_effect=SystemExit,
                                        ):
                                            with self.assertRaises(SystemExit):
                                                shell.cmdloop()

        mock_read.assert_called_once_with(conf["history_file"])
        mock_len.assert_called_once_with(25)

    def test_cmdloop_applies_history_size_when_history_file_missing(self):
        """Still apply history length when history file must be created first."""
        conf = CheckConfig(self.args + ["--history_size=11", "--strict=0"]).returnconf()
        shell = ShellCmd(
            conf,
            args=[],
            stdin=io.StringIO(),
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        shell.cmdqueue = ["exit"]

        with patch(
            "lshell.shellcmd.readline.read_history_file",
            side_effect=[IOError(), None],
        ) as mock_read:
            with patch("lshell.shellcmd.open", mock_open()):
                with patch("lshell.shellcmd.readline.set_history_length") as mock_len:
                    with patch(
                        "lshell.shellcmd.readline.get_completer_delims",
                        return_value=" \t\n",
                    ):
                        with patch("lshell.shellcmd.readline.set_completer_delims"):
                            with patch(
                                "lshell.shellcmd.readline.get_completer",
                                return_value=None,
                            ):
                                with patch("lshell.shellcmd.readline.set_completer"):
                                    with patch("lshell.shellcmd.readline.parse_and_bind"):
                                        with patch("lshell.shellcmd.readline.write_history_file"):
                                            with patch(
                                                "lshell.shellcmd.sys.exit",
                                                side_effect=SystemExit,
                                            ):
                                                with self.assertRaises(SystemExit):
                                                    shell.cmdloop()

        self.assertEqual(mock_read.call_count, 2)
        mock_len.assert_called_once_with(11)


if __name__ == "__main__":
    unittest.main()
