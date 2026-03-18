"""Functional tests for runtime containment limits."""

import os
import tempfile
import unittest
from getpass import getuser

import pexpect


TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"
LSHELL = f"{TOPDIR}/bin/lshell"
USER = getuser()
PROMPT = f"{USER}:~\\$"


class TestRuntimeContainmentFunctional(unittest.TestCase):
    """Validate runtime containment limits in a real shell session."""

    def _spawn_shell(self, extra_args, env=None, timeout=15):
        command = f"{LSHELL} --config {CONFIG} {extra_args}"
        return pexpect.spawn(command, encoding="utf-8", timeout=timeout, env=env)

    def _env_with(self, **extra):
        env = os.environ.copy()
        env.update(extra)
        return env

    def _safe_exit(self, child):
        if not child.isalive():
            return
        child.sendline("exit")
        try:
            child.expect(pexpect.EOF, timeout=3)
            return
        except pexpect.TIMEOUT:
            pass

        if child.isalive():
            child.sendline("exit")
            child.expect(pexpect.EOF, timeout=5)

    def test_max_sessions_per_user_enforced(self):
        """Deny second concurrent shell when max_sessions_per_user is exceeded."""
        with tempfile.TemporaryDirectory(prefix="lshell-session-func-") as session_dir:
            env = self._env_with(LSHELL_SESSION_DIR=session_dir)
            first = self._spawn_shell("--max_sessions_per_user 1 --strict 1", env=env)
            second = None
            try:
                first.expect(PROMPT)

                second = self._spawn_shell(
                    "--max_sessions_per_user 1 --strict 1",
                    env=env,
                )
                second.expect(pexpect.EOF)
                output = second.before
                self.assertIn("session denied", output)
                self.assertIn("max_sessions_per_user=1", output)
            finally:
                if second is not None:
                    second.close(force=True)
                self._safe_exit(first)

    def test_max_background_jobs_enforced(self):
        """Deny new background command when max_background_jobs is reached."""
        child = self._spawn_shell(
            "--strict 1 --forbidden \"[]\" --allowed \"['sleep']\" "
            "--max_background_jobs 1"
        )
        try:
            child.expect(PROMPT)
            child.sendline("sleep 60 &")
            child.expect(PROMPT)

            child.sendline("sleep 60 &")
            child.expect(PROMPT)
            output = child.before
            self.assertIn("background job denied", output)
            self.assertIn("max_background_jobs=1", output)
        finally:
            self._safe_exit(child)


if __name__ == "__main__":
    unittest.main()
