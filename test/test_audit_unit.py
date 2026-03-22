"""Unit tests for structured security audit logging."""

import json
import logging
import os
import unittest
from unittest.mock import patch

from lshell import audit
from lshell.checkconfig import CheckConfig


TOPDIR = f"{os.path.dirname(os.path.realpath(__file__))}/../"
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"


class _DummyAuditLogger:
    """Capture structured audit calls."""

    def __init__(self):
        self.entries = []

    def log(self, level, message, extra=None):
        """Record one structured audit call."""
        self.entries.append((level, message, extra or {}))


class TestAuditLogging(unittest.TestCase):
    """Validate JSON/ECS security audit event behavior."""

    args = [f"--config={CONFIG}", "--quiet=1"]

    def test_security_audit_json_flag_is_parsed(self):
        """Config/CLI flag should enable structured audit mode."""
        conf = CheckConfig(self.args + ["--security_audit_json=1"]).returnconf()
        self.assertEqual(conf["security_audit_json"], 1)

    def test_log_command_event_emits_ecs_json(self):
        """Structured event should include ECS fields and decision reason."""
        logger = _DummyAuditLogger()
        conf = {
            "security_audit_json": 1,
            "logpath": logger,
            "session_id": "session-123",
            "username": "testuser",
        }

        with patch.dict(os.environ, {"SSH_CLIENT": "192.0.2.10 2222 22"}, clear=False):
            audit.log_command_event(
                conf,
                "cat /etc/passwd",
                allowed=False,
                reason="forbidden path: /etc/passwd",
            )

        self.assertEqual(len(logger.entries), 1)
        level, message, extra = logger.entries[0]
        self.assertEqual(level, logging.WARNING)
        self.assertEqual(message, "lshell command authorization decision")
        self.assertEqual(extra["session_id"], "session-123")
        self.assertEqual(extra["source_ip"], "192.0.2.10")
        self.assertEqual(extra["process_command_line"], "cat /etc/passwd")
        self.assertEqual(extra["event_reason"], "forbidden path: /etc/passwd")
        self.assertEqual(extra["event_outcome"], "failure")

    def test_ecs_formatter_outputs_json_payload(self):
        """Formatter should render ECS-aligned JSON from log extras."""
        formatter = audit.EcsJsonFormatter()
        record = logging.makeLogRecord(
            {
                "levelname": "WARNING",
                "levelno": logging.WARNING,
                "msg": "lshell command authorization decision",
                "session_id": "session-123",
                "source_ip": "192.0.2.10",
                "username": "testuser",
                "event_kind": "event",
                "event_category": ["authentication", "process"],
                "event_type": ["access"],
                "event_action": "command_authorization",
                "event_outcome": "failure",
                "event_reason": "forbidden path: /etc/passwd",
                "process_command_line": "cat /etc/passwd",
                "lshell_security_allowed": False,
            }
        )
        payload = json.loads(formatter.format(record))
        self.assertEqual(payload["session.id"], "session-123")
        self.assertEqual(payload["source.ip"], "192.0.2.10")
        self.assertEqual(payload["process.command_line"], "cat /etc/passwd")
        self.assertEqual(payload["event.reason"], "forbidden path: /etc/passwd")
        self.assertEqual(payload["event.outcome"], "failure")

    def test_log_command_event_noop_when_disabled(self):
        """No structured event should be emitted when feature flag is off."""
        logger = _DummyAuditLogger()
        conf = {
            "security_audit_json": 0,
            "logpath": logger,
            "session_id": "session-123",
            "username": "testuser",
        }
        audit.log_command_event(conf, "echo ok", allowed=True, reason="allowed")
        self.assertEqual(logger.entries, [])

    def test_log_security_event_keeps_machine_readable_reason(self):
        """Generic runtime security events should retain reason code strings."""
        logger = _DummyAuditLogger()
        conf = {
            "security_audit_json": 1,
            "logpath": logger,
            "session_id": "session-abc",
            "username": "testuser",
        }

        audit.log_security_event(
            conf,
            action="runtime_containment",
            allowed=False,
            reason="runtime_limit.max_background_jobs_exceeded",
            command="sleep 60 &",
            level="warning",
            message="lshell runtime containment decision",
        )

        self.assertEqual(len(logger.entries), 1)
        level, message, extra = logger.entries[0]
        self.assertEqual(level, logging.WARNING)
        self.assertEqual(message, "lshell runtime containment decision")
        self.assertEqual(extra["event_action"], "runtime_containment")
        self.assertEqual(
            extra["event_reason"], "runtime_limit.max_background_jobs_exceeded"
        )
        self.assertEqual(extra["event_outcome"], "failure")
