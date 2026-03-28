"""Unit tests for prompt, prompt_short, and LPS1 override behavior."""

import os
import unittest
from getpass import getuser
from unittest.mock import patch

from lshell.config.runtime import CheckConfig
from lshell.utils import getpromptbase, updateprompt

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


if __name__ == "__main__":
    unittest.main()
