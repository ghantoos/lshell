"""Unit tests for history_size parsing and runtime behavior."""

import io
import os
import unittest
from unittest.mock import ANY, call, mock_open, patch

from lshell import history as history_utils
from lshell.config.runtime import CheckConfig
from lshell.shellcmd import (
    READLINE_HISTORY_SEARCH_BINDINGS,
    READLINE_INCREMENTAL_SEARCH_BINDINGS,
    ShellCmd,
    _readline_char_point,
)

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

    def test_cmdloop_does_not_normalize_history_when_input_returns_eof(self):
        """Ctrl-D/EOF should not rewrite the latest history entry as literal EOF."""
        conf = CheckConfig(self.args + ["--strict=0"]).returnconf()
        shell = ShellCmd(
            conf,
            args=[],
            stdin=io.StringIO(),
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )

        with patch("lshell.shellcmd.readline.read_history_file"):
            with patch("lshell.shellcmd.readline.set_history_length"):
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
                                            "lshell.shellcmd.readline.set_completion_display_matches_hook"
                                        ):
                                            with patch(
                                                "lshell.shellcmd.history_utils.prepare_latest_history_entry"
                                            ) as mock_prepare:
                                                with patch(
                                                    "builtins.input",
                                                    side_effect=EOFError,
                                                ):
                                                    with patch(
                                                        "lshell.shellcmd.sys.exit",
                                                        side_effect=SystemExit,
                                                    ):
                                                        with self.assertRaises(SystemExit):
                                                            shell.cmdloop()

        mock_prepare.assert_not_called()

    def test_cmdloop_does_not_normalize_history_for_cmdqueue_entries(self):
        """Queued commands should not be treated as freshly entered readline history."""
        conf = CheckConfig(self.args + ["--strict=0"]).returnconf()
        shell = ShellCmd(
            conf,
            args=[],
            stdin=io.StringIO(),
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        shell.cmdqueue = ["exit"]

        with patch("lshell.shellcmd.readline.read_history_file"):
            with patch("lshell.shellcmd.readline.set_history_length"):
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
                                            "lshell.shellcmd.readline.set_completion_display_matches_hook"
                                        ):
                                            with patch(
                                                "lshell.shellcmd.history_utils.prepare_latest_history_entry"
                                            ) as mock_prepare:
                                                with patch(
                                                    "lshell.shellcmd.sys.exit",
                                                    side_effect=SystemExit,
                                                ):
                                                    with self.assertRaises(SystemExit):
                                                        shell.cmdloop()

        mock_prepare.assert_not_called()

    def test_cmdloop_binds_prefix_history_search_to_arrow_keys(self):
        """Fallback arrow bindings should be installed when custom hooks are unavailable."""
        conf = CheckConfig(self.args + ["--history_size=7", "--strict=0"]).returnconf()
        shell = ShellCmd(
            conf,
            args=[],
            stdin=io.StringIO(),
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        shell.cmdqueue = ["exit"]

        with patch("lshell.shellcmd._bind_custom_history_search", return_value=False) as mock_custom:
            with patch("lshell.shellcmd.readline.read_history_file"):
                with patch("lshell.shellcmd.readline.set_history_length"):
                    with patch(
                        "lshell.shellcmd.readline.get_completer_delims",
                        return_value=" \t\n",
                    ):
                        with patch("lshell.shellcmd.readline.set_completer_delims"):
                            with patch("lshell.shellcmd.readline.get_completer", return_value=None):
                                with patch("lshell.shellcmd.readline.set_completer"):
                                    with patch("lshell.shellcmd.readline.parse_and_bind") as mock_bind:
                                        with patch("lshell.shellcmd.readline.write_history_file"):
                                            with patch(
                                                "lshell.shellcmd.readline.set_completion_display_matches_hook"
                                            ) as mock_hook:
                                                with patch(
                                                    "lshell.shellcmd.sys.exit",
                                                    side_effect=SystemExit,
                                                ):
                                                    with self.assertRaises(SystemExit):
                                                        shell.cmdloop()

        expected_calls = [call(f"{shell.completekey}: complete")]
        expected_calls.extend(call(binding) for binding in READLINE_INCREMENTAL_SEARCH_BINDINGS)
        expected_calls.extend(call(binding) for binding in READLINE_HISTORY_SEARCH_BINDINGS)
        mock_bind.assert_has_calls(expected_calls)
        mock_custom.assert_called_once_with(shell)
        mock_hook.assert_any_call(ANY)
        mock_hook.assert_any_call(None)

    def test_history_search_skips_duplicate_matches_and_restores_original_line(self):
        """Prefix search should deduplicate matches and restore the typed line on final down."""
        conf = CheckConfig(self.args + ["--strict=0"]).returnconf()
        shell = ShellCmd(
            conf,
            args=[],
            stdin=io.StringIO(),
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )

        history_items = {
            1: "echo alpha",
            2: "echo alpha beta",
            3: "echo alpha",
        }
        replaced = []
        with patch("lshell.shellcmd.readline.get_current_history_length", return_value=3):
            with patch("lshell.shellcmd.readline.get_history_item", side_effect=history_items.get):
                with patch("lshell.shellcmd._replace_readline_buffer", side_effect=replaced.append):
                    with patch("lshell.shellcmd.readline.get_line_buffer", return_value="echo a"):
                        shell.history_search(True)
                    with patch(
                        "lshell.shellcmd.readline.get_line_buffer",
                        return_value="echo alpha",
                    ):
                        shell.history_search(True)
                    with patch(
                        "lshell.shellcmd.readline.get_line_buffer",
                        return_value="echo alpha beta",
                    ):
                        shell.history_search(False)
                    with patch(
                        "lshell.shellcmd.readline.get_line_buffer",
                        return_value="echo alpha",
                    ):
                        shell.history_search(False)

        self.assertEqual(
            replaced,
            ["echo alpha", "echo alpha beta", "echo alpha", "echo a"],
        )
        self.assertEqual(shell.history_search_state["matches"], [])
        self.assertIsNone(shell.history_search_state["index"])

    def test_readline_char_point_converts_utf8_byte_offset_to_character_index(self):
        """Byte-based readline cursor offsets should map safely back to string indices."""
        with patch("lshell.shellcmd._readline_point", return_value=2):
            self.assertEqual(_readline_char_point("éx"), 1)

    def test_normalize_history_line_reduces_unquoted_blanks_only(self):
        """History normalization should keep quoted spacing while reducing outer blanks."""
        line = '  echo    "alpha   beta"    gamma  '
        self.assertEqual(
            history_utils.normalize_history_line(line),
            'echo "alpha   beta" gamma',
        )

    def test_prepare_latest_history_entry_replaces_and_drops_consecutive_duplicate(self):
        """Latest history item should be normalized and removed when it duplicates the prior item."""
        with patch("lshell.history.readline.get_current_history_length", return_value=2):
            with patch(
                "lshell.history.readline.get_history_item",
                side_effect=lambda index: {1: "echo alpha", 2: "echo   alpha"}[index],
            ):
                with patch("lshell.history.readline.replace_history_item") as mock_replace:
                    with patch("lshell.history.readline.remove_history_item") as mock_remove:
                        history_utils.prepare_latest_history_entry("echo   alpha")

        mock_replace.assert_called_once_with(1, "echo alpha")
        mock_remove.assert_called_once_with(1)

    def test_entries_for_persisted_history_reduce_blanks_and_keep_latest_duplicate(self):
        """Persisted history should drop older duplicates after normalization."""
        entries = ["echo   alpha", "help", "echo alpha", 'echo    "x   y"']
        self.assertEqual(
            history_utils.entries_for_persisted_history(entries),
            ["help", "echo alpha", 'echo "x   y"'],
        )


if __name__ == "__main__":
    unittest.main()
