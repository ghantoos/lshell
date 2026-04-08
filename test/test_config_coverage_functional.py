"""Functional and integration coverage for lshell configuration settings."""

import io
import json
import os
import re
import stat
import tempfile
import textwrap
import unittest
from getpass import getuser
from unittest.mock import patch

import pexpect

from lshell.config.runtime import CheckConfig
from lshell.config import diagnostics as policy


TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"
LSHELL = f"{TOPDIR}/bin/lshell"
USER = getuser()
PROMPT = f"{USER}:~\\$"


class TestConfigCoverageFunctional(unittest.TestCase):
    """Supplementary config-coverage tests focused on behavior contracts."""

    args = [f"--config={CONFIG}", "--quiet=1"]

    def setUp(self):
        self._saved_lshell_args = os.environ.get("LSHELL_ARGS")
        self._saved_lps1 = os.environ.get("LPS1")

    def tearDown(self):
        if self._saved_lshell_args is None:
            os.environ.pop("LSHELL_ARGS", None)
        else:
            os.environ["LSHELL_ARGS"] = self._saved_lshell_args

        if self._saved_lps1 is None:
            os.environ.pop("LPS1", None)
        else:
            os.environ["LPS1"] = self._saved_lps1

    def _write_config(self, directory, content, filename="lshell.conf"):
        path = os.path.join(directory, filename)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(textwrap.dedent(content).strip() + "\n")
        return path

    def _clean_env(self, extra=None):
        env = os.environ.copy()
        env.pop("LSHELL_ARGS", None)
        env.pop("LPS1", None)
        if extra:
            env.update(extra)
        return env

    def _spawn_shell_with_config(
        self,
        config_path,
        extra_args="",
        timeout=12,
        env=None,
        prompt=PROMPT,
    ):
        command = f"{LSHELL} --config {config_path} {extra_args}".strip()
        child = pexpect.spawn(
            command,
            encoding="utf-8",
            timeout=timeout,
            env=self._clean_env(env),
        )
        child.expect(prompt)
        return child

    def _safe_exit(self, child):
        if not child.isalive():
            return
        child.sendline("exit")
        try:
            child.expect(pexpect.EOF, timeout=4)
        except pexpect.TIMEOUT:
            child.close(force=True)

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
            checker = CheckConfig(
                [f"--config={configfile}", "--quiet=1"],
                refresh=True,
                stdin=io.StringIO(),
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            )
        return checker.returnconf()

    def test_global_log_settings_create_custom_log_file_and_logger_name(self):
        """Cover logpath/loglevel/logfilename/syslogname integration in runtime config."""
        with tempfile.TemporaryDirectory(prefix="lshell-log-coverage-") as logdir:
            conf = CheckConfig(
                self.args
                + [
                    f"--logpath={logdir}",
                    "--loglevel=4",
                    "--logfilename=cov-%u",
                    "--syslogname=coverage-syslog",
                ]
            ).returnconf()

            expected_log = os.path.join(logdir, f"cov-{USER}.log")
            self.assertTrue(os.path.isfile(expected_log))
            self.assertEqual(conf["loglevel"], 4)
            self.assertTrue(conf["logpath"].name.startswith("coverage-syslog."))

    def test_global_loglevel_is_clamped_to_supported_range(self):
        """Values outside 0..4 should clamp to the nearest valid loglevel."""
        high = CheckConfig(self.args + ["--loglevel=99"]).returnconf()
        low = CheckConfig(self.args + ["--loglevel=-7"]).returnconf()
        self.assertEqual(high["loglevel"], 4)
        self.assertEqual(low["loglevel"], 0)

    def test_include_dir_runtime_precedence_user_group_default(self):
        """Runtime loader should merge include_dir sections with user > group > default."""
        with tempfile.TemporaryDirectory(prefix="lshell-include-runtime-") as tempdir:
            include_dir = os.path.join(tempdir, "include.d")
            os.makedirs(include_dir, exist_ok=True)

            configfile = self._write_config(
                tempdir,
                f"""
                [global]
                logpath : /tmp
                loglevel : 0
                include_dir : {include_dir}/layer.

                [default]
                allowed : ['base']
                forbidden : [';']
                warning_counter : 2
                strict : 1
                """,
            )

            self._write_config(
                include_dir,
                """
                [default]
                allowed : + ['default_inc']
                """,
                filename="layer.10-default",
            )

            self._write_config(
                include_dir,
                """
                [grp:ops]
                allowed : + ['group_inc']
                """,
                filename="layer.20-group",
            )

            self._write_config(
                include_dir,
                """
                [alice]
                allowed : + ['user_inc'] - ['base']
                """,
                filename="layer.30-user",
            )

            conf = self._runtime_checkconfig(
                configfile=configfile,
                username="alice",
                group_ids=[1000],
                gid_to_group={1000: "ops"},
            )

            self.assertIn("default_inc", conf["allowed"])
            self.assertIn("group_inc", conf["allowed"])
            self.assertIn("user_inc", conf["allowed"])
            self.assertNotIn("base", conf["allowed"])

    def test_home_path_and_history_file_expand_username_placeholder(self):
        """home_path/history_file should resolve %u placeholders for the target user."""
        with tempfile.TemporaryDirectory(prefix="lshell-home-path-") as tempdir:
            alice_home = os.path.join(tempdir, "alice-home")
            os.makedirs(alice_home, exist_ok=True)
            configfile = self._write_config(
                tempdir,
                f"""
                [global]
                logpath : /tmp
                loglevel : 0

                [default]
                allowed : ['echo']
                forbidden : []
                warning_counter : 2
                strict : 0
                home_path : '{tempdir}/%u-home'
                history_file : '.hist_%u'
                """,
            )

            with (
                patch("lshell.config.runtime.getuser", return_value="alice"),
                patch("lshell.config.runtime.os.getgroups", return_value=[]),
            ):
                conf = CheckConfig(
                    [f"--config={configfile}", "--quiet=1"],
                    refresh=True,
                    stdin=io.StringIO(),
                    stdout=io.StringIO(),
                    stderr=io.StringIO(),
                ).returnconf()

            expected_home = os.path.join(tempdir, "alice-home")
            self.assertEqual(conf["home_path"], expected_home)
            self.assertEqual(conf["oldpwd"], expected_home)
            self.assertEqual(conf["history_file"], f"{expected_home}/.hist_alice")

    def test_custom_intro_is_displayed_before_first_prompt(self):
        """Configured intro string should be printed before interactive prompt."""
        with tempfile.TemporaryDirectory(prefix="lshell-intro-") as tempdir:
            configfile = self._write_config(
                tempdir,
                """
                [global]
                logpath : /tmp
                loglevel : 0

                [default]
                allowed : ['echo']
                forbidden : []
                warning_counter : 2
                strict : 0
                intro : 'COVERAGE_INTRO_MESSAGE'
                """,
            )

            child = pexpect.spawn(
                f"{LSHELL} --config {configfile}",
                encoding="utf-8",
                timeout=10,
                env=self._clean_env(),
            )
            try:
                child.expect(PROMPT)
                self.assertIn("COVERAGE_INTRO_MESSAGE", child.before)
                child.sendline("exit")
                child.expect(pexpect.EOF)
            finally:
                child.close(force=True)

    def test_quiet_is_parsed_and_rejects_non_integer_values(self):
        """quiet should parse as int and reject non-integer values."""
        conf = CheckConfig(self.args + ["--quiet=1"]).returnconf()
        self.assertEqual(conf["quiet"], 1)

        with self.assertRaises(SystemExit):
            CheckConfig(self.args + ["--quiet='loud'"]).returnconf()

    def test_messages_config_rejects_unsupported_keys_and_placeholders(self):
        """messages should reject unknown keys and unsupported placeholder fields."""
        with tempfile.TemporaryDirectory(prefix="lshell-messages-") as tempdir:
            invalid_key_config = self._write_config(
                tempdir,
                """
                [global]
                logpath : /tmp
                loglevel : 0

                [default]
                allowed : ['ls']
                forbidden : [';']
                warning_counter : 2
                messages : {'unsupported_key': 'x'}
                """,
                filename="invalid-key.conf",
            )

            invalid_placeholder_config = self._write_config(
                tempdir,
                """
                [global]
                logpath : /tmp
                loglevel : 0

                [default]
                allowed : ['ls']
                forbidden : [';']
                warning_counter : 2
                messages : {'unknown_syntax': 'bad {nope}'}
                """,
                filename="invalid-placeholder.conf",
            )

            with self.assertRaises(ValueError) as invalid_key_error:
                policy.resolve_policy(invalid_key_config, USER, [])
            self.assertIn("unsupported key", str(invalid_key_error.exception))

            with self.assertRaises(ValueError) as invalid_placeholder_error:
                policy.resolve_policy(invalid_placeholder_config, USER, [])
            self.assertIn("unsupported placeholders", str(invalid_placeholder_error.exception))

    def test_allowed_shell_escape_all_literal_is_rejected(self):
        """allowed_shell_escape=all must fail closed in policy resolution."""
        with tempfile.TemporaryDirectory(prefix="lshell-shell-escape-") as tempdir:
            configfile = self._write_config(
                tempdir,
                """
                [global]
                logpath : /tmp
                loglevel : 0

                [default]
                allowed : ['ls']
                allowed_shell_escape : all
                forbidden : [';']
                warning_counter : 2
                """,
            )

            with self.assertRaises(ValueError) as error:
                policy.resolve_policy(configfile, USER, [])
            self.assertIn("allowed_shell_escape", str(error.exception))
            self.assertIn("cannot be set to 'all'", str(error.exception))

    def test_runtime_executor_allowed_shell_escape_and_path_noexec_interaction(self):
        """shellless should still allow explicit shell escape when path_noexec is disabled."""
        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} "
            "--runtime_executor shellless "
            "--path_noexec \"''\" "
            "--allowed \"[]\" "
            "--allowed_shell_escape \"['echo']\" "
            "--forbidden \"[]\"",
            encoding="utf-8",
            timeout=10,
            env=self._clean_env(),
        )
        try:
            child.expect(PROMPT)
            child.sendline("echo SHELL_ESCAPE_OK")
            child.expect(PROMPT)
            output = child.before
            self.assertIn("SHELL_ESCAPE_OK", output)
            self._safe_exit(child)
        finally:
            child.close(force=True)

    def test_path_env_umask_and_env_file_interaction(self):
        """Combined path/env/umask controls should enforce predictable runtime behavior."""
        with tempfile.TemporaryDirectory(prefix="lshell-path-env-") as tempdir:
            home_path = os.path.join(tempdir, "home")
            bindir = os.path.join(tempdir, "bin")
            os.makedirs(home_path, exist_ok=True)
            os.makedirs(bindir, exist_ok=True)

            command_name = "cov_allowed_cmd"
            command_path = os.path.join(bindir, command_name)
            with open(command_path, "w", encoding="utf-8") as handle:
                handle.write("#!/bin/sh\n")
                handle.write("echo ALLOWED_CMD_PATH_AND_ENV_PATH_OK\n")
            os.chmod(command_path, 0o700)

            env_file = os.path.join(tempdir, "extra.env")
            with open(env_file, "w", encoding="utf-8") as handle:
                handle.write("export COV_RUNTIME_ENV=from_file\n")

            configfile = self._write_config(
                tempdir,
                f"""
                [global]
                logpath : /tmp
                loglevel : 0

                [default]
                allowed : ['echo', 'touch', '{command_name}']
                forbidden : []
                warning_counter : 2
                strict : 1
                path : ['{home_path}']
                home_path : '{home_path}'
                env_path : '{bindir}'
                allowed_cmd_path : ['{bindir}']
                env_vars : {{'COV_RUNTIME_ENV': 'from_conf'}}
                env_vars_files : ['{env_file}']
                umask : 0077
                """,
            )

            active_prompt = (
                rf"{re.escape(USER)}:"
                rf"(?:~|{re.escape(os.path.realpath(home_path))})\$"
            )
            child = self._spawn_shell_with_config(configfile, prompt=active_prompt)
            try:
                child.sendline("echo $COV_RUNTIME_ENV")
                child.expect(active_prompt)
                self.assertIn("from_file", child.before)

                child.sendline(command_name)
                child.expect(active_prompt)
                self.assertIn("ALLOWED_CMD_PATH_AND_ENV_PATH_OK", child.before)

                child.sendline("touch secret.txt")
                child.expect(active_prompt)
            finally:
                self._safe_exit(child)
                child.close(force=True)

            mode = stat.S_IMODE(os.stat(os.path.join(home_path, "secret.txt")).st_mode)
            self.assertEqual(mode, 0o600)

    def test_observability_interaction_custom_logfilename_with_json_audit(self):
        """Logpath/loglevel/logfilename/audit-json should emit ECS command events to custom file."""
        with tempfile.TemporaryDirectory(prefix="lshell-observability-") as log_dir:
            child = pexpect.spawn(
                f"{LSHELL} --config {CONFIG} --log {log_dir} "
                "--loglevel=4 --logfilename=coverage-%u --security_audit_json=1 "
                "--strict 0",
                encoding="utf-8",
                timeout=10,
                env=self._clean_env(),
            )
            try:
                child.expect(PROMPT)
                child.sendline("echo OBSERVABILITY_OK")
                child.expect(PROMPT)
                child.sendline("exit")
                child.expect(pexpect.EOF)
            finally:
                child.close(force=True)

            logfile = os.path.join(log_dir, f"coverage-{USER}.log")
            self.assertTrue(os.path.exists(logfile))

            events = []
            with open(logfile, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if payload.get("event.action") == "command_authorization":
                        events.append(payload)

            success_events = [
                event
                for event in events
                if event.get("process.command_line") == "echo OBSERVABILITY_OK"
                and event.get("event.outcome") == "success"
            ]
            self.assertTrue(success_events, msg=f"missing command event in {events}")

    def test_lshow_always_available_while_aliases_expand(self):
        """Legacy policy_commands key must not hide lshow; aliases should still expand."""
        with tempfile.TemporaryDirectory(prefix="lshell-lshow-always-") as tempdir:
            configfile = self._write_config(
                tempdir,
                """
                [global]
                logpath : /tmp
                loglevel : 0

                [default]
                allowed : ['echo']
                forbidden : []
                warning_counter : 3
                strict : 0
                aliases : {'sayhi':'echo ALIAS_OK'}
                policy_commands : 0
                """,
            )

            child = self._spawn_shell_with_config(configfile, "--quiet 1")
            try:
                child.sendline("sayhi")
                child.expect(PROMPT)
                self.assertIn("ALIAS_OK", child.before)

                child.sendline("lshow echo visible")
                child.expect(PROMPT)
                output = child.before
                self.assertIn("Command       : echo visible", output)
                self.assertIn("Decision      :", output)
                self.assertIn("ALLOW", output)
            finally:
                self._safe_exit(child)
                child.close(force=True)


if __name__ == "__main__":
    unittest.main()
