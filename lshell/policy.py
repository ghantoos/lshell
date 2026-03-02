"""Diagnostics mode for policy resolution and command decisions."""

import argparse
import configparser
import glob
import grp
import json
import os
import pwd
import re
import sys
import textwrap
from getpass import getuser

from lshell import builtincmd
from lshell import configschema
from lshell import sec
from lshell import utils
from lshell import variables


MERGE_LIST_KEYS = {
    "path",
    "overssh",
    "allowed",
    "allowed_shell_escape",
    "allowed_file_extensions",
    "forbidden",
}

DISPLAY_KEY_ORDER = [
    "allowed",
    "allowed_shell_escape",
    "allowed_file_extensions",
    "forbidden",
    "sudo_commands",
    "strict",
    "warning_counter",
    "path",
    "home_path",
    "env_path",
    "allowed_cmd_path",
    "overssh",
    "scp",
    "scp_upload",
    "scp_download",
    "sftp",
    "umask",
    "aliases",
    "winscp",
    "policy_commands",
    "disable_exit",
    "timer",
    "history_size",
    "history_file",
    "prompt",
    "prompt_short",
    "intro",
]


def _safe_eval(value, key=""):
    """Safely parse config values with shared schema validation."""
    return configschema.parse_config_value(value, key)


def _expand_all():
    """Expand 'all' into executable names from PATH plus shell builtins."""
    expanded_all = [
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

    for directory in os.environ.get("PATH", "").split(":"):
        if not directory:
            continue
        if os.path.exists(directory):
            for item in os.listdir(directory):
                if os.access(os.path.join(directory, item), os.X_OK):
                    expanded_all.append(item)

    return str(expanded_all)


def _minusplus(conf_raw, key, extra):
    """Update configuration lists containing -/+ operators."""
    if key in conf_raw:
        current = _safe_eval(conf_raw[key], key)
    elif key == "path":
        current = ["", ""]
    else:
        current = []

    sublist = _safe_eval(extra[1:], key)
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

    return {key: str(current)}


def _read_config_with_sources(configfile, include_dir):
    """Load config files and return parser + key source mapping."""
    parser = configparser.ConfigParser(interpolation=None)
    read_files = [configfile]
    include_files = []
    if include_dir:
        include_files = glob.glob(f"{include_dir}*")
        read_files.extend(include_files)
    parser.read(read_files)

    key_sources = {}
    for file_path in read_files:
        file_parser = configparser.ConfigParser(interpolation=None)
        file_parser.read(file_path)
        for section in file_parser.sections():
            for key, _ in file_parser.items(section):
                key_sources[(section, key)] = file_path
    return parser, include_files, key_sources


def _merge_section(conf_raw, section, section_items, key_sources, trace):
    """Apply a single section to conf_raw while recording trace details."""
    for key, value in section_items:
        source = key_sources.get((section, key))
        split = [""]
        if isinstance(value, str):
            split = re.split(r"((?:\+|-)\s*\[[^\]]+\])", value)

        previous = conf_raw.get(key)

        if len(split) > 1 and key in MERGE_LIST_KEYS:
            for token in split:
                if not token.strip():
                    continue
                if token.startswith("-") or token.startswith("+"):
                    conf_raw.update(_minusplus(conf_raw, key, token))
                    trace.append(
                        {
                            "section": section,
                            "source": source,
                            "key": key,
                            "op": token[0],
                            "token": token[1:],
                            "before": previous,
                            "after": conf_raw.get(key),
                        }
                    )
                    previous = conf_raw.get(key)
                elif configschema.is_all_literal(token):
                    if key == "allowed_shell_escape":
                        raise ValueError(
                            "'allowed_shell_escape' cannot be set to 'all'"
                        )
                    conf_raw.update({key: _expand_all()})
                    trace.append(
                        {
                            "section": section,
                            "source": source,
                            "key": key,
                            "op": "set_all",
                            "token": token,
                            "before": previous,
                            "after": conf_raw.get(key),
                        }
                    )
                    previous = conf_raw.get(key)
                elif key == "path":
                    allow_deny = ["", ""]
                    for path_pattern in _safe_eval(token, key):
                        for item in glob.glob(path_pattern):
                            allow_deny[0] += os.path.realpath(item) + "/|"
                    allow_deny[0] = allow_deny[0].replace("//", "/")
                    conf_raw.update({key: str(allow_deny)})
                    trace.append(
                        {
                            "section": section,
                            "source": source,
                            "key": key,
                            "op": "set",
                            "token": token,
                            "before": previous,
                            "after": conf_raw.get(key),
                        }
                    )
                    previous = conf_raw.get(key)
                elif isinstance(_safe_eval(token, key), list):
                    conf_raw.update({key: token})
                    trace.append(
                        {
                            "section": section,
                            "source": source,
                            "key": key,
                            "op": "set",
                            "token": token,
                            "before": previous,
                            "after": conf_raw.get(key),
                        }
                    )
                    previous = conf_raw.get(key)
        elif key == "allowed" and split[0].strip() == "'all'":
            conf_raw.update({key: _expand_all()})
            trace.append(
                {
                    "section": section,
                    "source": source,
                    "key": key,
                    "op": "set_all",
                    "token": split[0],
                    "before": previous,
                    "after": conf_raw.get(key),
                }
            )
        elif key == "allowed_shell_escape" and configschema.is_all_literal(split[0]):
            raise ValueError("'allowed_shell_escape' cannot be set to 'all'")
        elif key == "path":
            allow_deny = ["", ""]
            for path_pattern in _safe_eval(value, "path"):
                for item in glob.glob(path_pattern):
                    allow_deny[0] += os.path.realpath(item) + "/|"
            allow_deny[0] = allow_deny[0].replace("//", "/")
            conf_raw.update({key: str(allow_deny)})
            trace.append(
                {
                    "section": section,
                    "source": source,
                    "key": key,
                    "op": "set",
                    "token": value,
                    "before": previous,
                    "after": conf_raw.get(key),
                }
            )
        else:
            conf_raw[key] = value
            trace.append(
                {
                    "section": section,
                    "source": source,
                    "key": key,
                    "op": "set",
                    "token": value,
                    "before": previous,
                    "after": conf_raw.get(key),
                }
            )


def _build_runtime_policy(conf_raw, username):
    """Convert raw merged config values into effective runtime policy."""
    policy = {}

    for item in [
        "allowed",
        "allowed_shell_escape",
        "allowed_file_extensions",
        "forbidden",
        "sudo_commands",
        "warning_counter",
        "overssh",
        "strict",
        "aliases",
        "allowed_cmd_path",
        "winscp",
        "policy_commands",
        "scp_upload",
        "scp_download",
    ]:
        try:
            if len(conf_raw[item]) == 0:
                policy[item] = ""
            else:
                policy[item] = _safe_eval(conf_raw[item], item)
        except KeyError:
            if item in [
                "allowed",
                "allowed_shell_escape",
                "allowed_file_extensions",
                "overssh",
                "sudo_commands",
                "allowed_cmd_path",
            ]:
                policy[item] = []
            elif item in ["scp_upload", "scp_download"]:
                policy[item] = 1
            elif item in ["aliases"]:
                policy[item] = {}
            elif item in ["policy_commands"]:
                policy[item] = 1
            else:
                policy[item] = 0

    policy["username"] = username

    if "home_path" in conf_raw:
        home_path = conf_raw["home_path"].replace("%u", username)
        policy["home_path"] = os.path.normpath(_safe_eval(home_path, "home_path"))
    else:
        policy["home_path"] = os.environ.get("HOME", "/")

    if "path" in conf_raw:
        policy["path"] = _safe_eval(conf_raw["path"], "path")
        policy["path"][0] += policy["home_path"]
    else:
        policy["path"] = ["", ""]
        policy["path"][0] = policy["home_path"]

    policy["allowed"] += list(set(builtincmd.builtins_list) - set(["export"]))
    if policy.get("policy_commands") != 1:
        policy["allowed"] = [
            cmd for cmd in policy["allowed"] if cmd not in builtincmd.POLICY_COMMANDS
        ]
    if policy["sudo_commands"]:
        policy["allowed"].append("sudo")

    for path in policy.get("allowed_cmd_path", []):
        if os.path.isdir(path):
            for item in os.listdir(path):
                cmd = os.path.join(path, item)
                if os.access(cmd, os.X_OK):
                    policy["allowed"].append(item)

    if "sudo_commands" in conf_raw and configschema.is_all_literal(
        str(conf_raw["sudo_commands"])
    ):
        exclude = builtincmd.builtins_list + ["sudo"]
        policy["sudo_commands"] = [x for x in policy["allowed"] if x not in exclude]

    policy["allowed"] += policy["allowed_shell_escape"]

    if policy.get("winscp") == 1:
        policy["allowed"].extend(["scp", "env", "pwd", "groups", "unset", "unalias"])
        policy["scp_upload"] = 1
        policy["scp_download"] = 1
        policy["allowed"] = list(set(policy["allowed"]))
        if ";" in policy["forbidden"]:
            policy["forbidden"].remove(";")

    return policy


def resolve_policy(configfile, username, groups):
    """Resolve effective policy and detailed merge trace for policy-show mode."""
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(configfile)
    if not parser.has_section("global"):
        raise ValueError("Config file missing [global] section")

    include_dir = None
    if parser.has_option("global", "include_dir"):
        include_dir = parser.get("global", "include_dir")

    parser, include_files, key_sources = _read_config_with_sources(configfile, include_dir)

    conf_raw = {}
    trace = []
    precedence_chain = ["default"]
    effective_groups = list(groups)
    fallback_group_section = f"grp:{username}"
    if not effective_groups and parser.has_section(fallback_group_section):
        effective_groups = [username]

    group_sections = [f"grp:{group_name}" for group_name in effective_groups]
    precedence_chain.extend(reversed(group_sections))
    precedence_chain.append(username)
    precedence_chain.append(f"user:{username}")
    applied_sections = []

    for section in precedence_chain:
        if parser.has_section(section):
            applied_sections.append(section)
            _merge_section(
                conf_raw,
                section,
                list(parser.items(section)),
                key_sources,
                trace,
            )

    for required_key in variables.required_config:
        if required_key not in conf_raw:
            raise ValueError(
                f"Missing parameter '{required_key}' in [{username}] or [default]"
            )

    policy = _build_runtime_policy(conf_raw, username)
    return {
        "configfile": configfile,
        "include_files": include_files,
        "precedence_chain": precedence_chain,
        "applied_sections": applied_sections,
        "trace": trace,
        "conf_raw": conf_raw,
        "policy": policy,
    }


def policy_command_decision(command_line, policy):
    """Determine whether a command would be allowed and why."""
    if re.findall(r"[\x01-\x1F\x7F]", command_line):
        return {"allowed": False, "reason": "forbidden control character"}

    for item in policy["forbidden"]:
        if item in ["&", "|"]:
            escaped = re.escape(item)
            if re.search(rf"(?<!{escaped}){escaped}(?!{escaped})", command_line):
                return {"allowed": False, "reason": f"forbidden character '{item}'"}
        elif item in command_line:
            return {"allowed": False, "reason": f"forbidden character '{item}'"}

    lines = utils.split_commands(command_line.strip())
    for separate_line in lines:
        line = re.sub(r"\)$", "", separate_line)
        line = " ".join(line.split())
        command, command_args_list, full_command = sec._split_command_for_auth(line)

        if command == "sudo" and command_args_list:
            if command_args_list[0] == "-u":
                if len(command_args_list) < 3:
                    return {
                        "allowed": False,
                        "reason": "forbidden sudo command (missing target command)",
                    }
                sudocmd = command_args_list[2]
            else:
                sudocmd = command_args_list[0]
            if sudocmd not in policy["sudo_commands"]:
                return {
                    "allowed": False,
                    "reason": f"forbidden sudo command '{sudocmd}'",
                }

        if (
            full_command not in policy["allowed"]
            and command not in policy["allowed"]
            and command
        ):
            if policy.get("strict"):
                return {"allowed": False, "reason": f"forbidden command '{command}'"}
            return {"allowed": False, "reason": f"unknown syntax '{full_command}'"}

        allowed_extensions = policy.get("allowed_file_extensions")
        if allowed_extensions and sec.should_enforce_file_extensions(command):
            check_extensions, disallowed_extensions = sec.check_allowed_file_extensions(
                full_command, allowed_extensions
            )
            if check_extensions is False:
                return {
                    "allowed": False,
                    "reason": (
                        "forbidden file extension(s) "
                        + ", ".join(disallowed_extensions)
                    ),
                }

    path_ret, _ = sec.check_path(command_line, {"path": policy["path"]}, completion=1)
    if path_ret == 1:
        return {"allowed": False, "reason": "forbidden path"}

    return {"allowed": True, "reason": "allowed by final policy"}


def _parse_groups(group_values):
    groups = []
    for entry in group_values:
        for group_name in entry.split(","):
            group_name = group_name.strip()
            if group_name:
                groups.append(group_name)
    return groups


def _resolve_user_groups(username, explicit_groups):
    """Resolve target groups from CLI input or system user/group database."""
    parsed_groups = _parse_groups(explicit_groups)
    if parsed_groups:
        return parsed_groups

    try:
        user_entry = pwd.getpwnam(username)
    except KeyError:
        return []

    discovered = []
    try:
        primary_group = grp.getgrgid(user_entry.pw_gid).gr_name
        discovered.append(primary_group)
    except KeyError:
        pass

    for group_entry in grp.getgrall():
        if username in group_entry.gr_mem and group_entry.gr_name not in discovered:
            discovered.append(group_entry.gr_name)

    return discovered


def _format_section_label(section, username):
    if section == username:
        return f"user:{username}"
    return section


def _resolve_key_value_display(conf_raw, key):
    if key == "path":
        return _safe_eval(conf_raw[key], key)
    try:
        value = _safe_eval(conf_raw[key], key)
        if isinstance(value, list):
            return sorted(value, key=lambda item: str(item))
        return value
    except Exception:  # pragma: no cover - fallback for unusual string formats
        return conf_raw[key]


def _ordered_keys(conf_raw):
    ordered = [key for key in DISPLAY_KEY_ORDER if key in conf_raw]
    remaining = sorted([key for key in conf_raw.keys() if key not in DISPLAY_KEY_ORDER])
    return ordered + remaining


def _build_resolved_rows(result):
    latest_by_key = {}
    for event in result["trace"]:
        latest_by_key[event["key"]] = event

    rows = []
    for key in _ordered_keys(result["conf_raw"]):
        event = latest_by_key.get(key, {})
        section = _format_section_label(
            event.get("section", "unknown"), result["policy"]["username"]
        )
        value = _resolve_key_value_display(result["conf_raw"], key)
        rows.append(
            {
                "section": section,
                "key": key,
                "value": value,
            }
        )
    return rows


def _build_grouped_rows(result):
    rows = _build_resolved_rows(result)
    grouped = {section: [] for section in result["applied_sections"]}
    for row in rows:
        section = row["section"]
        if section not in grouped:
            grouped[section] = []
        grouped[section].append(row)
    return grouped


def _use_color():
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM", "").lower() == "dumb":
        return False
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def _paint(text, style, enabled):
    if not enabled:
        return text
    styles = {
        "bold": "\033[1m",
        "dim": "\033[2m",
        "cyan": "\033[36m",
        "green": "\033[32m",
        "red": "\033[31m",
        "yellow": "\033[33m",
    }
    reset = "\033[0m"
    return f"{styles.get(style, '')}{text}{reset}"


def _render_value(value):
    if isinstance(value, str) and any(ord(char) < 32 for char in value):
        return value.encode("unicode_escape").decode("ascii")
    return str(value)


def _format_wrapped_list(values, indent=22, width=88):
    joined = ", ".join(_render_value(item) for item in values) if values else "none"
    return textwrap.fill(
        joined,
        width=width,
        subsequent_indent=" " * indent,
    )


def _print_text(result, command_line=None, decision=None):
    color = _use_color()
    username = result["policy"]["username"]

    print(_paint("LSHELL POLICY", "bold", color))
    print(f"Target user   : {_paint(username, 'cyan', color)}")
    print(f"Main config   : {result['configfile']}")

    if result["include_files"]:
        print("Include files :")
        for include_file in result["include_files"]:
            print(f"  - {include_file}")
    else:
        print(f"Include files : {_paint('none', 'dim', color)}")

    print("")
    print(_paint("Resolution Order", "bold", color))
    if result["applied_sections"]:
        for section in result["applied_sections"]:
            print(
                "  "
                + _paint(">", "dim", color)
                + " ["
                + _format_section_label(section, result["policy"]["username"])
                + "]"
            )
    else:
        print("  none")

    print("")
    print(_paint("Resolved Values", "bold", color))
    grouped = _build_grouped_rows(result)
    for section in result["applied_sections"]:
        label = _format_section_label(section, result["policy"]["username"])
        section_rows = grouped.get(section, [])
        if not section_rows:
            continue
        print(_paint(f"[{label}]", "cyan", color))
        key_width = max(len(row["key"]) for row in section_rows)
        for row in section_rows:
            print(f"  {row['key']:<{key_width}} : {_render_value(row['value'])}")
        print("")

    if command_line is not None and decision is not None:
        verdict = "ALLOW" if decision["allowed"] else "DENY"
        verdict_style = "green" if decision["allowed"] else "red"
        print(_paint("Command Check", "bold", color))
        print(f"Command       : {command_line}")
        print(
            "Decision      : "
            + _paint(verdict, verdict_style, color)
            + f" ({decision['reason']})"
        )


def print_user_view(result, command_line=None, decision=None):
    """Print a concise user-facing policy summary and optional decision."""
    color = _use_color()
    policy = result["policy"]
    strict_mode = "on" if policy.get("strict") else "off"
    warning_counter = policy.get("warning_counter", 0)
    warnings_value = "disabled" if warning_counter == -1 else str(warning_counter)

    allowed_entries = sorted(set(policy.get("allowed", [])), key=str)
    aliases = policy.get("aliases", {})
    alias_entries = []
    if isinstance(aliases, dict):
        alias_entries = [f"{key} -> {value}" for key, value in sorted(aliases.items())]
    sudo_commands = sorted(set(policy.get("sudo_commands", [])), key=str)
    timer_value = policy.get("timer")
    forbidden = sorted(set(policy.get("forbidden", [])), key=str)
    extensions = policy.get("allowed_file_extensions", [])

    print(_paint("Policy Overview", "bold", color))
    print("-" * 15)
    print(f"Strict mode            : {strict_mode}")
    print(f"Warnings remaining     : {warnings_value}")
    print("")

    print(_paint("Command Access", "bold", color))
    print("-" * 14)
    print("Allowed commands       : ", end="")
    print(_format_wrapped_list(allowed_entries, indent=24))
    print("Allowed sudo           : ", end="")
    print(_format_wrapped_list(sudo_commands, indent=24))
    print("Aliases                : ", end="")
    print(_format_wrapped_list(alias_entries, indent=24))
    print(f"Timer                  : {timer_value}")
    print("")

    print(_paint("Security Constraints", "bold", color))
    print("-" * 20)
    print("Forbidden characters   : ", end="")
    print(_format_wrapped_list(forbidden, indent=24))
    if extensions:
        allowed_extensions = _format_wrapped_list(
            sorted(set(extensions), key=str), indent=24
        )
    else:
        allowed_extensions = "any"
    print("Allowed extensions     : " + allowed_extensions)
    print("")

    if command_line is not None and decision is not None:
        verdict = "ALLOW" if decision["allowed"] else "DENY"
        verdict_style = "green" if decision["allowed"] else "red"
        print(_paint("Command Check", "bold", color))
        print(f"Command       : {command_line}")
        print(
            "Decision      : "
            + _paint(verdict, verdict_style, color)
            + f" ({decision['reason']})"
        )


def main(argv):
    """Entry point for `lshell policy-show`."""
    parser = argparse.ArgumentParser(
        prog="lshell policy-show",
        description="Explain effective lshell policy resolution and command decision.",
    )
    parser.add_argument(
        "--config",
        default=variables.configfile,
        help=f"Config file location (default: {variables.configfile})",
    )
    parser.add_argument(
        "--user",
        default=getuser(),
        help="Target username (default: current user)",
    )
    parser.add_argument(
        "--group",
        action="append",
        default=[],
        help="Target group (repeatable, or comma-separated). First group has highest precedence.",
    )
    parser.add_argument(
        "--command",
        help="Command line to evaluate against resolved policy.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output.",
    )
    parser.add_argument(
        "command_args",
        nargs=argparse.REMAINDER,
        help="Optional command to evaluate, as trailing args after --",
    )
    args = parser.parse_args(argv)

    command_line = args.command
    if not command_line and args.command_args:
        if args.command_args and args.command_args[0] == "--":
            args.command_args = args.command_args[1:]
        command_line = " ".join(args.command_args).strip()
    configfile = os.path.realpath(args.config)
    if not os.path.exists(configfile):
        sys.stderr.write("lshell: config file doesn't exist\n")
        return 1

    groups = _resolve_user_groups(args.user, args.group)
    try:
        result = resolve_policy(configfile, args.user, groups)
        decision = None
        if command_line:
            decision = policy_command_decision(command_line, result["policy"])
    except ValueError as exception:
        sys.stderr.write(f"lshell: {exception}\n")
        return 1

    if args.json:
        payload = {
            "target": {"user": args.user, "groups": groups},
            "resolution": result,
            "command": command_line,
            "decision": decision,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_text(result, command_line, decision)

    if decision is None:
        return 0
    return 0 if decision["allowed"] else 2
