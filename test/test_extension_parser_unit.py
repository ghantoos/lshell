"""Unit tests for allowed file extension parser and builtin exemptions."""

import io
import os
import unittest
from unittest.mock import ANY, patch

from lshell import sec
from lshell import utils
from lshell.checkconfig import CheckConfig

TOPDIR = f"{os.path.dirname(os.path.realpath(__file__))}/../"
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"


class DummyLog:
    """Minimal logger object for command parser tests."""

    def critical(self, _message):
        """No-op logger stub."""


class DummyShellContext:
    """Minimal shell context consumed by utils.cmd_parse_execute."""

    def __init__(self, conf):
        self.conf = conf
        self.log = DummyLog()
        self.stdin = io.StringIO()
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()


class TestExtensionParser(unittest.TestCase):
    """Unit tests for extension parsing behavior."""

    args = [f"--config={CONFIG}", "--quiet=1"]

    def test_allowed_extension_check_blocks_extensionless_arguments(self):
        """Reject extensionless operands when extension policy is configured."""
        allowed, disallowed = sec.check_allowed_file_extensions("touch report", [".log"])
        self.assertFalse(allowed)
        self.assertEqual(disallowed, ["<none>"])

    def test_allowed_extension_check_uses_final_filename_extension(self):
        """Use final basename suffix for multi-dot paths."""
        allowed, disallowed = sec.check_allowed_file_extensions(
            "cat /tmp/archive.v1/report.tar.gz",
            [".gz"],
        )
        self.assertTrue(allowed)
        self.assertIsNone(disallowed)

    def test_allowed_extension_check_ignores_option_tokens(self):
        """Parse option values and validate extension-bearing patterns."""
        allowed, disallowed = sec.check_allowed_file_extensions(
            "cat --include=*.log app.log",
            [".log"],
        )
        self.assertTrue(allowed)
        self.assertIsNone(disallowed)

    def test_allowed_extension_check_ignores_literal_when_file_like_present(self):
        """Treat bare literals as non-files when explicit file-like args exist."""
        allowed, disallowed = sec.check_allowed_file_extensions(
            "cat --include=*.log value app.log",
            [".log"],
        )
        self.assertTrue(allowed)
        self.assertIsNone(disallowed)

    def test_extension_policy_exempts_selected_builtin_commands(self):
        """Skip extension enforcement for selected builtins."""
        self.assertFalse(sec.should_enforce_file_extensions("cd"))
        self.assertFalse(sec.should_enforce_file_extensions("clear"))
        self.assertFalse(sec.should_enforce_file_extensions("fg"))
        self.assertFalse(sec.should_enforce_file_extensions("bg"))
        self.assertFalse(sec.should_enforce_file_extensions("ls"))

    def test_check_secure_does_not_apply_extension_policy_to_cd(self):
        """Ensure extension policy is not evaluated for builtin cd."""
        conf = CheckConfig(
            self.args
            + [
                "--allowed=['cd']",
                "--allowed_file_extensions=['.log']",
                "--strict=1",
            ]
        ).returnconf()
        ret, _ = sec.check_secure("cd /tmp", conf, strict=1)
        self.assertEqual(ret, 0)

    @patch("lshell.utils.exec_cmd", return_value=0)
    def test_cmd_parse_execute_treats_ls_as_builtin(self, mock_exec_cmd):
        """Dispatch ls through builtin handling path."""
        conf = CheckConfig(
            self.args
            + [
                "--allowed=['ls']",
                "--allowed_file_extensions=['.log']",
                "--path=['/tmp']",
                "--strict=1",
            ]
        ).returnconf()
        shell_context = DummyShellContext(conf)
        retcode = utils.cmd_parse_execute("ls /tmp", shell_context=shell_context)
        self.assertEqual(retcode, 0)
        mock_exec_cmd.assert_called_once_with(
            "ls /tmp",
            conf=ANY,
            log=ANY,
        )


if __name__ == "__main__":
    unittest.main()
