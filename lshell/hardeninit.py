"""Generate hardened baseline lshell configurations."""

import argparse
import configparser
import os
import re
import sys
from datetime import datetime, timezone

from lshell import configschema


SAFE_FORBIDDEN_OPERATORS = [";", "&", "|", "`", ">", "<", "$(", "${"]
REQUIRED_PROFILE_KEYS = {
    "allowed",
    "allowed_shell_escape",
    "forbidden",
    "warning_counter",
    "strict",
    "scp",
    "scp_upload",
    "scp_download",
    "sftp",
    "overssh",
}
UNSAFE_ALLOWED_SHELL_ESCAPE = {
    "awk",
    "bash",
    "dash",
    "env",
    "expect",
    "find",
    "fish",
    "ksh",
    "less",
    "lua",
    "man",
    "more",
    "nano",
    "nawk",
    "node",
    "perl",
    "php",
    "python",
    "python3",
    "ruby",
    "sed",
    "sh",
    "ssh",
    "vi",
    "vim",
    "xargs",
    "zsh",
}


PROFILE_DEFINITIONS = {
    "sftp-only": {
        "description": "SFTP transport only with no interactive remote command execution.",
        "global": {
            "logpath": "/var/log/lshell/",
            "loglevel": 2,
            "security_audit_json": 1,
        },
        "default": {
            "allowed": ["pwd", "ls", "cd"],
            "allowed_shell_escape": [],
            "forbidden": list(SAFE_FORBIDDEN_OPERATORS),
            "warning_counter": 2,
            "strict": 1,
            "scp": 0,
            "scp_upload": 0,
            "scp_download": 0,
            "sftp": 1,
            "overssh": [],
            "sudo_commands": [],
            "allowed_file_extensions": [],
            "path": [],
            "umask": "0077",
        },
        "explain": [
            "Use this for file-drop or file-retrieval accounts over SFTP.",
            "Interactive shell functionality is intentionally minimal.",
            "SCP is disabled to reduce protocol surface area.",
        ],
    },
    "rsync-backup": {
        "description": "Rsync over SSH for backup jobs with strict command controls.",
        "global": {
            "logpath": "/var/log/lshell/",
            "loglevel": 2,
            "security_audit_json": 1,
        },
        "default": {
            "allowed": ["rsync", "pwd"],
            "allowed_shell_escape": [],
            "forbidden": list(SAFE_FORBIDDEN_OPERATORS),
            "warning_counter": 2,
            "strict": 1,
            "scp": 0,
            "scp_upload": 0,
            "scp_download": 0,
            "sftp": 0,
            "overssh": ["rsync"],
            "sudo_commands": [],
            "allowed_file_extensions": [],
            "path": [],
            "umask": "0077",
        },
        "explain": [
            "Designed for backup endpoints that need rsync and little else.",
            "over-SSH commands are narrowed to rsync only.",
            "Strict mode enforces warning counter decrement on unknown syntax.",
        ],
    },
    "deploy-minimal": {
        "description": "Minimal deployment account for artifact sync and service rollout.",
        "global": {
            "logpath": "/var/log/lshell/",
            "loglevel": 2,
            "security_audit_json": 1,
        },
        "default": {
            "allowed": [
                "cat",
                "cp",
                "git",
                "ln",
                "ls",
                "mkdir",
                "mv",
                "pwd",
                "rsync",
                "scp",
                "tail",
                "touch",
            ],
            "allowed_shell_escape": [],
            "forbidden": list(SAFE_FORBIDDEN_OPERATORS),
            "warning_counter": 2,
            "strict": 1,
            "scp": 1,
            "scp_upload": 1,
            "scp_download": 0,
            "sftp": 0,
            "overssh": ["rsync", "scp"],
            "sudo_commands": [],
            "allowed_file_extensions": [".log", ".txt", ".yml", ".yaml"],
            "path": [],
            "umask": "0027",
        },
        "explain": [
            "Use when CI/CD or operators need tightly scoped deployment operations.",
            "SCP upload is enabled for controlled artifact delivery; download is disabled.",
            "Keep sudo disabled by default and elevate only in explicit user sections.",
        ],
    },
    "readonly-support": {
        "description": "Read-only troubleshooting profile for support and incident triage.",
        "global": {
            "logpath": "/var/log/lshell/",
            "loglevel": 2,
            "security_audit_json": 1,
        },
        "default": {
            "allowed": ["cat", "grep", "head", "ls", "pwd", "tail"],
            "allowed_shell_escape": [],
            "forbidden": list(SAFE_FORBIDDEN_OPERATORS),
            "warning_counter": 2,
            "strict": 1,
            "scp": 0,
            "scp_upload": 0,
            "scp_download": 0,
            "sftp": 0,
            "overssh": [],
            "sudo_commands": [],
            "allowed_file_extensions": [".conf", ".ini", ".json", ".log", ".txt", ".yaml"],
            "path": [],
            "umask": "0077",
        },
        "explain": [
            "Purpose-built for support users who should inspect but not modify systems.",
            "No SSH transfer protocols are enabled.",
            "allowed_file_extensions helps prevent access to unexpected file types.",
        ],
    },
}

FIELD_COMMENTS = {
    "allowed": "Explicit allow-list only; never use 'all' for hardened baselines.",
    "allowed_shell_escape": (
        "Commands here bypass noexec restrictions; keep this list empty unless "
        "you have a reviewed exception."
    ),
    "forbidden": "Deny shell control operators that enable chaining, redirection, or substitution.",
    "warning_counter": "Session is terminated after repeated violations. -1 disables termination.",
    "strict": "Strict mode treats unknown syntax as policy violations (recommended: 1).",
    "scp": "Enable/disable SCP protocol surface.",
    "scp_upload": "Allow SCP uploads only when operationally required.",
    "scp_download": "Allow SCP downloads only when operationally required.",
    "sftp": "Enable/disable SFTP protocol surface.",
    "overssh": "Commands allowed for direct SSH command execution; keep as small as possible.",
    "sudo_commands": "Keep empty by default. Add only audited, non-interactive commands.",
    "allowed_file_extensions": (
        "Optional file-type allow-list; empty means no extension restriction."
    ),
    "path": "Optional path restrictions; empty list disables path ACL enforcement.",
    "umask": "Conservative process umask for files created in shell sessions.",
    "logpath": "Centralized log directory used by lshell.",
    "loglevel": "Logging verbosity (0-4). Use >=2 for security operations.",
    "security_audit_json": "Enable JSON/ECS audit events for SIEM ingestion.",
}


def _format_value(value):
    if isinstance(value, str):
        return value if value.isdigit() else repr(value)
    return repr(value)


def list_templates():
    """Return template rows for display."""
    rows = []
    for name in sorted(PROFILE_DEFINITIONS):
        rows.append((name, PROFILE_DEFINITIONS[name]["description"]))
    return rows


def get_profile(name):
    """Fetch profile data by name or raise ValueError."""
    try:
        return PROFILE_DEFINITIONS[name]
    except KeyError as exception:
        available = ", ".join(sorted(PROFILE_DEFINITIONS))
        raise ValueError(
            f"Unknown profile '{name}'. Available profiles: {available}"
        ) from exception


def validate_profile(profile_name, profile_data):
    """Validate profile structure and security constraints."""
    errors = []
    default = profile_data.get("default", {})
    missing = sorted(REQUIRED_PROFILE_KEYS - set(default.keys()))
    if missing:
        errors.append(f"missing required keys in [default]: {', '.join(missing)}")

    allowed_value = default.get("allowed", [])
    if configschema.is_all_literal(allowed_value) or allowed_value == "all":
        errors.append("allowed must be an explicit list and cannot be 'all'")
    if not isinstance(allowed_value, list) or not allowed_value:
        errors.append("allowed must be a non-empty list")

    strict_value = default.get("strict")
    if strict_value != 1:
        errors.append("strict must be set to 1 for hardened profiles")

    forbidden_value = default.get("forbidden", [])
    if not isinstance(forbidden_value, list):
        errors.append("forbidden must be a list")
    else:
        missing_ops = [item for item in SAFE_FORBIDDEN_OPERATORS if item not in forbidden_value]
        if missing_ops:
            errors.append(
                "forbidden list is missing hardened operators: " + ", ".join(missing_ops)
            )

    shell_escape_value = default.get("allowed_shell_escape", [])
    if shell_escape_value == "all" or configschema.is_all_literal(shell_escape_value):
        errors.append("allowed_shell_escape cannot be 'all'")
    if not isinstance(shell_escape_value, list):
        errors.append("allowed_shell_escape must be a list")
    else:
        for raw_command in shell_escape_value:
            base_command = raw_command.strip().split(" ", maxsplit=1)[0].lower()
            if base_command in UNSAFE_ALLOWED_SHELL_ESCAPE:
                errors.append(
                    "allowed_shell_escape contains unsafe command: " + raw_command
                )

    for key in ("scp", "scp_upload", "scp_download", "sftp", "warning_counter"):
        value = default.get(key)
        if not isinstance(value, int):
            errors.append(f"{key} must be an integer")

    for key in ("overssh", "sudo_commands", "allowed_file_extensions", "path"):
        value = default.get(key)
        if not isinstance(value, list):
            errors.append(f"{key} must be a list")

    if profile_name == "sftp-only":
        if default.get("sftp") != 1 or default.get("scp") != 0:
            errors.append("sftp-only profile must set sftp=1 and scp=0")
        if default.get("overssh"):
            errors.append("sftp-only profile must keep overssh empty")
    elif profile_name == "rsync-backup":
        if "rsync" not in default.get("allowed", []):
            errors.append("rsync-backup profile must allow rsync")
        if default.get("overssh") != ["rsync"]:
            errors.append("rsync-backup profile must set overssh to ['rsync']")
    elif profile_name == "readonly-support":
        if any(default.get(key) != 0 for key in ("scp", "sftp", "scp_upload", "scp_download")):
            errors.append("readonly-support profile must disable SCP and SFTP")

    return errors


def run_sanity_checks(rendered_config):
    """Sanity-parse generated config and return (ok, details)."""
    return run_sanity_checks_for_targets(rendered_config, [])


def run_sanity_checks_for_targets(rendered_config, target_sections):
    """Sanity-parse generated config and validate required section keys."""
    details = []
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(rendered_config)
    except (configparser.Error, OSError) as exception:
        return False, [f"parser: fail ({exception})"]
    details.append("parser: pass")

    if not parser.has_section("global"):
        details.append("global-section: fail (missing [global])")
        return False, details
    details.append("global-section: pass")

    if not target_sections:
        if not parser.has_section("default"):
            details.append("default-section: fail (missing [default])")
            return False, details
        details.append("default-section: pass")
        target_sections = ["default"]
    else:
        for section in target_sections:
            if not parser.has_section(section):
                details.append(f"{section}: fail (missing section)")
                return False, details
            details.append(f"{section}: pass")

    for section in target_sections:
        for key in REQUIRED_PROFILE_KEYS:
            if not parser.has_option(section, key):
                details.append(f"{section}.{key}: fail (missing)")
                return False, details
            raw_value = parser.get(section, key)
            try:
                configschema.parse_config_value(raw_value, key)
                details.append(f"{section}.{key}: pass")
            except ValueError as exception:
                details.append(f"{section}.{key}: fail ({exception})")
                return False, details

    return True, details


def _render_section(lines, section_name, values):
    lines.extend(["", f"[{section_name}]"])
    for key, value in values.items():
        comment = FIELD_COMMENTS.get(key)
        if comment:
            lines.append(f"# {comment}")
        lines.append(f"{key:<15} : {_format_value(value)}")


def render_profile(profile_name, profile_data, groups=None, users=None):
    """Render profile as lshell configuration text with inline comments."""
    groups = groups or []
    users = users or []
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    lines = [
        "# Generated by: lshell harden-init",
        f"# Profile: {profile_name}",
        f"# Generated (UTC): {timestamp}",
        "# Review this baseline and scope per-user/group overrides as needed.",
        "",
        "[global]",
    ]

    for key, value in profile_data["global"].items():
        comment = FIELD_COMMENTS.get(key)
        if comment:
            lines.append(f"# {comment}")
        lines.append(f"{key:<15} : {_format_value(value)}")

    if groups or users:
        lines.append("# Scoped profile sections generated from CLI target flags.")
        lines.append("# No [default] section is emitted to avoid global policy impact.")
        for group_name in groups:
            _render_section(lines, f"grp:{group_name}", profile_data["default"])
        for user_name in users:
            _render_section(lines, f"user:{user_name}", profile_data["default"])
    else:
        _render_section(lines, "default", profile_data["default"])

    lines.append("")
    return "\n".join(lines)


def explain_profile(profile_name, profile_data):
    """Return human-readable hardening rationale for a profile."""
    lines = [f"Profile: {profile_name}", f"Purpose: {profile_data['description']}", "Controls:"]
    lines.extend(f"- {item}" for item in profile_data["explain"])
    return "\n".join(lines)


def _print_sanity_checks(details, ok):
    for item in details:
        print(f"sanity: {item}")
    print("sanity: overall: pass" if ok else "sanity: overall: fail")


def _write_output(path, rendered_config):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(rendered_config)


def _default_output_path(profile_name):
    return f"/etc/lshell.d/{profile_name}.conf"


def _run_wizard():
    print("lshell harden-init wizard")
    print("Select a hardened profile:")
    rows = list_templates()
    for index, row in enumerate(rows, start=1):
        print(f"  {index}. {row[0]} - {row[1]}")

    selection = input("Profile name or number: ").strip()
    if selection.isdigit():
        value = int(selection)
        if value < 1 or value > len(rows):
            print("lshell harden-init: invalid profile selection", file=sys.stderr)
            return 1
        profile_name = rows[value - 1][0]
    else:
        profile_name = selection

    try:
        profile_data = get_profile(profile_name)
    except ValueError as exception:
        print(f"lshell harden-init: {exception}", file=sys.stderr)
        return 1

    output_path = input(
        f"Output file path [{_default_output_path(profile_name)}]: "
    ).strip() or _default_output_path(profile_name)
    group_name = input("Optional target group (blank for none): ").strip()
    user_name = input("Optional target user (blank for none): ").strip()
    groups = [group_name] if group_name else []
    users = [user_name] if user_name else []

    rendered = render_profile(profile_name, profile_data, groups=groups, users=users)
    errors = validate_profile(profile_name, profile_data)
    if errors:
        for error in errors:
            print(f"lshell harden-init: validation failed: {error}", file=sys.stderr)
        return 1

    target_sections = [f"grp:{item}" for item in groups] + [f"user:{item}" for item in users]
    ok, details = run_sanity_checks_for_targets(rendered, target_sections)
    _print_sanity_checks(details, ok)
    if not ok:
        return 1

    _write_output(output_path, rendered)
    print(f"lshell harden-init: wrote {output_path}")
    return 0


def build_parser():
    """Build argparse parser for harden-init mode."""
    parser = argparse.ArgumentParser(
        prog="lshell harden-init",
        description="Generate secure-by-default lshell policy baseline profiles.",
    )
    parser.add_argument(
        "--list-templates",
        action="store_true",
        help="List available hardened templates.",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILE_DEFINITIONS),
        help="Template/profile to render.",
    )
    parser.add_argument(
        "--output",
        help="Write rendered config to this path.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Write rendered config to standard output.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render config and run sanity checks without writing files.",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Print profile hardening rationale.",
    )
    parser.add_argument(
        "--group",
        action="append",
        default=[],
        help="Generate a scoped [grp:<name>] section (repeatable).",
    )
    parser.add_argument(
        "--user",
        action="append",
        default=[],
        help="Generate a scoped [user:<name>] section (repeatable).",
    )
    return parser


def _validate_target_names(label, values):
    pattern = re.compile(r"^[A-Za-z0-9_.-]+$")
    errors = []
    for item in values:
        if not pattern.match(item):
            errors.append(
                f"invalid {label} name '{item}'. Use letters, digits, underscore, dot, or dash."
            )
    return errors


def main(argv=None):
    """Entry point for `lshell harden-init`."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_templates:
        if args.group or args.user:
            parser.error("--group/--user cannot be used with --list-templates")
        for name, description in list_templates():
            print(f"{name:<18} {description}")
        return 0

    if not args.profile:
        if sys.stdin.isatty() and sys.stdout.isatty():
            return _run_wizard()
        parser.error("missing --profile. Use --list-templates to discover options.")

    if args.output and args.stdout:
        parser.error("--output and --stdout cannot be used together")
    if not args.output and not args.stdout and not args.dry_run:
        args.output = _default_output_path(args.profile)

    profile_name = args.profile
    profile_data = get_profile(profile_name)
    target_errors = []
    target_errors.extend(_validate_target_names("group", args.group))
    target_errors.extend(_validate_target_names("user", args.user))
    if target_errors:
        for error in target_errors:
            print(f"lshell harden-init: {error}", file=sys.stderr)
        return 1

    validation_errors = validate_profile(profile_name, profile_data)
    if validation_errors:
        for error in validation_errors:
            print(f"lshell harden-init: validation failed: {error}", file=sys.stderr)
        return 1

    rendered = render_profile(
        profile_name, profile_data, groups=args.group, users=args.user
    )
    target_sections = [f"grp:{item}" for item in args.group] + [
        f"user:{item}" for item in args.user
    ]
    ok, details = run_sanity_checks_for_targets(rendered, target_sections)
    if args.dry_run:
        print(rendered.rstrip())
        _print_sanity_checks(details, ok)
        if args.explain:
            print("")
            print(explain_profile(profile_name, profile_data))
        return 0 if ok else 1

    if not ok:
        _print_sanity_checks(details, ok)
        return 1

    if args.explain:
        print(explain_profile(profile_name, profile_data))

    if args.stdout:
        print(rendered.rstrip())
        return 0

    try:
        _write_output(args.output, rendered)
    except OSError as exception:
        print(f"lshell harden-init: {exception}", file=sys.stderr)
        return 1

    print(f"lshell harden-init: wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
