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

            with open(logfile, "r", encoding="utf-8") as handle:
                lines = [line.strip() for line in handle if line.strip()]

            events = []
            for line in lines:
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if payload.get("event.action") == "command_authorization":
                    events.append(payload)

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


if __name__ == "__main__":
    unittest.main()
