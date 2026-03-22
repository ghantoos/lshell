"""Structured security audit logging helpers."""

import json
import logging
import os
from datetime import datetime, timezone


ECS_VERSION = "8.11.0"
LAST_REASON_KEY = "_last_security_decision_reason"


def _now_utc_iso():
    """Return UTC ISO8601 timestamp with millisecond precision."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _source_ip():
    """Extract source IP from SSH context, falling back to localhost."""
    if os.environ.get("SSH_CLIENT"):
        return os.environ["SSH_CLIENT"].split()[0]
    if os.environ.get("SSH_CONNECTION"):
        return os.environ["SSH_CONNECTION"].split()[0]
    if os.environ.get("REMOTE_ADDR"):
        return os.environ["REMOTE_ADDR"]
    return "127.0.0.1"


def enabled(conf):
    """Return True when structured audit logging is enabled."""
    return bool(conf.get("security_audit_json") and conf.get("logpath"))


class EcsJsonFormatter(logging.Formatter):
    """Format log records as ECS-aligned JSON lines."""

    def format(self, record):
        payload = {
            "@timestamp": _now_utc_iso(),
            "ecs.version": ECS_VERSION,
            "log.level": record.levelname.lower(),
            "message": record.getMessage(),
            "session.id": str(
                getattr(record, "session_id", "")
                or os.environ.get("LSHELL_SESSION_ID", "")
            ),
            "source.ip": str(getattr(record, "source_ip", "") or _source_ip()),
            "user.name": str(
                getattr(record, "username", "")
                or os.environ.get("LOGNAME")
                or os.environ.get("USER")
                or ""
            ),
        }

        event_kind = getattr(record, "event_kind", None)
        if event_kind:
            payload["event.kind"] = event_kind
        event_category = getattr(record, "event_category", None)
        if event_category:
            payload["event.category"] = event_category
        event_type = getattr(record, "event_type", None)
        if event_type:
            payload["event.type"] = event_type
        event_action = getattr(record, "event_action", None)
        if event_action:
            payload["event.action"] = event_action
        event_outcome = getattr(record, "event_outcome", None)
        if event_outcome:
            payload["event.outcome"] = event_outcome
        event_reason = getattr(record, "event_reason", None)
        if event_reason:
            payload["event.reason"] = event_reason
        process_command_line = getattr(record, "process_command_line", None)
        if process_command_line:
            payload["process.command_line"] = process_command_line

        allowed = getattr(record, "lshell_security_allowed", None)
        if allowed is not None:
            payload["lshell.security.allowed"] = bool(allowed)

        return json.dumps(payload, sort_keys=True)


def set_decision_reason(conf, reason):
    """Store latest decision reason in session config."""
    conf[LAST_REASON_KEY] = reason


def pop_decision_reason(conf, default="policy evaluation failed"):
    """Return and clear latest decision reason from session config."""
    return conf.pop(LAST_REASON_KEY, default)


def log_command_event(conf, command, allowed, reason, level=None):
    """Emit one ECS-aligned command authorization event."""
    log_security_event(
        conf,
        action="command_authorization",
        allowed=allowed,
        reason=reason,
        command=command,
        level=level,
        message="lshell command authorization decision",
    )


def log_security_event(
    conf,
    action,
    allowed,
    reason,
    command="",
    level=None,
    message="lshell security decision",
):
    """Emit one ECS-aligned runtime security event."""
    if not enabled(conf):
        return

    logger = conf["logpath"]
    log_method = str(level or ("info" if allowed else "warning")).lower()
    log_level = getattr(logging, log_method.upper(), logging.INFO)
    logger.log(
        log_level,
        message,
        extra={
            "session_id": str(conf.get("session_id", "")),
            "source_ip": _source_ip(),
            "username": str(conf.get("username", "")),
            "event_kind": "event",
            "event_category": ["authentication", "process"],
            "event_type": ["access"],
            "event_action": str(action),
            "event_outcome": "success" if allowed else "failure",
            "event_reason": str(reason),
            "process_command_line": str(command or ""),
            "lshell_security_allowed": bool(allowed),
        },
    )
