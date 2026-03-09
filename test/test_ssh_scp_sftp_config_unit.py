"""Unit tests for SSH/SCP/SFTP-related configuration behavior."""

import os
import tempfile
import unittest

from lshell.checkconfig import CheckConfig
from lshell import builtincmd

TOPDIR = f"{os.path.dirname(os.path.realpath(__file__))}/../"
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"


class TestSSHScpSftpConfig(unittest.TestCase):
    """Config-level protocol tests split from generic unit coverage."""

    args = [f"--config={CONFIG}", "--quiet=1"]

    def test_20_winscp_allowed_commands(self):
        """U20 | when winscp is enabled, new allowed commands are automatically added."""
        args = self.args + ["--allowed=[]", "--winscp=1"]
        userconf = CheckConfig(args).returnconf()
        exclude = list(set(builtincmd.builtins_list) - set(["export"]))
        expected = exclude + ["scp", "env", "pwd", "groups", "unset", "unalias"]
        expected.sort()
        allowed = userconf["allowed"]
        allowed.sort()
        self.assertEqual(allowed, expected)

    def test_21_winscp_allowed_semicolon(self):
        """U21 | when winscp is enabled, use of semicolon is allowed."""
        args = self.args + ["--forbidden=[';']", "--winscp=1"]
        userconf = CheckConfig(args).returnconf()
        self.assertNotIn(";", userconf["forbidden"])

    def test_21b_winscp_forces_scp_transfers_enabled(self):
        """U21b | winscp should override scp_upload/scp_download to enabled."""
        args = self.args + ["--scp_upload=0", "--scp_download=0", "--winscp=1"]
        userconf = CheckConfig(args).returnconf()
        self.assertEqual(userconf["scp_upload"], 1)
        self.assertEqual(userconf["scp_download"], 1)

    def test_21c_winscp_ignores_scpforce(self):
        """U21c | winscp should ignore scpforce setting."""
        with tempfile.TemporaryDirectory() as forced_dir:
            args = self.args + [f"--scpforce='{forced_dir}'", "--winscp=1"]
            userconf = CheckConfig(args).returnconf()
            self.assertNotIn("scpforce", userconf)

    def test_21d_scp_transfer_flags_default_to_enabled(self):
        """U21d | scp_upload/scp_download default values should be enabled."""
        userconf = CheckConfig(self.args).returnconf()
        self.assertEqual(userconf["scp_upload"], 1)
        self.assertEqual(userconf["scp_download"], 1)


if __name__ == "__main__":
    unittest.main()
