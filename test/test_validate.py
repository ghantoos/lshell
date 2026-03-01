"""Tests for `lshell validate`."""

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest


TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LSHELL = os.path.join(TOPDIR, "bin", "lshell")


class TestValidate(unittest.TestCase):
    """Validation command behavior."""

    def _run_validate(self, args):
        command = [sys.executable, LSHELL, "validate"] + args
        env = dict(os.environ)
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = TOPDIR if not existing else f"{TOPDIR}:{existing}"
        return subprocess.run(
            command, capture_output=True, text=True, check=False, env=env
        )

    def _write_temp_config(self, content):
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as handle:
            handle.write(textwrap.dedent(content))
            return handle.name

    def test_validate_help(self):
        """validate --help should return 0 and print usage."""
        result = self._run_validate(["--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("Usage: lshell validate", result.stdout)

    def test_validate_with_warnings_returns_two(self):
        """Valid config with warnings should return 2 by default."""
        config_path = self._write_temp_config(
            """
            [global]
            logpath : /tmp
            loglevel: 2
            path_noexec: ''

            [default]
            allowed : ['ls']
            forbidden : [';', '&', '|', '`', '>', '<', '$(', '${']
            warning_counter : 2
            strict : 1
            """
        )
        try:
            result = self._run_validate([f"--config={config_path}"])
            self.assertEqual(result.returncode, 2)
            self.assertIn("OK: configuration is valid", result.stdout)
            self.assertIn("WARN:", result.stdout)
        finally:
            os.unlink(config_path)

    def test_validate_strict_warnings_returns_one(self):
        """When --strict-warnings is set, warnings should fail validation."""
        config_path = self._write_temp_config(
            """
            [global]
            logpath : /tmp
            loglevel: 2
            path_noexec: ''

            [default]
            allowed : ['ls']
            forbidden : [';', '&', '|', '`', '>', '<', '$(', '${']
            warning_counter : 2
            strict : 1
            """
        )
        try:
            result = self._run_validate(["--strict-warnings", f"--config={config_path}"])
            self.assertEqual(result.returncode, 1)
            self.assertIn("OK: configuration is valid", result.stdout)
        finally:
            os.unlink(config_path)

    def test_validate_unknown_key_fails_with_hint(self):
        """Unknown keys should fail with a did-you-mean hint."""
        config_path = self._write_temp_config(
            """
            [global]
            logpath : /tmp
            loglevel: 2

            [default]
            allowed : ['ls']
            forbidden : [';', '&', '|', '`', '>', '<', '$(', '${']
            warning_counter : 2
            allowed_file_extension : ['.log']
            """
        )
        try:
            result = self._run_validate([f"--config={config_path}"])
            self.assertEqual(result.returncode, 1)
            self.assertIn("configuration is invalid", result.stderr)
            self.assertIn("allowed_file_extensions", result.stderr)
        finally:
            os.unlink(config_path)


if __name__ == "__main__":
    unittest.main()
