"""Reason codes and user-facing mappings for the canonical v2 engine."""

from typing import Any, Dict, NamedTuple


class Reason(NamedTuple):
    """Structured authorization reason."""

    code: str
    details: Dict[str, Any]


ALLOWED = "allowed"
UNKNOWN_SYNTAX = "unknown_syntax"
FORBIDDEN_CONTROL_CHAR = "forbidden_control_char"
FORBIDDEN_CHARACTER = "forbidden_character"
FORBIDDEN_PATH = "forbidden_path"
FORBIDDEN_COMMAND = "forbidden_command"
FORBIDDEN_SUDO_COMMAND = "forbidden_sudo_command"
FORBIDDEN_FILE_EXTENSION = "forbidden_file_extension"
FORBIDDEN_ENV_ASSIGNMENT = "forbidden_env_assignment"
FORBIDDEN_TRUSTED_PROTOCOL = "forbidden_trusted_protocol"
COMMAND_NOT_FOUND = "command_not_found"


def make_reason(code, **details):
    """Build a structured reason payload."""
    return Reason(code=code, details=details)


def to_policy_message(reason):
    """Map structured reasons to legacy policy-show decision text."""
    code = reason.code
    details = reason.details

    if code == ALLOWED:
        return "allowed by final policy"
    if code == UNKNOWN_SYNTAX:
        return f"unknown syntax '{details.get('command', '')}'"
    if code == FORBIDDEN_CONTROL_CHAR:
        return "forbidden control character"
    if code == FORBIDDEN_CHARACTER:
        return f"forbidden character '{details.get('token', '')}'"
    if code == FORBIDDEN_PATH:
        return "forbidden path"
    if code == FORBIDDEN_COMMAND:
        return f"forbidden command '{details.get('command', '')}'"
    if code == FORBIDDEN_SUDO_COMMAND:
        if details.get("missing_target"):
            return "forbidden sudo command (missing target command)"
        return f"forbidden sudo command '{details.get('command', '')}'"
    if code == FORBIDDEN_FILE_EXTENSION:
        disallowed = details.get("disallowed_extensions", [])
        return "forbidden file extension(s) " + ", ".join(disallowed)
    if code == FORBIDDEN_ENV_ASSIGNMENT:
        return (
            "forbidden environment variable assignment "
            f"'{details.get('variable', '')}'"
        )
    if code == COMMAND_NOT_FOUND:
        return f"command not found '{details.get('command', '')}'"
    if code == FORBIDDEN_TRUSTED_PROTOCOL:
        return "forbidden trusted SSH protocol command"

    return "policy evaluation failed"


def to_audit_reason(reason):
    """Map structured reasons to runtime audit strings."""
    code = reason.code
    details = reason.details

    if code == ALLOWED:
        return details.get("reason", "allowed by command and path policy")
    if code == UNKNOWN_SYNTAX:
        return f"unknown syntax: {details.get('command', '')}"
    if code == FORBIDDEN_CONTROL_CHAR:
        return f"forbidden control char: {details.get('line', '')}"
    if code == FORBIDDEN_CHARACTER:
        return f"forbidden character: {details.get('token', '')}"
    if code == FORBIDDEN_PATH:
        return f"forbidden path: {details.get('path', '')}"
    if code == FORBIDDEN_COMMAND:
        return f"forbidden command: {details.get('command', '')}"
    if code == FORBIDDEN_SUDO_COMMAND:
        return f"forbidden sudo command: {details.get('line', '')}"
    if code == FORBIDDEN_FILE_EXTENSION:
        return f"forbidden file extension: {', '.join(details.get('disallowed_extensions', []))}"
    if code == FORBIDDEN_ENV_ASSIGNMENT:
        return "forbidden environment variable assignment: " + details.get(
            "variable", ""
        )
    if code == FORBIDDEN_TRUSTED_PROTOCOL:
        return "forbidden trusted SSH protocol command: " + details.get("command", "")
    if code == COMMAND_NOT_FOUND:
        return f"command not found: {details.get('command', '')}"

    return "policy evaluation failed"


def warning_payload(reason):
    """Map structured reasons to warn_count()/warn_unknown_syntax payload."""
    code = reason.code
    details = reason.details

    if code == UNKNOWN_SYNTAX:
        return {"kind": "unknown_syntax", "command": details.get("command", "")}
    if code == FORBIDDEN_CONTROL_CHAR:
        return {
            "kind": "warn_count",
            "messagetype": "control char",
            "command": details.get("line", ""),
        }
    if code == FORBIDDEN_CHARACTER:
        return {
            "kind": "warn_count",
            "messagetype": "character",
            "command": details.get("token", ""),
        }
    if code == FORBIDDEN_PATH:
        return {
            "kind": "warn_count",
            "messagetype": "path",
            "command": details.get("path", ""),
        }
    if code == FORBIDDEN_COMMAND:
        return {
            "kind": "warn_count",
            "messagetype": "command",
            "command": details.get("command", ""),
        }
    if code == FORBIDDEN_SUDO_COMMAND:
        return {
            "kind": "warn_count",
            "messagetype": "sudo command",
            "command": details.get("line", ""),
        }
    if code == FORBIDDEN_FILE_EXTENSION:
        return {
            "kind": "warn_count",
            "messagetype": f"file extension {details.get('disallowed_extensions', [])}",
            "command": details.get("full_command", ""),
        }

    return None
