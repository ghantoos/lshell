"""Functional attacker/sysadmin behavior tests for lshell sessions."""

import os
import unittest
from getpass import getuser

import pexpect


TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"
LSHELL = f"{TOPDIR}/bin/lshell"
USER = getuser()
PROMPT = f"{USER}:~\\$"


class TestUserBehaviorSecurityFunctional(unittest.TestCase):
    """End-to-end tests that mimic realistic operator and attacker behavior."""

    def _spawn_shell(self, extra_args=""):
        """Spawn lshell and wait for prompt."""
        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} {extra_args}",
            encoding="utf-8",
            timeout=10,
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
            self.assertIn('*** forbidden character: ";"', first_probe)
            self.assertIn("1 warning(s) left", first_probe)

            second_probe = self._run_command(child, "id")
            self.assertIn('*** forbidden command: "id"', second_probe)
            self.assertIn("0 warning(s) left", second_probe)

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
            self.assertIn("*** forbidden environment variable: PATH", hijack_attempt)

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
            self.assertIn("*** unknown syntax:", smuggling_attempt)
            self.assertFalse(
                self._contains_standalone_line(smuggling_attempt, "PWNED"),
                msg="payload output should not execute for malformed operator chains",
            )

            post_attack = self._run_command(child, "echo AFTER")
            self.assertIn("AFTER", post_attack)
            self._exit_shell(child)
        finally:
            child.close()
