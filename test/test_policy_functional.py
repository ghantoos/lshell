"""Functional tests for `lshell policy-show` CLI behavior."""

import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from getpass import getuser


TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LSHELL = f"{TOPDIR}/bin/lshell"


class TestPolicyShowFunctional(unittest.TestCase):
    """Exercise policy-show end-to-end through the top-level CLI."""

    def _write_config(self, directory, content):
        config_path = os.path.join(directory, "lshell.conf")
        with open(config_path, "w", encoding="utf-8") as handle:
            handle.write(textwrap.dedent(content).strip() + "\n")
        return config_path

    def test_policy_show_json_returns_allow_decision(self):
        """policy-show should return JSON payload with allow decision details."""
        with tempfile.TemporaryDirectory(prefix="lshell-policy-show-") as tempdir:
            config_path = self._write_config(
                tempdir,
                """
                [global]
                logpath : /tmp
                loglevel : 0

                [default]
                allowed : ['ls']
                forbidden : [';']
                warning_counter : 2
                strict : 1
                """,
            )

            result = subprocess.run(
                [
                    LSHELL,
                    "policy-show",
                    "--config",
                    config_path,
                    "--user",
                    getuser(),
                    "--command",
                    "ls",
                    "--json",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["command"], "ls")
            self.assertTrue(payload["decision"]["allowed"])
            self.assertIn("allowed by final policy", payload["decision"]["reason"])

    def test_policy_show_trailing_command_args_return_deny_exit_code(self):
        """Trailing command args (after --) should be parsed and denied with code 2."""
        with tempfile.TemporaryDirectory(prefix="lshell-policy-show-") as tempdir:
            config_path = self._write_config(
                tempdir,
                """
                [global]
                logpath : /tmp
                loglevel : 0

                [default]
                allowed : ['ls']
                forbidden : [';']
                warning_counter : 2
                strict : 0
                """,
            )

            result = subprocess.run(
                [
                    LSHELL,
                    "policy-show",
                    "--config",
                    config_path,
                    "--user",
                    getuser(),
                    "--json",
                    "--",
                    "echo",
                    "blocked",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["command"], "echo blocked")
            self.assertFalse(payload["decision"]["allowed"])
            self.assertIn("unknown syntax", payload["decision"]["reason"])


if __name__ == "__main__":
    unittest.main()
