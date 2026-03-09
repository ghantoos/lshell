"""Security-focused unit tests for SSH/SCP/SFTP execution paths."""

import io
import os
import tempfile
import unittest
from unittest.mock import patch

from lshell.checkconfig import CheckConfig
from lshell.shellcmd import ShellCmd

TOPDIR = f"{os.path.dirname(os.path.realpath(__file__))}/../"
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"


class TestSSHScpSftpAttackSurface(unittest.TestCase):
    """Protocol hardening tests split from general attack surface coverage."""

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

    def test_run_overssh_strips_auto_ls_alias_before_execution(self):
        """Keep the synthetic local ls alias from mutating forced SSH commands."""
        saved_env = self._with_forced_ssh_env()
        try:
            conf = CheckConfig(
                self.args + ["--allowed=['echo']", "--overssh=['ls']", "--strict=0"]
            ).returnconf()
            if not conf.get("_auto_ls_alias") or conf["aliases"].get("ls") is None:
                self.skipTest("platform does not synthesize an ls alias")

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
                "/usr/libexec/sftp-server",
                shell_context=unittest.mock.ANY,
                trusted_protocol=True,
            )
        finally:
            self._restore_ssh_env(saved_env)

    def test_run_overssh_rejects_scp_when_disabled_and_not_in_overssh(self):
        """Deny scp transfer when global scp flag is disabled."""
        saved_env = self._with_forced_ssh_env()
        try:
            conf = CheckConfig(self.args + ["--scp=0", "--overssh=[]", "--strict=0"]).returnconf()
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
                self.args + ["--scp=0", "--overssh=['scp']", "--scp_download=1", "--strict=0"]
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
                f"scp -f {conf['home_path']}/artifact",
                shell_context=unittest.mock.ANY,
                trusted_protocol=False,
            )
        finally:
            self._restore_ssh_env(saved_env)

    def test_run_overssh_rejects_scp_download_when_scp_download_disabled(self):
        """Deny scp -f when scp_download flag is disabled."""
        saved_env = self._with_forced_ssh_env()
        try:
            conf = CheckConfig(self.args + ["--scp=1", "--scp_download=0", "--strict=0"]).returnconf()
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
            conf = CheckConfig(self.args + ["--scp=1", "--scp_upload=0", "--strict=0"]).returnconf()
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
            with tempfile.TemporaryDirectory(prefix="lshell_scpforce_", dir=os.environ["HOME"]) as forced_dir:
                conf = CheckConfig(
                    self.args + ["--scp=1", "--scp_upload=1", f"--scpforce='{forced_dir}'", "--strict=0"]
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
                trusted_protocol=False,
            )
        finally:
            self._restore_ssh_env(saved_env)

    def test_run_overssh_rejects_scp_chain_with_non_protocol_segment(self):
        """Reject scp chaining when a later segment is not allowed over SSH."""
        saved_env = self._with_forced_ssh_env()
        try:
            conf = CheckConfig(self.args + ["--scp=1", "--scp_download=1"]).returnconf()
            conf["ssh"] = f"scp -f {conf['home_path']}/artifact || id"
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

    def test_run_overssh_applies_aliases_to_scp_commands(self):
        """Expand aliases before SCP policy checks and execution."""
        saved_env = self._with_forced_ssh_env()
        try:
            conf = CheckConfig(
                self.args
                + [
                    "--scp=1",
                    "--scp_download=1",
                    f"--aliases={{'getscp':'scp -f {os.environ['HOME']}/artifact'}}",
                ]
            ).returnconf()
            conf["ssh"] = "getscp"
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
                f"scp -f {conf['home_path']}/artifact",
                shell_context=unittest.mock.ANY,
                trusted_protocol=False,
            )
        finally:
            self._restore_ssh_env(saved_env)


if __name__ == "__main__":
    unittest.main()
