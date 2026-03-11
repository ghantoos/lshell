"""Centralized message templates and formatting helpers."""

from string import Formatter


DEFAULT_MESSAGES = {
    "unknown_syntax": "lshell: unknown syntax: {command}",
    "command_not_found": 'lshell: command not found: "{command}"',
    "forbidden_generic": 'lshell: forbidden {messagetype}: "{command}"',
    "forbidden_command": 'lshell: forbidden command: "{command}"',
    "forbidden_path": 'lshell: forbidden path: "{command}"',
    "forbidden_character": 'lshell: forbidden character: "{command}"',
    "forbidden_control_char": 'lshell: forbidden control char: "{command}"',
    "forbidden_command_over_ssh": 'lshell: forbidden {message}: "{command}"',
    "forbidden_scp_over_ssh": "lshell: forbidden {message}",
    "warning_remaining": (
        "lshell: warning: {remaining} {violation_label}"
        " remaining before session termination"
    ),
    "session_terminated": "lshell: session terminated: warning limit exceeded",
    "incident_reported": "This incident has been reported.",
}

MESSAGE_FIELDS = {
    "unknown_syntax": {"command"},
    "command_not_found": {"command"},
    "forbidden_generic": {"messagetype", "command"},
    "forbidden_command": {"command"},
    "forbidden_path": {"command"},
    "forbidden_character": {"command"},
    "forbidden_control_char": {"command"},
    "forbidden_command_over_ssh": {"message", "command"},
    "forbidden_scp_over_ssh": {"message"},
    "warning_remaining": {"remaining", "violation_label"},
    "session_terminated": set(),
    "incident_reported": set(),
}


def validate_messages_config(messages):
    """Validate custom message overrides from configuration."""
    if not isinstance(messages, dict):
        raise ValueError("'messages' must be a dictionary")

    for key, template in messages.items():
        if key not in DEFAULT_MESSAGES:
            raise ValueError(f"'messages' contains unsupported key: '{key}'")
        if not isinstance(template, str):
            raise ValueError(f"'messages.{key}' must be a string")

        fields = {
            field_name
            for _, field_name, _, _ in Formatter().parse(template)
            if field_name is not None
        }
        invalid_fields = fields - MESSAGE_FIELDS[key]
        if invalid_fields:
            invalid = ", ".join(sorted(invalid_fields))
            raise ValueError(
                f"'messages.{key}' contains unsupported placeholders: {invalid}"
            )

    return messages


def get_message(conf, key, **context):
    """Return a formatted message template from config or defaults."""
    template = conf.get("messages", {}).get(key, DEFAULT_MESSAGES[key])
    return template.format(**context)


def get_forbidden_message(conf, messagetype, command):
    """Return the best matching forbidden message for a given violation type."""
    key = f"forbidden_{messagetype.replace(' ', '_')}"
    if key in DEFAULT_MESSAGES:
        return get_message(conf, key, command=command)
    return get_message(
        conf,
        "forbidden_generic",
        messagetype=messagetype,
        command=command,
    )
