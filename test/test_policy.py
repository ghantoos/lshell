"""Unit tests for lshell policy diagnostics mode."""

import io
import os
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
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
            self.assertIn("ls", allowed)
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

    def test_policy_command_decision_denies_extensionless_argument(self):
        """EX03b | extension policy blocks extensionless file arguments."""
        runtime_policy = {
            "forbidden": [";"],
            "allowed": ["touch"],
            "strict": 1,
            "sudo_commands": [],
            "allowed_file_extensions": [".log"],
            "path": ["", ""],
        }

        decision = policy.policy_command_decision("touch report", runtime_policy)
        self.assertFalse(decision["allowed"])
        self.assertIn("<none>", decision["reason"])

    def test_policy_command_decision_allows_dotted_parent_directory(self):
        """EX03c | extension check uses final file suffix, not parent path dots."""
        runtime_policy = {
            "forbidden": [";"],
            "allowed": ["cat"],
            "strict": 1,
            "sudo_commands": [],
            "allowed_file_extensions": [".log"],
            "path": ["", ""],
        }

        decision = policy.policy_command_decision(
            "cat /tmp/releases.v1/audit.log", runtime_policy
        )
        self.assertTrue(decision["allowed"])

    def test_policy_command_decision_exempts_builtin_ls_from_extension_filter(self):
        """EX03d | builtin ls is not constrained by allowed_file_extensions."""
        runtime_policy = {
            "forbidden": [";"],
            "allowed": ["ls"],
            "strict": 1,
            "sudo_commands": [],
            "allowed_file_extensions": [".log"],
            "path": ["", ""],
        }

        decision = policy.policy_command_decision("ls /tmp", runtime_policy)
        self.assertTrue(decision["allowed"])

    def test_resolve_policy_allowed_all_unquoted_expands(self):
        """EX03e | allowed=all (unquoted) should expand successfully."""
        with tempfile.TemporaryDirectory() as tempdir:
            config = self._write_config(
                tempdir,
                """
                [global]
                logpath : /tmp
                loglevel : 0

                [default]
                allowed : all
                forbidden : [';']
                warning_counter : 2
                """,
            )
            result = policy.resolve_policy(config, "bleh", [])
            self.assertIn("ls", result["policy"]["allowed"])

    def test_resolve_policy_allowed_all_minus_list(self):
        """EX03f | allowed supports all - [item] merge semantics."""
        with tempfile.TemporaryDirectory() as tempdir:
            config = self._write_config(
                tempdir,
                """
                [global]
                logpath : /tmp
                loglevel : 0

                [default]
                allowed : all - ['echo']
                forbidden : [';']
                warning_counter : 2
                """,
            )
            result = policy.resolve_policy(config, "bleh", [])
            self.assertNotIn("echo", result["policy"]["allowed"])

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

    def test_resolve_policy_plus_minus_supported_for_all_list_merge_keys(self):
        """EX08b | policy mode applies +/- merges on every merge-capable list key."""
        with tempfile.TemporaryDirectory() as tempdir:
            config = self._write_config(
                tempdir,
                """
                [global]
                logpath : /tmp
                loglevel : 0

                [default]
                allowed : ['basecmd']
                allowed_shell_escape : ['ase_base']
                allowed_file_extensions : ['.log']
                forbidden : [';']
                overssh : ['scp', 'rsync']
                path : ['/']
                warning_counter : 2

                [user:bleh]
                allowed : + ['pluscmd'] - ['basecmd']
                allowed_shell_escape : + ['ase_plus'] - ['ase_base']
                allowed_file_extensions : + ['.txt'] - ['.log']
                forbidden : + ['#'] - [';']
                overssh : + ['ls'] - ['scp']
                path : - ['/var', '/etc'] + ['/var/log']
                """,
            )

            result = policy.resolve_policy(config, "bleh", [])
            runtime_policy = result["policy"]

            self.assertIn("pluscmd", runtime_policy["allowed"])
            self.assertNotIn("basecmd", runtime_policy["allowed"])

            self.assertEqual(set(runtime_policy["allowed_shell_escape"]), {"ase_plus"})
            self.assertEqual(set(runtime_policy["allowed_file_extensions"]), {".txt"})

            self.assertIn("#", runtime_policy["forbidden"])
            self.assertNotIn(";", runtime_policy["forbidden"])

            self.assertIn("rsync", runtime_policy["overssh"])
            self.assertIn("ls", runtime_policy["overssh"])
            self.assertNotIn("scp", runtime_policy["overssh"])

            self.assertTrue(runtime_policy["path"][0].startswith("/|"))
            self.assertIn(
                f"{os.path.realpath('/var/log')}/|",
                runtime_policy["path"][0],
            )
            self.assertIn(f"{os.path.realpath('/var')}/|", runtime_policy["path"][1])
            self.assertIn(f"{os.path.realpath('/etc')}/|", runtime_policy["path"][1])

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

    def test_print_user_view_includes_containment_settings(self):
        """EX11 | policy overview includes runtime containment limits."""
        result = {
            "policy": {
                "username": "bleh",
                "strict": 1,
                "warning_counter": 2,
                "allowed": ["ls"],
                "aliases": {},
                "sudo_commands": [],
                "timer": 0,
                "forbidden": [";"],
                "allowed_file_extensions": [],
                "max_sessions_per_user": 2,
                "max_background_jobs": 3,
                "command_timeout": 15,
                "max_processes": 10,
            }
        }

        with redirect_stdout(io.StringIO()) as output:
            policy.print_user_view(result)
        rendered = output.getvalue()

        self.assertIn("Max sessions/user      : 2", rendered)
        self.assertIn("Max background jobs    : 3", rendered)
        self.assertIn("Command timeout (sec)  : 15s", rendered)
        self.assertIn("Max processes          : 10", rendered)

    def test_print_user_view_shows_unlimited_for_zero_containment_limits(self):
        """EX12 | zero-valued containment limits should render as Unlimited."""
        result = {
            "policy": {
                "username": "bleh",
                "strict": 0,
                "warning_counter": 2,
                "allowed": ["ls"],
                "aliases": {},
                "sudo_commands": [],
                "timer": 0,
                "forbidden": [";"],
                "allowed_file_extensions": [],
                "max_sessions_per_user": 0,
                "max_background_jobs": 0,
                "command_timeout": 0,
                "max_processes": 0,
            }
        }

        with redirect_stdout(io.StringIO()) as output:
            policy.print_user_view(result)
        rendered = output.getvalue()

        self.assertIn("Max sessions/user      : Unlimited", rendered)
        self.assertIn("Max background jobs    : Unlimited", rendered)
        self.assertIn("Command timeout (sec)  : Unlimited", rendered)
        self.assertIn("Max processes          : Unlimited", rendered)


if __name__ == "__main__":
    unittest.main()
