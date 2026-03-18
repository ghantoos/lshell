"""Functional tests for the lshell harden-init CLI mode."""

import os
import subprocess
import tempfile
import unittest

TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LSHELL = f"{TOPDIR}/bin/lshell"


class TestHardenInitFunctional(unittest.TestCase):
    """Exercise harden-init end-to-end through the top-level CLI."""

    def test_harden_init_writes_config_file(self):
        """Generate a config file from a hardened template profile."""
        with tempfile.TemporaryDirectory(prefix="lshell-harden-init-") as tempdir:
            output_path = os.path.join(tempdir, "generated.conf")
            result = subprocess.run(
                [LSHELL, "harden-init", "--profile", "sftp-only", "--output", output_path],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertTrue(os.path.isfile(output_path))
            with open(output_path, "r", encoding="utf-8") as handle:
                rendered = handle.read()
            self.assertIn("[default]", rendered)
            self.assertIn("sftp            : 1", rendered)
            self.assertIn("strict          : 1", rendered)

    def test_harden_init_writes_scoped_group_and_user_sections(self):
        """Generate include file targeting one group and one user."""
        with tempfile.TemporaryDirectory(prefix="lshell-harden-init-") as tempdir:
            output_path = os.path.join(tempdir, "scoped.conf")
            result = subprocess.run(
                [
                    LSHELL,
                    "harden-init",
                    "--profile",
                    "sftp-only",
                    "--group",
                    "sftpusers",
                    "--user",
                    "alice",
                    "--output",
                    output_path,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            with open(output_path, "r", encoding="utf-8") as handle:
                rendered = handle.read()
            self.assertIn("[grp:sftpusers]", rendered)
            self.assertIn("[user:alice]", rendered)
            self.assertNotIn("\n[default]\n", rendered)


if __name__ == "__main__":
    unittest.main()
