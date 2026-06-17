"""Functional interaction regression tests for user-visible shell behavior."""

import os
import re
import tempfile
import textwrap
import time
import unittest
from getpass import getuser

import pexpect


TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"
LSHELL = f"{TOPDIR}/bin/lshell"
USER = getuser()
PROMPT = f"{USER}:~\\$"


class TestSessionInteractionFunctional(unittest.TestCase):
    """Cover session lifecycle and user-facing interaction edge cases."""

    def _clean_env(self, extra=None):
        """Return a sanitized environment for deterministic subprocess behavior."""
        env = os.environ.copy()
        env.pop("LSHELL_ARGS", None)
        env.pop("LPS1", None)
        if extra:
            env.update(extra)
        return env

    def _spawn_shell(self, extra_args="", env=None, timeout=10, prompt=PROMPT):
        command = f"{LSHELL} --config {CONFIG} {extra_args}".strip()
        child = pexpect.spawn(
            command,
            encoding="utf-8",
            timeout=timeout,
            env=self._clean_env(env),
        )
        child.expect(prompt)
        return child

    def _run_command(self, child, command, prompt=PROMPT):
        child.sendline(command)
        child.expect(prompt)
        return child.before.split("\n", 1)[1]

    def _safe_exit(self, child):
        if not child.isalive():
            return
        child.sendline("exit")
        try:
            child.expect(pexpect.EOF, timeout=3)
        except pexpect.TIMEOUT:
            child.close(force=True)

    def _last_non_empty_line(self, text):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return lines[-1] if lines else ""

    def test_login_script_runs_before_first_prompt(self):
        """Startup login_script should execute before the first interactive prompt."""
        with tempfile.TemporaryDirectory(prefix="lshell-login-script-") as tempdir:
            config_path = os.path.join(tempdir, "lshell.conf")
            with open(config_path, "w", encoding="utf-8") as handle:
                handle.write(
                    textwrap.dedent(
                        """
                        [global]
                        logpath : /tmp
                        loglevel : 0

                        [default]
                        allowed : ['echo']
                        forbidden : []
                        warning_counter : 2
                        strict : 0
                        login_script : 'echo LOGIN_SCRIPT_RAN'
                        """
                    ).strip()
                    + "\n"
                )

            child = pexpect.spawn(
                f"{LSHELL} --config {config_path}",
                encoding="utf-8",
                timeout=10,
                env=self._clean_env(),
            )
            try:
                child.expect(PROMPT)
                startup = child.before
                self.assertIn("LOGIN_SCRIPT_RAN", startup)
                child.sendline("exit")
                child.expect(pexpect.EOF)
            finally:
                child.close(force=True)

    def test_quit_exits_session(self):
        """`quit` should terminate the session like `exit`."""
        child = self._spawn_shell()
        try:
            child.sendline("quit")
            child.expect(pexpect.EOF)
        finally:
            child.close(force=True)

    def test_ctrl_d_exits_session_without_stopped_jobs(self):
        """Ctrl-D on an idle prompt should exit the shell."""
        child = self._spawn_shell()
        try:
            child.sendeof()
            child.expect(pexpect.EOF)
        finally:
            child.close(force=True)

    def test_disable_exit_blocks_quit_and_ctrl_d(self):
        """disable_exit should keep session alive for both quit and Ctrl-D."""
        child = self._spawn_shell("--disable_exit 1")
        try:
            child.sendline("quit")
            child.expect(PROMPT)

            child.sendeof()
            child.expect(PROMPT)

            output = self._run_command(child, "echo STILL_HERE")
            self.assertIn("STILL_HERE", output)
        finally:
            child.close(force=True)

    def test_timer_expiry_prints_message_and_ends_session(self):
        """Timer expiry should end session with the user-facing timeout message."""
        child = self._spawn_shell("--timer 1", timeout=12)
        try:
            child.expect("Time is up\\.", timeout=8)
            child.expect(pexpect.EOF, timeout=5)
        finally:
            child.close(force=True)

    def test_unknown_command_user_message_differs_by_strict_mode(self):
        """Unknown-command output should differ between strict and non-strict modes."""
        non_strict = self._spawn_shell("--strict 0 --warning_counter 2 --quiet 0")
        try:
            non_strict_output = self._run_command(non_strict, "id")
            self.assertIn("lshell: unknown syntax: id", non_strict_output)
            self.assertNotIn("lshell: warning:", non_strict_output)
        finally:
            self._safe_exit(non_strict)
            non_strict.close(force=True)

        strict = self._spawn_shell("--strict 1 --warning_counter 2 --quiet 0")
        try:
            strict_output = self._run_command(strict, "id")
            self.assertIn('lshell: forbidden command: "id"', strict_output)
            self.assertIn("lshell: warning: 1 violation remaining", strict_output)
        finally:
            self._safe_exit(strict)
            strict.close(force=True)

    def test_up_down_arrows_search_history_by_current_prefix(self):
        """Up/down arrows should recall history entries matching the typed prefix."""
        def run_sequence(*keys):
            history_path = None
            child = None
            try:
                with tempfile.NamedTemporaryFile(
                    "w",
                    encoding="utf-8",
                    delete=False,
                    prefix="lshell-history-search-",
                ) as history_file:
                    history_file.write("echo alpha\n")
                    history_file.write("help\n")
                    history_file.write("echo alpha beta\n")
                    history_path = history_file.name

                child = self._spawn_shell(
                    "--allowed \"['echo', 'help']\" "
                    '--forbidden "[]" '
                    "--strict 0 "
                    f"--history_file='{history_path}'"
                )
                child.send("echo a")
                for key in keys:
                    child.send(key)
                child.sendline("")
                child.expect(PROMPT)
                return child.before.replace("\r", "").replace("\x08", "")
            finally:
                if child is not None:
                    self._safe_exit(child)
                    child.close(force=True)
                if history_path and os.path.exists(history_path):
                    os.unlink(history_path)

        latest_match = run_sequence("\x1b[A")
        self.assertRegex(latest_match, r"(?m)^alpha beta$")

        older_match = run_sequence("\x1b[A", "\x1b[A")
        self.assertRegex(older_match, r"(?m)^alpha$")

        forward_match = run_sequence("\x1b[A", "\x1b[A", "\x1b[B")
        self.assertRegex(forward_match, r"(?m)^alpha beta$")

    def test_history_command_persists_deduplicated_normalized_entries(self):
        """History output should apply duplicate removal and blank reduction policies."""
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            delete=False,
            prefix="lshell-history-policies-",
        ) as history_file:
            history_path = history_file.name

        child = self._spawn_shell(
            "--allowed \"['echo', 'history']\" "
            '--forbidden "[]" '
            "--strict 0 "
            f"--history_file='{history_path}'"
        )
        try:
            self._run_command(child, "echo    alpha")
            self._run_command(child, "echo beta")
            self._run_command(child, "echo alpha")
            history_output = self._run_command(child, "history")

            self.assertEqual(history_output.count("echo alpha"), 1)
            self.assertEqual(history_output.count("echo beta"), 1)
            self.assertNotIn("echo    alpha", history_output)
        finally:
            self._safe_exit(child)
            child.close(force=True)
            if os.path.exists(history_path):
                os.unlink(history_path)

    def test_ctrl_d_does_not_persist_literal_eof_into_history(self):
        """Ctrl-D should exit cleanly without rewriting the last history entry as EOF."""
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            delete=False,
            prefix="lshell-history-eof-",
        ) as history_file:
            history_file.write("echo seed\n")
            history_path = history_file.name

        child = self._spawn_shell(
            "--allowed \"['echo']\" "
            '--forbidden "[]" '
            "--strict 0 "
            f"--history_file='{history_path}'"
        )
        try:
            self._run_command(child, "echo keep")
            child.sendeof()
            child.expect(pexpect.EOF)
        finally:
            child.close(force=True)

        try:
            with open(history_path, "r", encoding="utf-8") as handle:
                persisted = handle.read()
            self.assertIn("echo keep", persisted)
            self.assertNotIn("EOF", persisted)
        finally:
            if os.path.exists(history_path):
                os.unlink(history_path)

    def test_bg_builtin_reports_not_supported(self):
        """`bg` should report explicit unsupported status to the user."""
        child = self._spawn_shell()
        try:
            output = self._run_command(child, "bg")
            self.assertIn("lshell: bg not supported", output)
        finally:
            self._safe_exit(child)
            child.close(force=True)

    def test_lshow_allowed_command_sets_shell_visible_success(self):
        """Allowed `lshow <command>` decision should leave a success exit status."""
        child = self._spawn_shell('--forbidden "[]" --strict 0')
        try:
            allow_output = self._run_command(child, "lshow echo HELLO")
            self.assertIn("Command       : echo HELLO", allow_output)
            self.assertIn("Decision      :", allow_output)
            self.assertIn("ALLOW", allow_output)

            allow_status = self._run_command(child, "echo $?")
            self.assertEqual(self._last_non_empty_line(allow_status), "0")
        finally:
            self._safe_exit(child)
            child.close(force=True)

    def test_lshow_denied_command_prints_decision_and_ends_session(self):
        """Denied `lshow <command>` should print decision and terminate session."""
        child = self._spawn_shell('--forbidden "[]" --strict 0')
        try:
            child.sendline("lshow id")
            child.expect(pexpect.EOF)
            output = child.before
            self.assertIn("Command       : id", output)
            self.assertIn("Decision      :", output)
            self.assertIn("DENY", output)
        finally:
            child.close(force=True)

    def test_forbidden_sudo_subcommand_shows_policy_denial(self):
        """Unauthorized sudo subcommand should be denied with user-visible warning text."""
        child = self._spawn_shell(
            "--allowed \"['sudo']\" "
            "--sudo_commands \"['ls']\" "
            "--forbidden \"[]\" "
            "--strict 1 --warning_counter 2 --quiet 0"
        )
        try:
            output = self._run_command(child, "sudo cat /etc/passwd")
            self.assertIn(
                'lshell: forbidden sudo command: "sudo cat /etc/passwd"',
                output,
            )
            self.assertIn("lshell: warning: 1 violation remaining", output)
        finally:
            self._safe_exit(child)
            child.close(force=True)

    def test_alias_expansion_smuggling_is_blocked_and_session_recovers(self):
        """Alias expansion should not bypass forbidden-operator enforcement."""
        child = self._spawn_shell(
            "--strict 1 --warning_counter 5 --quiet 0 "
            "--aliases \"{'safe':'echo SAFE; id'}\""
        )
        try:
            attack_output = self._run_command(child, "safe")
            self.assertIn('lshell: forbidden character: ";"', attack_output)
            self.assertNotIn("uid=", attack_output)

            post_attack = self._run_command(child, "echo AFTER_ALIAS_BLOCK")
            self.assertIn("AFTER_ALIAS_BLOCK", post_attack)
        finally:
            self._safe_exit(child)
            child.close(force=True)

    def test_forbidden_environment_assignments_ld_family_and_tmpdir(self):
        """Dangerous env assignment prefixes should be blocked and shell should stay usable."""
        child = self._spawn_shell(
            "--strict 1 --warning_counter 5 --quiet 0 "
            "--forbidden \"[]\" --allowed \"+['printenv','echo']\""
        )
        try:
            for var_name in ("LD_PRELOAD", "LD_LIBRARY_PATH", "TMPDIR"):
                with self.subTest(var_name=var_name):
                    output = self._run_command(
                        child,
                        f"{var_name}=/tmp printenv {var_name}",
                    )
                    self.assertIn(
                        f"lshell: forbidden environment variable: {var_name}",
                        output,
                    )
                    lines = [line.strip() for line in output.splitlines() if line.strip()]
                    self.assertNotIn("/tmp", lines)

            post_attack = self._run_command(child, "echo ENV_GUARD_OK")
            self.assertIn("ENV_GUARD_OK", post_attack)
        finally:
            self._safe_exit(child)
            child.close(force=True)

    def test_assignment_only_command_persists_in_live_session(self):
        """Assignment-only input should update interactive shell env and chained command view."""
        child = self._spawn_shell('--strict 1 --forbidden "[]" --allowed "+[\'echo\']"')
        try:
            assignment_output = self._run_command(child, "LSHELL_INTERACTIVE_ASSIGN=LIVE")
            self.assertEqual(self._last_non_empty_line(assignment_output), "")

            value_output = self._run_command(child, "echo $LSHELL_INTERACTIVE_ASSIGN")
            self.assertEqual(self._last_non_empty_line(value_output), "LIVE")

            chained_output = self._run_command(
                child,
                "LSHELL_CHAIN_ASSIGN=CHAINED && echo $LSHELL_CHAIN_ASSIGN",
            )
            self.assertEqual(self._last_non_empty_line(chained_output), "CHAINED")
        finally:
            self._safe_exit(child)
            child.close(force=True)

    def test_config_reload_applies_new_policy_mid_session(self):
        """Config mtime change should reload policy and affect next user command."""
        with tempfile.TemporaryDirectory(prefix="lshell-config-reload-") as tempdir:
            config_path = os.path.join(tempdir, "lshell.conf")

            def write_config(allowed):
                with open(config_path, "w", encoding="utf-8") as handle:
                    handle.write(
                        textwrap.dedent(
                            f"""
                            [global]
                            logpath : /tmp
                            loglevel : 0

                            [default]
                            allowed : {allowed}
                            forbidden : []
                            warning_counter : 5
                            strict : 1
                            """
                        ).strip()
                        + "\n"
                    )

            write_config("['echo']")
            child = pexpect.spawn(
                f"{LSHELL} --config {config_path}",
                encoding="utf-8",
                timeout=10,
                env=self._clean_env(),
            )
            try:
                child.expect(PROMPT)

                first_attempt = self._run_command(child, "id")
                self.assertIn('lshell: forbidden command: "id"', first_attempt)

                # Config reload check uses mtime comparison; ensure a visible timestamp bump.
                time.sleep(1.1)
                write_config("['echo','id']")
                os.utime(config_path, None)

                second_attempt = self._run_command(child, "id")
                self.assertIn("uid=", second_attempt)
            finally:
                self._safe_exit(child)
                child.close(force=True)

    def test_leading_trailing_operator_sequences_fail_closed(self):
        """Leading/trailing operators should not execute payloads and should show syntax denial."""
        child = self._spawn_shell('--strict 0 --forbidden "[]" --allowed "+[\'echo\']"')
        try:
            leading = self._run_command(child, "|| echo PAYLOAD")
            self.assertIn("lshell: unknown syntax:", leading)
            leading_lines = [line.strip() for line in leading.splitlines() if line.strip()]
            self.assertNotIn("PAYLOAD", leading_lines)

            trailing = self._run_command(child, "echo SAFE &&")
            self.assertIn("lshell: unknown syntax:", trailing)

            post_probe = self._run_command(child, "echo AFTER_OPERATOR_PROBE")
            self.assertIn("AFTER_OPERATOR_PROBE", post_probe)
        finally:
            self._safe_exit(child)
            child.close(force=True)

    def test_allowed_cmd_path_resolves_and_allows_executable(self):
        """allowed_cmd_path should expose discovered binaries as runnable allowed commands."""
        with tempfile.TemporaryDirectory(prefix="lshell-allowed-cmd-path-") as bindir:
            command_name = "lshell_allowed_cmd_probe"
            script_path = os.path.join(bindir, command_name)
            with open(script_path, "w", encoding="utf-8") as handle:
                handle.write("#!/bin/sh\necho ALLOWED_CMD_PATH_OK\n")
            os.chmod(script_path, 0o700)

            child = self._spawn_shell(
                f'--forbidden "[]" --allowed "[]" --allowed_cmd_path "[\'{bindir}\']"'
            )
            try:
                output = self._run_command(child, command_name)
                self.assertIn("ALLOWED_CMD_PATH_OK", output)
            finally:
                self._safe_exit(child)
                child.close(force=True)

    def test_env_path_resolves_allowed_command_binary(self):
        """env_path should extend PATH for allowed command lookup in live session."""
        with tempfile.TemporaryDirectory(prefix="lshell-env-path-") as bindir:
            command_name = "lshell_env_path_probe"
            script_path = os.path.join(bindir, command_name)
            with open(script_path, "w", encoding="utf-8") as handle:
                handle.write("#!/bin/sh\necho ENV_PATH_OK\n")
            os.chmod(script_path, 0o700)

            child = self._spawn_shell(
                f'--forbidden "[]" --allowed "[\'{command_name}\']" --env_path {bindir}'
            )
            try:
                output = self._run_command(child, command_name)
                self.assertIn("ENV_PATH_OK", output)
            finally:
                self._safe_exit(child)
                child.close(force=True)

    def test_inherited_path_does_not_hijack_allowed_command_resolution(self):
        """Ambient PATH should not shadow an allowed command with a rogue binary."""
        with tempfile.TemporaryDirectory(prefix="lshell-path-shadow-") as bindir:
            script_path = os.path.join(bindir, "ls")
            with open(script_path, "w", encoding="utf-8") as handle:
                handle.write("#!/bin/sh\necho PWNED_STARTUP_PATH\n")
            os.chmod(script_path, 0o700)

            child = self._spawn_shell(
                "--allowed \"['ls']\" --strict 0",
                env={"PATH": f"{bindir}:{os.environ.get('PATH', '')}"},
            )
            try:
                output = self._run_command(child, "ls")
                self.assertNotIn("PWNED_STARTUP_PATH", output)
            finally:
                self._safe_exit(child)
                child.close(force=True)

    def test_command_resolution_drift_blocks_bare_command_after_session_start(self):
        """Replacing an allowlisted bare command mid-session should fail closed."""
        with tempfile.TemporaryDirectory(prefix="lshell-command-drift-") as bindir:
            command_name = "lshell_drift_probe"
            script_path = os.path.join(bindir, command_name)
            with open(script_path, "w", encoding="utf-8") as handle:
                handle.write("#!/bin/sh\necho SAFE_START\n")
            os.chmod(script_path, 0o700)

            child = self._spawn_shell(
                f'--forbidden "[]" --allowed "[\'{command_name}\']" --env_path {bindir}'
            )
            try:
                initial_output = self._run_command(child, command_name)
                self.assertIn("SAFE_START", initial_output)

                replacement_path = os.path.join(bindir, f"{command_name}.new")
                with open(replacement_path, "w", encoding="utf-8") as handle:
                    handle.write("#!/bin/sh\necho PWNED_AFTER_SWAP\n")
                os.chmod(replacement_path, 0o700)
                os.replace(replacement_path, script_path)

                drift_output = self._run_command(child, command_name)
                self.assertIn(
                    f'lshell: command path changed since session start: "{command_name}"',
                    drift_output,
                )
                self.assertNotIn("PWNED_AFTER_SWAP", drift_output)
            finally:
                self._safe_exit(child)
                child.close(force=True)

    def test_malformed_sudo_dash_u_is_denied_and_session_recovers(self):
        """Malformed `sudo -u` forms should be denied without killing the session."""
        child = self._spawn_shell(
            "--allowed \"['sudo','echo']\" "
            "--sudo_commands \"['ls']\" "
            "--forbidden \"[]\" "
            "--strict 1 --warning_counter 5 --quiet 0"
        )
        try:
            for malformed in ("sudo -u", "sudo -u root"):
                with self.subTest(malformed=malformed):
                    output = self._run_command(child, malformed)
                    self.assertIn(f'lshell: forbidden sudo command: "{malformed}"', output)

            post_probe = self._run_command(child, "echo SUDO_MALFORMED_OK")
            self.assertIn("SUDO_MALFORMED_OK", post_probe)
        finally:
            self._safe_exit(child)
            child.close(force=True)

    def test_lps1_prompt_override_persists_across_prompt_refresh(self):
        """LPS1 environment prompt override should remain stable after commands."""
        custom_prompt = "LSHELL_PROMPT> "
        env = {"LPS1": custom_prompt}

        child = self._spawn_shell(env=env, prompt=re.escape(custom_prompt))
        try:
            child.sendline("cd /tmp")
            child.expect(re.escape(custom_prompt))

            child.sendline("echo PROMPT_OK")
            child.expect(re.escape(custom_prompt))
            self.assertIn("PROMPT_OK", child.before)
        finally:
            child.close(force=True)


if __name__ == "__main__":
    unittest.main()
