"""Regression tests ensuring runtime and diagnostics share merge behavior."""

import io
import os
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from lshell.config.runtime import CheckConfig
from lshell.config import diagnostics as policy


class TestPolicyMergeParity(unittest.TestCase):
    """Validate parity between runtime config merge and policy diagnostics."""

    def _write_config(self, directory, content, filename="lshell.conf"):
        path = os.path.join(directory, filename)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(textwrap.dedent(content).strip() + "\n")
        return path

    def _runtime_checkconfig(self, configfile, username, group_ids, gid_to_group):
        def _fake_getgrgid(gid):
            if gid in gid_to_group:
                return (gid_to_group[gid], "x", gid, [])
            raise KeyError(gid)

        with (
            patch("lshell.config.runtime.getuser", return_value=username),
            patch("lshell.config.runtime.os.getgroups", return_value=group_ids),
            patch("lshell.config.runtime.grp.getgrgid", side_effect=_fake_getgrgid),
        ):
            return CheckConfig(
                [f"--config={configfile}", "--quiet=1"],
                refresh=True,
                stdin=io.StringIO(),
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            )

    def assert_runtime_policy_parity(self, runtime_conf, policy_conf):
        """Compare stable effective policy fields across both code paths."""
        self.assertEqual(runtime_conf["warning_counter"], policy_conf["warning_counter"])
        self.assertEqual(runtime_conf["strict"], policy_conf["strict"])
        self.assertEqual(runtime_conf["path"], policy_conf["path"])
        self.assertEqual(
            set(runtime_conf["allowed_file_extensions"]),
            set(policy_conf["allowed_file_extensions"]),
        )
        self.assertEqual(
            set(runtime_conf["allowed_shell_escape"]),
            set(policy_conf["allowed_shell_escape"]),
        )
        self.assertEqual(set(runtime_conf["forbidden"]), set(policy_conf["forbidden"]))
        self.assertEqual(set(runtime_conf["overssh"]), set(policy_conf["overssh"]))
        self.assertEqual(set(runtime_conf["allowed"]), set(policy_conf["allowed"]))

    def test_parity_user_group_default_precedence_with_include_overlay(self):
        """PAR01 | Runtime and policy-show resolve same precedence and include overlays."""
        with tempfile.TemporaryDirectory() as tempdir:
            include_dir = os.path.join(tempdir, "lshell.d")
            os.makedirs(include_dir, exist_ok=True)

            allow_main = os.path.join(tempdir, "allow-main")
            allow_blocked = os.path.join(tempdir, "allow-blocked")
            allow_extra = os.path.join(tempdir, "allow-extra")
            for directory in [allow_main, allow_blocked, allow_extra]:
                os.makedirs(directory, exist_ok=True)

            configfile = self._write_config(
                tempdir,
                f"""
                [global]
                logpath : /tmp
                loglevel : 0
                include_dir : {include_dir}/conf.

                [default]
                allowed : ['base']
                allowed_shell_escape : ['ase_base']
                allowed_file_extensions : ['.log']
                forbidden : [';']
                overssh : ['scp']
                path : ['{tempdir}/allow-*']
                warning_counter : 2
                strict : 1
                """,
            )

            self._write_config(
                include_dir,
                """
                [default]
                allowed : ['base'] + ['include_default']
                forbidden : [';'] + ['#']
                """,
                filename="conf.10-default",
            )
            self._write_config(
                include_dir,
                f"""
                [grp:alpha]
                allowed : + ['group_alpha']
                allowed_shell_escape : + ['ase_group'] - ['ase_base']
                overssh : + ['rsync']
                forbidden : + ['|']
                path : - ['{allow_blocked}']
                """,
                filename="conf.20-group",
            )
            self._write_config(
                include_dir,
                f"""
                [alice]
                allowed : + ['user_only'] - ['base']
                allowed_file_extensions : + ['.txt'] - ['.log']
                path : + ['{allow_extra}']
                """,
                filename="conf.30-user",
            )

            runtime = self._runtime_checkconfig(
                configfile=configfile,
                username="alice",
                group_ids=[100, 200],
                gid_to_group={100: "alpha", 200: "beta"},
            )
            result = policy.resolve_policy(configfile, "alice", ["alpha", "beta"])

            self.assert_runtime_policy_parity(runtime.returnconf(), result["policy"])
            self.assertIn("include_default", result["policy"]["allowed"])
            self.assertIn("group_alpha", result["policy"]["allowed"])
            self.assertIn("user_only", result["policy"]["allowed"])
            self.assertNotIn("base", result["policy"]["allowed"])
            self.assertIn(f"{os.path.realpath(allow_blocked)}/|", result["policy"]["path"][1])

    def test_parity_allowed_all_minus_list(self):
        """PAR02 | allowed='all' with minus operation resolves identically."""
        with tempfile.TemporaryDirectory() as tempdir:
            configfile = self._write_config(
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

            runtime = self._runtime_checkconfig(
                configfile=configfile,
                username="alice",
                group_ids=[],
                gid_to_group={},
            )
            result = policy.resolve_policy(configfile, "alice", [])

            self.assert_runtime_policy_parity(runtime.returnconf(), result["policy"])
            self.assertIn("ls", result["policy"]["allowed"])
            self.assertNotIn("echo", result["policy"]["allowed"])

    def test_invalid_schema_type_error_behavior_preserved(self):
        """PAR03 | Runtime exits on schema failure while diagnostics raises ValueError."""
        with tempfile.TemporaryDirectory() as tempdir:
            configfile = self._write_config(
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

            with self.assertRaises(SystemExit):
                self._runtime_checkconfig(
                    configfile=configfile,
                    username="alice",
                    group_ids=[],
                    gid_to_group={},
                )

            with self.assertRaises(ValueError) as exc:
                policy.resolve_policy(configfile, "alice", [])
            self.assertIn("allowed", str(exc.exception))


if __name__ == "__main__":
    unittest.main()
