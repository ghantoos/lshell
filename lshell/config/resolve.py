"""Resolve final raw configuration values from layered config sections.

This module is the canonical implementation shared by runtime and diagnostics.
It handles:
- ``+/-`` list operations
- ``all`` expansion for allow-lists
- path glob expansion into allow/deny path entries
- per-section application with optional source/trace recording

The functions are callback-driven so callers control parsing, errors, and logs.
"""

import glob
import os
import re

from lshell.config import schema


MERGE_LIST_KEYS = {
    "path",
    "overssh",
    "allowed",
    "allowed_shell_escape",
    "allowed_file_extensions",
    "forbidden",
}

_MERGE_TOKEN_SPLIT = re.compile(r"((?:\+|-)\s*\[[^\]]+\])")

_SHELL_BUILTINS_FOR_ALL = [
    "bg",
    "break",
    "case",
    "cd",
    "continue",
    "eval",
    "exec",
    "exit",
    "fg",
    "if",
    "jobs",
    "kill",
    "login",
    "logout",
    "set",
    "shift",
    "stop",
    "suspend",
    "umask",
    "unset",
    "wait",
    "while",
]


def expand_all(path_env, on_missing_path=None):
    """Expand 'all' into shell builtins and executable names from PATH."""
    expanded_all = list(_SHELL_BUILTINS_FOR_ALL)
    for directory in path_env.split(":"):
        if not directory:
            continue
        if os.path.exists(directory):
            for item in os.listdir(directory):
                if os.access(os.path.join(directory, item), os.X_OK):
                    expanded_all.append(item)
        elif on_missing_path:
            on_missing_path(directory)
    return str(expanded_all)


def minusplus(
    conf_raw,
    key,
    extra,
    parse_value,
    on_missing_remove=None,
):
    """Apply +/- list merge operation for a single token."""
    if key in conf_raw:
        current = parse_value(conf_raw[key], key)
    elif key == "path":
        current = ["", ""]
    else:
        current = []

    sublist = parse_value(extra[1:], key)
    if extra.startswith("+"):
        if key == "path":
            for path in sublist:
                current[0] += os.path.realpath(path) + "/|"
        else:
            for item in sublist:
                current.append(item)
    elif extra.startswith("-"):
        if key == "path":
            for path in sublist:
                current[1] += os.path.realpath(path) + "/|"
        else:
            for item in sublist:
                if item in current:
                    current.remove(item)
                elif on_missing_remove:
                    on_missing_remove(key, item)

    return {key: str(current)}


def merge_section(
    conf_raw,
    section,
    section_items,
    parse_value,
    expand_all_value,
    on_error,
    trace=None,
    key_sources=None,
    on_missing_remove=None,
):
    """Merge one section into conf_raw with optional trace recording."""
    for key, value in section_items:
        source = None
        if key_sources is not None:
            source = key_sources.get((section, key))

        split = [""]
        if isinstance(value, str):
            split = _MERGE_TOKEN_SPLIT.split(value)

        previous = conf_raw.get(key)

        def _trace_event(op, token):
            if trace is None:
                return
            trace.append(
                {
                    "section": section,
                    "source": source,
                    "key": key,
                    "op": op,
                    "token": token,
                    "before": previous,
                    "after": conf_raw.get(key),
                }
            )

        if len(split) > 1 and key in MERGE_LIST_KEYS:
            for token in split:
                if not token.strip():
                    continue

                if token.startswith("-") or token.startswith("+"):
                    conf_raw.update(
                        minusplus(
                            conf_raw,
                            key,
                            token,
                            parse_value,
                            on_missing_remove=on_missing_remove,
                        )
                    )
                    _trace_event(token[0], token[1:])
                    previous = conf_raw.get(key)
                    continue

                if schema.is_all_literal(token):
                    if key == "allowed":
                        conf_raw.update({key: expand_all_value()})
                        _trace_event("set_all", token)
                        previous = conf_raw.get(key)
                    elif key == "allowed_shell_escape":
                        on_error("'allowed_shell_escape' cannot be set to 'all'")
                    else:
                        on_error(f"'{key}' cannot be set to 'all'")
                    continue

                if key == "path":
                    allow_deny = ["", ""]
                    for path_pattern in parse_value(token, key):
                        for item in glob.glob(path_pattern):
                            allow_deny[0] += os.path.realpath(item) + "/|"
                    allow_deny[0] = allow_deny[0].replace("//", "/")
                    conf_raw.update({key: str(allow_deny)})
                    _trace_event("set", token)
                    previous = conf_raw.get(key)
                    continue

                parsed_token = parse_value(token, key)
                if isinstance(parsed_token, list):
                    conf_raw.update({key: token})
                    _trace_event("set", token)
                    previous = conf_raw.get(key)
            continue

        if key == "allowed" and schema.is_all_literal(split[0]):
            conf_raw.update({key: expand_all_value()})
            _trace_event("set_all", split[0])
            continue

        if key == "allowed_shell_escape" and schema.is_all_literal(split[0]):
            on_error("'allowed_shell_escape' cannot be set to 'all'")
            continue

        if key == "path":
            allow_deny = ["", ""]
            for path_pattern in parse_value(value, key):
                for item in glob.glob(path_pattern):
                    allow_deny[0] += os.path.realpath(item) + "/|"
            allow_deny[0] = allow_deny[0].replace("//", "/")
            conf_raw.update({key: str(allow_deny)})
            _trace_event("set", value)
            continue

        conf_raw[key] = value
        _trace_event("set", value)
