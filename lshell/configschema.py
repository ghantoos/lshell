"""Shared config parsing and schema validation for lshell."""

import ast

from lshell import messages


LIST_VALUE_KEYS = {
    "allowed",
    "allowed_shell_escape",
    "allowed_file_extensions",
    "forbidden",
    "overssh",
    "sudo_commands",
    "env_vars_files",
    "allowed_cmd_path",
    "path",
}
LIST_OF_STRING_KEYS = {
    "allowed",
    "allowed_shell_escape",
    "allowed_file_extensions",
    "forbidden",
    "overssh",
    "sudo_commands",
    "env_vars_files",
    "allowed_cmd_path",
    "path",
}
INT_VALUE_KEYS = {
    "warning_counter",
    "timer",
    "scp",
    "scp_upload",
    "scp_download",
    "sftp",
    "strict",
    "history_size",
    "winscp",
    "disable_exit",
    "policy_commands",
    "quiet",
    "loglevel",
    "security_audit_json",
    "max_sessions_per_user",
    "max_background_jobs",
    "command_timeout",
    "max_processes",
}
DICT_VALUE_KEYS = {"aliases", "env_vars", "messages"}
STRING_VALUE_KEYS = {
    "intro",
    "prompt",
    "home_path",
    "env_path",
    "history_file",
    "path_noexec",
    "scpforce",
    "logfilename",
    "syslogname",
}
DEDUP_LIST_KEYS = {
    "allowed",
    "allowed_shell_escape",
    "allowed_file_extensions",
    "forbidden",
    "overssh",
    "sudo_commands",
}


def is_all_literal(raw_value):
    """Return True when the config value denotes the literal 'all'."""
    if not isinstance(raw_value, str):
        return False
    return raw_value.strip() in {"all", "'all'", '"all"'}


def _is_string_literal(text):
    stripped = text.strip()
    return (
        len(stripped) >= 2
        and stripped[0] in ("'", '"')
        and stripped[-1] == stripped[0]
    )


def parse_config_value(value, key=""):
    """Safely parse config value and enforce key schema.

    Raises ValueError with user-friendly field-level errors.
    """
    if (
        isinstance(value, str)
        and key in {"allowed", "sudo_commands"}
        and is_all_literal(value)
    ):
        return "all"

    try:
        evaluated = ast.literal_eval(value)
    except (SyntaxError, ValueError) as exception:
        if key in STRING_VALUE_KEYS and isinstance(value, str):
            evaluated = value.strip()
        elif isinstance(exception, SyntaxError):
            raise ValueError(f"Incomplete {key} field in configuration file") from exception
        else:
            raise ValueError(f"Invalid value for '{key}' in configuration file") from exception

    if key in INT_VALUE_KEYS and not isinstance(evaluated, int):
        raise ValueError(f"'{key}' must be an integer")

    if key in LIST_VALUE_KEYS and not isinstance(evaluated, list):
        raise ValueError(f"'{key}' must be a list")

    if key in DICT_VALUE_KEYS and not isinstance(evaluated, dict):
        raise ValueError(f"'{key}' must be a dictionary")

    if key == "messages":
        evaluated = messages.validate_messages_config(evaluated)

    if key in STRING_VALUE_KEYS:
        if isinstance(evaluated, str):
            if _is_string_literal(evaluated):
                try:
                    evaluated = ast.literal_eval(evaluated)
                except (SyntaxError, ValueError):
                    pass
        else:
            raise ValueError(f"'{key}' must be a string")

    if key in LIST_OF_STRING_KEYS and any(not isinstance(item, str) for item in evaluated):
        raise ValueError(f"'{key}' list entries must be strings")

    if isinstance(evaluated, list) and key in DEDUP_LIST_KEYS:
        evaluated = list(set(evaluated))

    return evaluated
