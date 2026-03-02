"""Unit tests for lshell policy diagnostics mode."""

import os
import tempfile
import textwrap
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from lshell import policy
from lshell import utils


class TestPolicy(unittest.TestCase):
    """Tests for policy mode resolution and command decisions."""

    def _write_config(self, directory, content, filename="lshell.conf"):
        path = os.path.join(directory, filename)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(textwrap.dedent(content).strip() + "\n")
        return path

    def test_resolve_policy_precedence_and_overrides(self):
        """EX01 | user overrides group and default with +/- merge semantics."""
        with tempfile.TemporaryDirectory() as tempdir:
            include_dir = os.path.join(tempdir, "lshell.d")
            os.makedirs(include_dir, exist_ok=True)

            main_config = self._write_config(
                tempdir,
                f"""
                [global]
                logpath : /tmp
                loglevel : 0
                include_dir : {include_dir}/conf.

                [default]
                allowed : ['ls']
                forbidden : [';']
                warning_counter : 2
                """,
            )

            self._write_config(
                include_dir,
                """
                [grp:ops]
                allowed : + ['cat']
                forbidden : + ['|']
                """,
                filename="conf.10-group",
            )

            self._write_config(
                include_dir,
                """
                [alice]
                allowed : + ['echo ok'] - ['ls']
                """,
                filename="conf.20-user",
            )

            result = policy.resolve_policy(main_config, "alice", ["ops"])

            allowed = result["policy"]["allowed"]
            self.assertIn("cat", allowed)
            self.assertIn("echo ok", allowed)
            self.assertNotIn("ls", allowed)
            self.assertIn("|", result["policy"]["forbidden"])
            self.assertTrue(result["include_files"])
            self.assertTrue(
                any(
                    event["section"] == "alice" and event["key"] == "allowed"
                    for event in result["trace"]
                )
            )

    def test_policy_command_decision_denied_with_reason(self):
        """EX02 | denied command reports actionable reason."""
        runtime_policy = {
            "forbidden": [";"],
            "allowed": ["ls"],
            "strict": 0,
            "sudo_commands": [],
            "allowed_file_extensions": [],
            "path": ["", ""],
        }

        decision = policy.policy_command_decision("echo hello", runtime_policy)
        self.assertFalse(decision["allowed"])
        self.assertIn("unknown syntax", decision["reason"])

    def test_policy_command_decision_allowed_exact_full_command(self):
        """EX03 | exact command line allow-list entry is honored."""
        runtime_policy = {
            "forbidden": [";"],
            "allowed": ["echo ok"],
            "strict": 1,
            "sudo_commands": [],
            "allowed_file_extensions": [],
            "path": ["", ""],
        }

        decision = policy.policy_command_decision("echo ok", runtime_policy)
        self.assertTrue(decision["allowed"])

    def test_build_resolved_rows_order_and_user_origin(self):
        """EX04 | rows are ordered and user section label is explicit."""
        result = {
            "conf_raw": {
                "warning_counter": "2",
                "forbidden": "[';']",
                "umask": "'0077'",
            },
            "policy": {"username": "bleh"},
            "trace": [
                {"key": "forbidden", "section": "default", "source": "/tmp/a.conf"},
                {
                    "key": "warning_counter",
                    "section": "default",
                    "source": "/tmp/a.conf",
                },
                {"key": "umask", "section": "bleh", "source": "/tmp/b.conf"},
            ],
        }

        rows = policy._build_resolved_rows(result)
        keys = [row["key"] for row in rows]
        self.assertEqual(keys, ["forbidden", "warning_counter", "umask"])
        self.assertEqual(rows[-1]["section"], "user:bleh")

    def test_resolve_policy_supports_user_prefixed_section(self):
        """EX05 | [user:<name>] section is resolved and can override values."""
        with tempfile.TemporaryDirectory() as tempdir:
            config = self._write_config(
                tempdir,
                """
                [global]
                logpath : /tmp
                loglevel : 0

                [default]
                allowed : ['ls']
                forbidden : [';']
                warning_counter : 2

                [user:bleh]
                umask : 0077
                """,
            )

            result = policy.resolve_policy(config, "bleh", [])
            self.assertIn("user:bleh", result["applied_sections"])
            rows = policy._build_resolved_rows(result)
            row_by_key = {row["key"]: row for row in rows}
            self.assertEqual(row_by_key["umask"]["section"], "user:bleh")
            self.assertEqual(row_by_key["umask"]["value"], "0077")

    def test_grouped_rows_follow_resolution_order(self):
        """EX06 | grouped rows follow applied section order."""
        result = {
            "conf_raw": {
                "allowed": "['ls']",
                "forbidden": "[';']",
                "umask": "'0007'",
            },
            "policy": {"username": "bleh"},
            "applied_sections": ["default", "user:bleh"],
            "trace": [
                {"key": "allowed", "section": "default"},
                {"key": "forbidden", "section": "default"},
                {"key": "umask", "section": "user:bleh"},
            ],
        }

        grouped = policy._build_grouped_rows(result)
        self.assertEqual(list(grouped.keys()), ["default", "user:bleh"])
        self.assertEqual(
            [r["key"] for r in grouped["default"]], ["allowed", "forbidden"]
        )
        self.assertEqual([r["key"] for r in grouped["user:bleh"]], ["umask"])

    @patch("lshell.policy.grp.getgrall")
    @patch("lshell.policy.grp.getgrgid")
    @patch("lshell.policy.pwd.getpwnam")
    def test_resolve_user_groups_auto_lookup(
        self, mock_getpwnam, mock_getgrgid, mock_getgrall
    ):
        """EX07 | when --group is omitted, user groups are auto-resolved."""
        mock_getpwnam.return_value = SimpleNamespace(pw_gid=1000)
        mock_getgrgid.return_value = SimpleNamespace(gr_name="testuser")
        mock_getgrall.return_value = [
            SimpleNamespace(gr_name="wheel", gr_mem=["someone"]),
            SimpleNamespace(gr_name="devops", gr_mem=["testuser"]),
        ]

        groups = policy._resolve_user_groups("testuser", [])
        self.assertEqual(groups, ["testuser", "devops"])

    def test_resolve_policy_falls_back_to_grp_user_section(self):
        """EX08 | if no groups are provided, grp:<user> section is still considered."""
        with tempfile.TemporaryDirectory() as tempdir:
            config = self._write_config(
                tempdir,
                """
                [global]
                logpath : /tmp
                loglevel : 0

                [default]
                allowed : ['ls']
                forbidden : [';']
                warning_counter : 2

                [grp:testuser]
                disable_exit : 0

                [user:testuser]
                umask : 0077
                """,
            )

            result = policy.resolve_policy(config, "testuser", [])
            self.assertIn("grp:testuser", result["applied_sections"])

    def test_main_without_command_returns_success(self):
        """EX09 | policy show without command should print resolved values and exit 0."""
        with tempfile.TemporaryDirectory() as tempdir:
            config = self._write_config(
                tempdir,
                """
                [global]
                logpath : /tmp
                loglevel : 0

                [default]
                allowed : ['ls']
                forbidden : [';']
                warning_counter : 2
                """,
            )

            ret = policy.main(["--config", config, "--user", "bleh"])
            self.assertEqual(ret, 0)

    def test_resolve_policy_rejects_invalid_allowed_schema(self):
        """EX09b | non-list allowed values should fail schema validation."""
        with tempfile.TemporaryDirectory() as tempdir:
            config = self._write_config(
                tempdir,
                """
                [global]
                logpath : /tmp
                loglevel : 0

                [default]
                allowed : 1
                forbidden : [';']
                warning_counter : 2
                """,
            )

            with self.assertRaises(ValueError) as exc:
                policy.resolve_policy(config, "bleh", [])
            self.assertIn("allowed", str(exc.exception))

    def test_builtin_policy_show_dispatches_from_utils(self):
        """EX10 | builtin dispatcher calls shell_context.do_policy_show."""

        class DummyContext:
            """Minimal shell context stub for builtin dispatcher tests."""

            def __init__(self):
                """Initialize stub fields used by handle_builtin_command."""
                self.conf = {}
                self.called = None

            def do_policy_show(self, arg):
                """Record argument and mimic a successful builtin call."""
                self.called = arg
                return 0

        ctx = DummyContext()
        retcode, _ = utils.handle_builtin_command(
            "policy-show echo hi", "policy-show", "echo hi", ctx
        )
        self.assertEqual(retcode, 0)
        self.assertEqual(ctx.called, "echo hi")


if __name__ == "__main__":
    unittest.main()
