"""Unit tests for prompt, prompt_short, and LPS1 override behavior."""

import os
import unittest
from getpass import getuser
from time import struct_time
from unittest.mock import patch

from lshell.config.runtime import CheckConfig
from lshell.utils import getpromptbase, parse_ps1, updateprompt

TOPDIR = f"{os.path.dirname(os.path.realpath(__file__))}/../"
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"


class TestPromptUnit(unittest.TestCase):
    """Prompt rendering tests focused on documented behavior."""

    args = [f"--config={CONFIG}", "--quiet=1"]

    def test_prompt_short_rejects_values_outside_documented_range(self):
        """Reject prompt_short values that are not 0, 1, or 2."""
        with self.assertRaises(SystemExit) as exc:
            CheckConfig(self.args + ["--prompt_short=3"]).returnconf()
        self.assertEqual(exc.exception.code, 1)

    def test_lps1_override_ignores_prompt_and_prompt_short(self):
        """LPS1 should fully override both prompt template and path style."""
        conf = CheckConfig(
            self.args + ["--prompt='%u@%h'", "--prompt_short=2"]
        ).returnconf()
        with patch.dict(os.environ, {"LPS1": "PROMPT> "}, clear=False):
            rendered = updateprompt("/tmp/lshell-path-that-should-not-appear", conf)
        self.assertEqual(rendered, "PROMPT> ")

    def test_getpromptbase_uses_config_prompt_when_lps1_not_set(self):
        """Prompt placeholders should expand from config when LPS1 is absent."""
        conf = CheckConfig(self.args + ["--prompt='%u@%h'"]).returnconf()
        with patch.dict(os.environ, {}, clear=True):
            rendered = getpromptbase(conf)
        expected = f"{getuser()}@{os.uname()[1].split('.')[0]}"
        self.assertEqual(rendered, expected)

    def test_parse_ps1_time_placeholders_use_localtime(self):
        """LPS1 time placeholders should render in local server time."""
        fixed_localtime = struct_time((2026, 6, 16, 21, 7, 5, 1, 167, -1))
        with patch("lshell.utils.localtime", return_value=fixed_localtime) as mock_localtime:
            rendered = parse_ps1(r"\t|\T|\A")
        self.assertEqual(rendered, "21:07:05|09:07:05|21:07")
        mock_localtime.assert_called_once()


if __name__ == "__main__":
    unittest.main()
