"""Functional tests for structured security audit logging."""

import json
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


class TestAuditFunctional(unittest.TestCase):
    """Validate ECS audit events from a real interactive shell session."""

    def _load_command_events(self, logfile):
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
        return events

    def test_security_audit_json_emits_allowed_and_denied_events(self):
        """Emit structured events with success/failure outcomes and reasons."""
        with tempfile.TemporaryDirectory(prefix="lshell-audit-log-") as log_dir:
            child = pexpect.spawn(
                f"{LSHELL} --config {CONFIG} --log {log_dir} --security_audit_json=1 "
                "--loglevel 4 --strict 0",
                encoding="utf-8",
                timeout=10,
            )
            try:
                child.expect(PROMPT)

                child.sendline("echo AUDIT_OK")
                child.expect(PROMPT)

                child.sendline("id")
                child.expect(PROMPT)

                child.sendline("exit")
                child.expect(pexpect.EOF)
            finally:
                child.close()

            logfile = os.path.join(log_dir, f"{USER}.log")
            self.assertTrue(os.path.exists(logfile))

            events = self._load_command_events(logfile)

            self.assertGreaterEqual(len(events), 2)

            allowed = [
                event
                for event in events
                if event.get("process.command_line") == "echo AUDIT_OK"
                and event.get("event.outcome") == "success"
            ]
            denied = [
                event
                for event in events
                if event.get("process.command_line") == "id"
                and event.get("event.outcome") == "failure"
            ]

            self.assertTrue(allowed, msg=f"missing allowed audit event in {events}")
            self.assertTrue(denied, msg=f"missing denied audit event in {events}")
            self.assertIn("unknown syntax", denied[0].get("event.reason", ""))

    def test_runtime_limit_denial_reason_is_machine_readable_in_audit(self):
        """Denied runtime-limit actions should emit machine-readable reason strings."""
        with tempfile.TemporaryDirectory(prefix="lshell-audit-log-") as log_dir:
            with tempfile.TemporaryDirectory(prefix="lshell-audit-session-") as session_dir:
                env = os.environ.copy()
                env["LSHELL_SESSION_DIR"] = session_dir
                child = pexpect.spawn(
                    f"{LSHELL} --config {CONFIG} --log {log_dir} --security_audit_json=1 "
                    "--loglevel 4 --strict 1 --forbidden \"[]\" --allowed \"['sleep']\" "
                    "--max_background_jobs 1",
                    encoding="utf-8",
                    timeout=10,
                    env=env,
                )
                try:
                    child.expect(PROMPT)
                    child.sendline("sleep 60 &")
                    child.expect(PROMPT)
                    child.sendline("sleep 60 &")
                    child.expect(PROMPT)
                    child.sendline("exit")
                    child.expect(PROMPT)
                    child.sendline("exit")
                    child.expect(pexpect.EOF)
                finally:
                    child.close()

            logfile = os.path.join(log_dir, f"{USER}.log")
            self.assertTrue(os.path.exists(logfile))
            events = self._load_command_events(logfile)

            denied = [
                event
                for event in events
                if event.get("event.outcome") == "failure"
                and "runtime_limit.max_background_jobs_exceeded"
                in event.get("event.reason", "")
            ]
            self.assertTrue(denied, msg=f"missing runtime-limit denial in {events}")


if __name__ == "__main__":
    unittest.main()
