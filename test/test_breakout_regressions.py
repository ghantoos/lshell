"""Breakout regression coverage for command-policy bypass chains."""

import os
import tempfile
import unittest
from getpass import getuser

import pexpect

from lshell.engine import authorizer
from lshell.engine import reasons


TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"
LSHELL = f"{TOPDIR}/bin/lshell"
USER = getuser()
PROMPT = f"{USER}:~\\$"


class TestBreakoutRegressions(unittest.TestCase):
    """Security expectations that should fail while breakout remains unfixed."""

    def _policy(self):
        return {
            "allowed": ["echo"],
            "overssh": [],
            "forbidden": [],
            "strict": 1,
            "sudo_commands": [],
            "allowed_file_extensions": [],
            "path": ["/|", ""],
        }

    def _spawn_shell(self, extra_args=None, env=None):
        args = [
            "--config",
            CONFIG,
            "--strict",
            "1",
            "--forbidden",
            "[]",
            "--allowed",
            "['echo']",
            "--path_noexec",
            "''",
        ]
        if extra_args:
            args.extend(extra_args)
        child = pexpect.spawn(
            LSHELL,
            args=args,
            env=env,
            encoding="utf-8",
            timeout=10,
        )
        child.expect(PROMPT)
        return child

    def _run_command(self, child, command):
        child.sendline(command)
        child.expect(PROMPT)
        return child.before.split("\n", 1)[1]

    def _safe_exit(self, child):
        if not child.isalive():
            return
        child.sendline("exit")
        child.expect(pexpect.EOF)

    def test_authorizer_misses_nested_command_substitution_in_parameter_expansion(
        self,
    ):
        """Nested `$(...)` inside `${...}` must be denied by allowlist checks."""
        policy = self._policy()

        direct = authorizer.authorize_line(
            "echo $(id)",
            policy,
            mode="policy",
            check_current_dir=False,
        )
        nested = authorizer.authorize_line(
            "echo ${LSHELL_BREAKOUT_TEST:-$(id)}",
            policy,
            mode="policy",
            check_current_dir=False,
        )

        self.assertFalse(direct.allowed)
        self.assertEqual(direct.reason.code, reasons.FORBIDDEN_COMMAND)
        self.assertFalse(nested.allowed)
        self.assertEqual(nested.reason.code, reasons.FORBIDDEN_COMMAND)

    def test_interactive_breakout_executes_disallowed_command_via_parameter_expansion(
        self,
    ):
        """Interactive shell must block nested breakout payloads."""
        child = self._spawn_shell()
        try:
            denied = self._run_command(child, "id")
            self.assertIn('lshell: forbidden command: "id"', denied)

            breakout = self._run_command(
                child,
                "echo ${LSHELL_BREAKOUT_TEST:-$(id)}",
            )
            self.assertIn('lshell: forbidden command: "id"', breakout)
            self.assertNotRegex(breakout, r"uid=[0-9]+")
        finally:
            self._safe_exit(child)
            child.close(force=True)

    def test_interactive_blocks_source_function_import_breakout(
        self,
    ):
        """`source` must not allow env poisoning that triggers disallowed binaries."""
        envfile = None
        child = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix="lshell-breakout-",
                dir="/tmp",
                delete=False,
            ) as handle:
                handle.write("export BASH_FUNC_echo%%='() { id; }'\n")
                envfile = handle.name

            child = self._spawn_shell(extra_args=["--path", "['/tmp']"])

            denied = self._run_command(child, "id")
            self.assertIn('lshell: forbidden command: "id"', denied)

            self._run_command(child, f"source {envfile}")

            breakout = self._run_command(child, "echo harmless")
            self.assertNotRegex(breakout, r"uid=[0-9]+")
            self.assertIn("harmless", breakout)
        finally:
            if child is not None:
                self._safe_exit(child)
                child.close(force=True)
            if envfile and os.path.exists(envfile):
                os.unlink(envfile)

    def test_interactive_blocks_path_hijack_of_shell_interpreter(
        self,
    ):
        """Allowed commands must not execute attacker-controlled PATH `bash` binaries."""
        child = None
        with tempfile.TemporaryDirectory(prefix="lshell-path-hijack-", dir="/tmp") as tmpdir:
            bindir = os.path.join(tmpdir, "bin")
            os.makedirs(bindir, exist_ok=True)
            fake_bash = os.path.join(bindir, "bash")
            with open(fake_bash, "w", encoding="utf-8") as handle:
                handle.write("#!/bin/sh\n")
                handle.write("command -p id\n")
                handle.write('exec /bin/bash "$@"\n')
            os.chmod(fake_bash, 0o700)

            env = dict(os.environ)
            env["PATH"] = f"{bindir}:{env.get('PATH', '')}"
            child = self._spawn_shell(env=env)
            try:
                denied = self._run_command(child, "id")
                self.assertIn('lshell: forbidden command: "id"', denied)

                breakout = self._run_command(child, "echo harmless")
                self.assertNotRegex(breakout, r"uid=[0-9]+")
                self.assertIn("harmless", breakout)
            finally:
                self._safe_exit(child)
                child.close(force=True)


if __name__ == "__main__":
    unittest.main()
