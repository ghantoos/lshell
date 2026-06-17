"""Functional attacker/sysadmin behavior tests for lshell sessions."""

import os
import tempfile
import unittest
from getpass import getuser

import pexpect


TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"
LSHELL = f"{TOPDIR}/bin/lshell"
SOURCE_FIXTURE = f"{TOPDIR}/test/testfiles/source_command_fixture.lsh"
USER = getuser()
PROMPT = f"{USER}:~\\$"


class TestUserBehaviorSecurityFunctional(unittest.TestCase):
    """End-to-end tests that mimic realistic operator and attacker behavior."""

    def _spawn_shell(self, extra_args="", env=None):
        """Spawn lshell and wait for prompt."""
        child_env = os.environ.copy()
        if env:
            child_env.update(env)
        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} {extra_args}",
            encoding="utf-8",
            timeout=10,
            env=child_env,
        )
        child.expect(PROMPT)
        return child

    def _run_command(self, child, command):
        """Run one command and return command output block."""
        child.sendline(command)
        child.expect(PROMPT)
        return child.before.split("\n", 1)[1].strip()

    def _contains_standalone_line(self, text, expected_line):
        """Return True when expected_line appears as its own output line."""
        return expected_line in [line.strip() for line in text.splitlines()]

    def _exit_shell(self, child):
        """Exit shell session and wait for EOF."""
        if not child.isalive():
            return
        child.sendline("exit")
        child.expect(pexpect.EOF)

    def test_hacker_session_exhausts_warning_budget_and_is_kicked(self):
        """Repeated policy violations should consume warnings and terminate session."""
        child = self._spawn_shell("--strict 1 --warning_counter 2 --quiet 0")
        try:
            first_probe = self._run_command(child, "echo SAFE; echo PWN")
            self.assertIn('lshell: forbidden character: ";"', first_probe)
            self.assertIn("lshell: warning: 1 violation", first_probe)

            second_probe = self._run_command(child, "id")
            self.assertIn('lshell: forbidden command: "id"', second_probe)
            self.assertIn("lshell: warning: 0 violations", second_probe)

            child.sendline("id")
            child.expect(pexpect.EOF)
            child.close()
            self.assertEqual(child.exitstatus, 1)
        finally:
            child.close()

    def test_inline_path_hijack_attempt_is_blocked_and_session_continues(self):
        """PATH=... command prefix should be rejected as forbidden env manipulation."""
        child = self._spawn_shell("--strict 0 --forbidden \"[]\" --allowed \"+['id']\"")
        try:
            hijack_attempt = self._run_command(child, "PATH=/tmp id")
            self.assertIn("lshell: forbidden environment variable: PATH", hijack_attempt)

            still_usable = self._run_command(child, "echo still_here")
            self.assertIn("still_here", still_usable)
            self._exit_shell(child)
        finally:
            child.close()

    def test_operator_smuggling_is_rejected_without_running_payload(self):
        """Malformed operator chains should fail closed and skip payload execution."""
        child = self._spawn_shell("--strict 0 --forbidden \"[]\" --allowed \"+['printf']\"")
        try:
            smuggling_attempt = self._run_command(child, "printf SAFE ||| printf PWNED")
            self.assertIn("lshell: unknown syntax:", smuggling_attempt)
            self.assertFalse(
                self._contains_standalone_line(smuggling_attempt, "PWNED"),
                msg="payload output should not execute for malformed operator chains",
            )

            post_attack = self._run_command(child, "echo AFTER")
            self.assertIn("AFTER", post_attack)
            self._exit_shell(child)
        finally:
            child.close()

    def test_source_is_blocked_by_default_but_shell_remains_usable(self):
        """Interactive source should require explicit admin opt-in."""
        child = self._spawn_shell("--strict 0")
        try:
            body = self._run_command(child, f"source {SOURCE_FIXTURE}")
            self.assertIn("lshell: unknown syntax: source", body)

            still_usable = self._run_command(child, "echo STILL_OK")
            self.assertIn("STILL_OK", still_usable)
            self._exit_shell(child)
        finally:
            child.close()

    def test_export_rejects_shellopts_and_session_recovers(self):
        """Dangerous bash-control variables should be rejected interactively."""
        child = self._spawn_shell("--strict 0 --forbidden \"[]\" --allowed \"+['export']\"")
        try:
            body = self._run_command(child, "export SHELLOPTS=xtrace")
            self.assertIn("lshell: forbidden environment variable: SHELLOPTS", body)

            still_usable = self._run_command(child, "echo AFTER_BLOCK")
            self.assertIn("AFTER_BLOCK", still_usable)
            self._exit_shell(child)
        finally:
            child.close()

    def test_lshell_args_env_cannot_override_active_config(self):
        """External LSHELL_ARGS must not be able to swap in a weaker config."""
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".conf") as handle:
            handle.write(
                "[global]\n"
                "logpath : /tmp/lshell-logs/\n\n"
                "[default]\n"
                "allowed : ['echo','id']\n"
                "forbidden : [';','&','|','`','>','<','$(','${']\n"
                "warning_counter : 2\n"
                "strict : 0\n"
            )
            malicious_config = handle.name

        try:
            child = self._spawn_shell(
                "--strict 0",
                env={"LSHELL_ARGS": f"['--config', '{malicious_config}']"},
            )
            try:
                body = self._run_command(child, "id")
                self.assertIn("lshell:", body)
                self.assertIn("id", body)
                self.assertNotIn("uid=", body)
            finally:
                self._exit_shell(child)
        finally:
            os.remove(malicious_config)
