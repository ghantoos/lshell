"""Configuration validation helpers for lshell."""

import configparser
import difflib
import glob
import os
import sys
from dataclasses import dataclass, field
from typing import List

from lshell import variables
from lshell.checkconfig import CheckConfig


GLOBAL_KEYS = {
    "logpath",
    "loglevel",
    "logfilename",
    "syslogname",
    "include_dir",
    "path_noexec",
}

PROFILE_KEYS = {
    "loglevel",
    "allowed",
    "allowed_shell_escape",
    "allowed_file_extensions",
    "forbidden",
    "sudo_commands",
    "warning_counter",
    "env_vars",
    "env_vars_files",
    "timer",
    "scp",
    "scp_upload",
    "scp_download",
    "sftp",
    "overssh",
    "strict",
    "aliases",
    "prompt",
    "prompt_short",
    "allowed_cmd_path",
    "history_size",
    "history_file",
    "login_script",
    "winscp",
    "disable_exit",
    "quiet",
    "home_path",
    "env_path",
    "scpforce",
    "intro",
    "passwd",
    "path",
    "umask",
}

HIGH_RISK_SHELL_ESCAPE = {
    "find",
    "vim",
    "vi",
    "nvim",
    "python",
    "python3",
    "perl",
    "ruby",
    "awk",
    "xargs",
}


@dataclass
class ValidationReport:
    """Simple accumulator for validation diagnostics."""

    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    infos: List[str] = field(default_factory=list)

    def add_error(self, message):
        self.errors.append(message)

    def add_warning(self, message):
        self.warnings.append(message)

    def add_info(self, message):
        self.infos.append(message)

    def ok(self):
        return not self.errors


def _is_profile_section(section_name):
    if section_name in {"default"}:
        return True
    if section_name.startswith("grp:") and len(section_name) > 4:
        return True
    if section_name.startswith("grp:"):
        return False
    return True


def _suggest_key(option_name, allowed_keys):
    suggestions = difflib.get_close_matches(option_name, sorted(allowed_keys), n=1)
    if suggestions:
        return f" (did you mean '{suggestions[0]}'?)"
    return ""


def _validate_parser_sections(config, source, report):
    for section in config.sections():
        if section == "global":
            continue
        if not _is_profile_section(section):
            report.add_error(
                f"{source}: invalid section '{section}'. "
                "Expected [global], [default], [grp:<group>], or [<username>]."
            )


def _validate_parser_options(config, source, report):
    for section in config.sections():
        allowed_keys = GLOBAL_KEYS if section == "global" else PROFILE_KEYS
        for option_name, _ in config.items(section):
            if option_name not in allowed_keys:
                hint = _suggest_key(option_name, allowed_keys)
                report.add_error(
                    f"{source}: unknown key '{option_name}' in section [{section}]{hint}"
                )


def _read_config_file(path, report):
    parser = configparser.ConfigParser(interpolation=None)
    try:
        with open(path, "r", encoding="utf-8") as config_file:
            parser.read_file(config_file)
    except (OSError, UnicodeDecodeError) as exception:
        report.add_error(f"{path}: unable to read config file ({exception})")
        return None
    except (
        configparser.MissingSectionHeaderError,
        configparser.ParsingError,
        configparser.DuplicateOptionError,
        configparser.DuplicateSectionError,
    ) as exception:
        report.add_error(f"{path}: parse error ({exception})")
        return None
    return parser


def _extract_config_path(args):
    config_path = variables.configfile
    index = 0
    while index < len(args):
        item = args[index]
        if item.startswith("--config="):
            config_path = os.path.realpath(item.split("=", 1)[1])
        elif item == "--config" and index + 1 < len(args):
            config_path = os.path.realpath(args[index + 1])
            index += 1
        index += 1
    return config_path


def _normalize_include_pattern(raw_value):
    cleaned = raw_value.strip().strip("\"'")
    return f"{cleaned}*"


def _validate_static_config(args, report):
    config_path = _extract_config_path(args)
    if not os.path.exists(config_path):
        report.add_error(f"{config_path}: config file does not exist")
        return config_path

    parser = _read_config_file(config_path, report)
    if parser is None:
        return config_path

    if not parser.has_section("global"):
        report.add_error(f"{config_path}: missing [global] section")
        return config_path

    _validate_parser_sections(parser, config_path, report)
    _validate_parser_options(parser, config_path, report)

    include_dir_raw = parser.get("global", "include_dir", fallback=None)
    if include_dir_raw:
        include_pattern = _normalize_include_pattern(include_dir_raw)
        include_files = sorted(glob.glob(include_pattern))
        if not include_files:
            report.add_warning(
                f"{config_path}: include_dir matched no files ({include_pattern})"
            )
        for include_file in include_files:
            include_parser = _read_config_file(include_file, report)
            if include_parser is None:
                continue
            if include_parser.has_section("global"):
                report.add_error(
                    f"{include_file}: [global] is not allowed in include_dir files"
                )
            _validate_parser_sections(include_parser, include_file, report)
            _validate_parser_options(include_parser, include_file, report)

    return config_path


def _security_lints(conf, report):
    warning_counter = conf.get("warning_counter")
    if warning_counter == -1:
        report.add_warning("warning_counter is -1 (users are never disconnected).")

    strict = conf.get("strict")
    if strict == 0:
        report.add_warning("strict is disabled (unknown commands do not decrement warnings).")

    forbidden = set(conf.get("forbidden", []))
    for recommended in [";", "|", "`", "$(", "${"]:
        if recommended not in forbidden:
            report.add_warning(
                f"forbidden does not contain recommended hardening token '{recommended}'."
            )

    allowed_shell_escape = set(conf.get("allowed_shell_escape", []))
    risky = sorted(HIGH_RISK_SHELL_ESCAPE.intersection(allowed_shell_escape))
    if risky:
        report.add_warning(
            "allowed_shell_escape contains high-risk commands: " + ", ".join(risky)
        )

    if not conf.get("path_noexec"):
        report.add_warning(
            "noexec library is not active (LD_PRELOAD hardening unavailable)."
        )


def run_validate(raw_args, stdout=None, stderr=None):
    """Run config validation and return a process exit code."""
    if stdout is None:
        stdout = sys.stdout
    if stderr is None:
        stderr = sys.stderr

    report = ValidationReport()
    strict_warnings = False
    passthrough_args = []

    index = 0
    while index < len(raw_args):
        option = raw_args[index]
        if option in {"-h", "--help"}:
            stdout.write(
                "Usage: lshell validate [OPTIONS] [lshell-overrides]\n"
                "  --strict-warnings : Return non-zero if warnings exist\n"
                "  -h, --help        : Show this help message\n"
            )
            return 0
        if option == "--strict-warnings":
            strict_warnings = True
        else:
            passthrough_args.append(option)
        index += 1

    config_path = _validate_static_config(passthrough_args, report)

    if report.ok():
        try:
            conf = CheckConfig(passthrough_args, validate_mode=True).returnconf()
        except SystemExit as exception:
            exit_code = exception.code if isinstance(exception.code, int) else 1
            report.add_error(
                f"semantic validation failed while loading '{config_path}' (exit {exit_code})."
            )
        else:
            _security_lints(conf, report)
            report.add_info(
                f"validated effective policy for user '{conf.get('username', 'unknown')}'."
            )

    if report.errors:
        stderr.write("FAIL: configuration is invalid\n")
        for entry in report.errors:
            stderr.write(f"  - {entry}\n")
        if report.warnings:
            stderr.write("WARNINGS:\n")
            for entry in report.warnings:
                stderr.write(f"  - {entry}\n")
        return 1

    stdout.write("OK: configuration is valid\n")
    stdout.write(f"Config: {config_path}\n")
    for entry in report.infos:
        stdout.write(f"INFO: {entry}\n")
    if report.warnings:
        stdout.write(f"WARN: {len(report.warnings)} warning(s)\n")
        for entry in report.warnings:
            stdout.write(f"  - {entry}\n")
        return 1 if strict_warnings else 2

    return 0
