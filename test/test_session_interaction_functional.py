"""Functional interaction regression tests for user-visible shell behavior."""

import os
import re
import tempfile
import textwrap
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

    def test_lps1_prompt_override_persists_across_prompt_refresh(self):
        """LPS1 environment prompt override should remain stable after commands."""
        custom_prompt = "LSHELL_PROMPT> "
        env = os.environ.copy()
        env["LPS1"] = custom_prompt

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
