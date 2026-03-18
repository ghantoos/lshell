"""Unit tests for lshell harden-init profile generator."""

import contextlib
import io
import os
import tempfile
import unittest
from unittest.mock import patch

from lshell import hardeninit


class TestHardenInit(unittest.TestCase):
    """Validate template rendering, validation, and CLI flags."""

    def test_list_templates_contains_required_profiles(self):
        """List mode includes all shipped hardened templates."""
        rows = dict(hardeninit.list_templates())
        self.assertIn("sftp-only", rows)
        self.assertIn("rsync-backup", rows)
        self.assertIn("deploy-minimal", rows)
        self.assertIn("readonly-support", rows)

    def test_render_profile_includes_inline_security_comments(self):
        """Rendered output includes comments that explain key controls."""
        profile = hardeninit.get_profile("readonly-support")
        rendered = hardeninit.render_profile("readonly-support", profile)
        self.assertIn("# Explicit allow-list only; never use 'all'", rendered)
        self.assertIn("strict          : 1", rendered)
        self.assertIn("forbidden       : [';', '&', '|', '`', '>', '<', '$(', '${']", rendered)

    def test_validate_profile_rejects_unsafe_shell_escape(self):
        """Validation fails when allowed_shell_escape contains risky commands."""
        profile = hardeninit.get_profile("deploy-minimal")
        profile_copy = {"global": dict(profile["global"]), "default": dict(profile["default"])}
        profile_copy["default"]["allowed_shell_escape"] = ["vim"]
        errors = hardeninit.validate_profile("deploy-minimal", profile_copy)
        self.assertTrue(any("unsafe command" in item for item in errors))

    def test_validate_profile_rejects_missing_required_key(self):
        """Validation fails when a required hardened key is absent."""
        profile = hardeninit.get_profile("sftp-only")
        profile_copy = {"global": dict(profile["global"]), "default": dict(profile["default"])}
        profile_copy["default"].pop("strict")
        errors = hardeninit.validate_profile("sftp-only", profile_copy)
        self.assertTrue(any("missing required keys" in item for item in errors))

    def test_run_sanity_checks_pass_for_valid_template(self):
        """Sanity checks succeed for stock profile output."""
        profile = hardeninit.get_profile("rsync-backup")
        rendered = hardeninit.render_profile("rsync-backup", profile)
        ok, details = hardeninit.run_sanity_checks(rendered)
        self.assertTrue(ok)
        self.assertTrue(any("overall" not in item for item in details))

    def test_main_list_templates_flag(self):
        """--list-templates returns success and prints template names."""
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = hardeninit.main(["--list-templates"])
        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("sftp-only", output)
        self.assertIn("rsync-backup", output)

    def test_main_stdout_flag(self):
        """--stdout renders config to standard output."""
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = hardeninit.main(["--profile", "sftp-only", "--stdout"])
        self.assertEqual(code, 0)
        rendered = stdout.getvalue()
        self.assertIn("[default]", rendered)
        self.assertIn("sftp            : 1", rendered)

    def test_main_stdout_group_and_user_flags_render_scoped_sections(self):
        """--group/--user render [grp:*]/[user:*] sections and skip [default]."""
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = hardeninit.main(
                [
                    "--profile",
                    "sftp-only",
                    "--group",
                    "sftpusers",
                    "--user",
                    "alice",
                    "--stdout",
                ]
            )
        self.assertEqual(code, 0)
        rendered = stdout.getvalue()
        self.assertIn("[grp:sftpusers]", rendered)
        self.assertIn("[user:alice]", rendered)
        self.assertNotIn("\n[default]\n", rendered)

    def test_main_dry_run_flag_outputs_sanity(self):
        """--dry-run prints rendered config plus sanity pass/fail lines."""
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = hardeninit.main(["--profile", "rsync-backup", "--dry-run"])
        self.assertEqual(code, 0)
        rendered = stdout.getvalue()
        self.assertIn("sanity: parser: pass", rendered)
        self.assertIn("sanity: overall: pass", rendered)

    def test_main_explain_flag(self):
        """--explain prints rationale alongside requested output mode."""
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = hardeninit.main(
                ["--profile", "readonly-support", "--stdout", "--explain"]
            )
        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("Profile: readonly-support", output)
        self.assertIn("Purpose:", output)

    def test_main_output_writes_file(self):
        """--output writes rendered configuration to the target file."""
        with tempfile.TemporaryDirectory(prefix="lshell-hardeninit-") as tempdir:
            output_file = os.path.join(tempdir, "lshell.conf")
            code = hardeninit.main(
                ["--profile", "deploy-minimal", "--output", output_file]
            )
            self.assertEqual(code, 0)
            self.assertTrue(os.path.exists(output_file))
            with open(output_file, "r", encoding="utf-8") as handle:
                data = handle.read()
            self.assertIn("[global]", data)
            self.assertIn("strict          : 1", data)

    def test_main_defaults_output_to_etc_lshell_d_profile_conf(self):
        """Without output/stdout/dry-run, write to /etc/lshell.d/<profile>.conf."""
        with patch("lshell.hardeninit._write_output") as write_output:
            code = hardeninit.main(["--profile", "sftp-only"])
        self.assertEqual(code, 0)
        write_output.assert_called_once()
        output_path = write_output.call_args[0][0]
        self.assertEqual(output_path, "/etc/lshell.d/sftp-only.conf")

    def test_main_rejects_invalid_group_name(self):
        """Invalid section target names are rejected with clear errors."""
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = hardeninit.main(
                ["--profile", "sftp-only", "--group", "bad/name", "--stdout"]
            )
        self.assertEqual(code, 1)
        self.assertIn("invalid group name", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
