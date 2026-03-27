"""Canonical policy authorizer shared by runtime and diagnostics."""

import os
import re
from typing import NamedTuple

from lshell import sec
from lshell.engine import normalizer
from lshell.engine import parser as engine_parser
from lshell.engine import reasons


class AuthorizationDecision(NamedTuple):
    """Authorization result for one canonical AST."""

    allowed: bool
    reason: reasons.Reason
    ast: object


def _deny(code, ast, **details):
    return AuthorizationDecision(False, reasons.make_reason(code, **details), ast)


def _allow(ast, reason_text="allowed by final policy"):
    return AuthorizationDecision(
        True, reasons.make_reason(reasons.ALLOWED, reason=reason_text), ast
    )


def _allowed_commands(policy, ssh=False):
    if ssh:
        return set(policy.get("overssh", []))
    return set(policy.get("allowed", []))


def _is_path_allowed(policy, candidate):
    path_acl = policy.get("path", ["", ""])
    allow = path_acl[0] if len(path_acl) > 0 else ""
    deny = path_acl[1] if len(path_acl) > 1 else ""
    allowed_roots = sec._split_path_acl_entries(allow)
    denied_roots = sec._split_path_acl_entries(deny)
    return sec._is_path_allowed(candidate, allowed_roots, denied_roots)


def _first_path_violation(line, policy, check_current_dir=False):
    path_tokens = sec._path_tokens_from_line(line)

    for item in path_tokens:
        candidates = sec.expand_shell_wildcards(item)
        if not candidates:
            return item

        for candidate in candidates:
            if not _is_path_allowed(policy, candidate):
                return sec._format_path_for_message(candidate)

    if check_current_dir:
        current_dir = os.path.realpath(os.getcwd())
        if not _is_path_allowed(policy, current_dir):
            return sec._format_path_for_message(current_dir)

    return None


def _forbidden_char_violation(line, policy):
    for item in policy.get("forbidden", []):
        if item in ["&", "|"]:
            escaped_item = re.escape(item)
            if re.search(rf"(?<!{escaped_item}){escaped_item}(?!{escaped_item})", line):
                return item
        elif item in line:
            return item
    return None


def forbidden_chars_decision(line, policy, ast=None):
    """Return a denial decision if forbidden-char policy is violated."""
    token = _forbidden_char_violation(line, policy)
    if token is None:
        return None
    return AuthorizationDecision(
        False,
        reasons.make_reason(reasons.FORBIDDEN_CHARACTER, token=token, line=line),
        ast,
    )


def _authorize_nested(inner_line, policy, mode, ssh, depth):
    return authorize_line(
        inner_line,
        policy,
        mode=mode,
        ssh=ssh,
        check_current_dir=False,
        depth=depth + 1,
    )


def _quoted_literals_without_assignment(line):
    """Extract quoted literals, excluding immediate assignment values (e.g. X=\"...\")."""
    literals = []
    index = 0
    length = len(line)

    while index < length:
        quote = line[index]
        if quote not in {"'", '"'}:
            index += 1
            continue

        previous = line[index - 1] if index > 0 else ""
        index += 1
        chunk = []
        escaped = False

        while index < length:
            char = line[index]
            if quote == '"' and escaped:
                chunk.append(char)
                escaped = False
                index += 1
                continue
            if quote == '"' and char == "\\":
                escaped = True
                index += 1
                continue
            if char == quote:
                break
            chunk.append(char)
            index += 1

        if index < length and line[index] == quote:
            chunk_text = "".join(chunk)
            if previous != "=":
                literals.append(chunk_text)
            if quote == "'":
                literals.extend(_quoted_literals_without_assignment(chunk_text))
        index += 1

    return literals


def authorize(
    canonical_ast, policy, mode="runtime", ssh=False, check_current_dir=None, depth=0
):
    """Authorize a canonical AST using one unified rule path."""
    if check_current_dir is None:
        check_current_dir = mode == "runtime"

    if depth > 8:
        return _deny(
            reasons.UNKNOWN_SYNTAX,
            canonical_ast,
            command=canonical_ast.line,
            line=canonical_ast.line,
        )

    if canonical_ast.parse_error:
        return _deny(
            reasons.UNKNOWN_SYNTAX,
            canonical_ast,
            command=canonical_ast.line,
            line=canonical_ast.line,
        )

    oline = canonical_ast.line
    line = oline.strip()

    for item in _quoted_literals_without_assignment(line):
        if os.path.exists(item):
            violation = _first_path_violation(item, policy, check_current_dir=False)
            if violation:
                return _deny(
                    reasons.FORBIDDEN_PATH,
                    canonical_ast,
                    path=violation,
                    line=oline,
                )

    if re.findall(r"[\x01-\x1F\x7F]", oline):
        return _deny(
            reasons.FORBIDDEN_CONTROL_CHAR,
            canonical_ast,
            line=oline,
        )

    forbidden_item = _forbidden_char_violation(line, policy)
    if forbidden_item is not None:
        return _deny(
            reasons.FORBIDDEN_CHARACTER,
            canonical_ast,
            token=forbidden_item,
            line=oline,
        )

    executions = re.findall(r"\$\([^)]+[)]", line)
    for item in executions:
        inner = item[2:-1].strip()
        violation = _first_path_violation(inner, policy, check_current_dir=False)
        if violation:
            return _deny(
                reasons.FORBIDDEN_PATH,
                canonical_ast,
                path=violation,
                line=oline,
            )

        nested_decision = _authorize_nested(inner, policy, mode, ssh, depth)
        if not nested_decision.allowed:
            return nested_decision

    backticks = re.findall(r"\`[^`]+[`]", line)
    for item in backticks:
        nested_decision = _authorize_nested(
            item[1:-1].strip(), policy, mode, ssh, depth
        )
        if not nested_decision.allowed:
            return nested_decision

    curly = re.findall(r"\$\{[^}]+[}]", line)
    for item in curly:
        if re.findall(r"=|\+|\?|\-", item):
            variable = re.split(r"=|\+|\?|\-", item, maxsplit=1)
        else:
            variable = item

        try:
            variable_text = variable[1][:-1]
        except (IndexError, TypeError):
            variable_text = ""

        violation = _first_path_violation(
            variable_text, policy, check_current_dir=False
        )
        if violation:
            return _deny(
                reasons.FORBIDDEN_PATH,
                canonical_ast,
                path=violation,
                line=oline,
            )

    allowed_commands = _allowed_commands(policy, ssh=ssh)

    for command_node in canonical_ast.commands:
        command = command_node.executable
        command_args_list = list(command_node.args)
        full_command = command_node.full_command

        if command == "sudo" and command_args_list:
            if command_args_list[0] == "-u":
                if len(command_args_list) < 3:
                    return _deny(
                        reasons.FORBIDDEN_SUDO_COMMAND,
                        canonical_ast,
                        command="",
                        line=oline,
                        missing_target=True,
                    )
                sudocmd = command_args_list[2]
            else:
                sudocmd = command_args_list[0]

            if sudocmd not in policy.get("sudo_commands", []):
                return _deny(
                    reasons.FORBIDDEN_SUDO_COMMAND,
                    canonical_ast,
                    command=sudocmd,
                    line=oline,
                    missing_target=False,
                )

        if (
            full_command not in allowed_commands
            and command not in allowed_commands
            and command
        ):
            if policy.get("strict"):
                return _deny(
                    reasons.FORBIDDEN_COMMAND,
                    canonical_ast,
                    command=command,
                    line=oline,
                )
            return _deny(
                reasons.UNKNOWN_SYNTAX,
                canonical_ast,
                command=full_command,
                line=oline,
            )

        allowed_extensions = policy.get("allowed_file_extensions")
        if allowed_extensions and sec.should_enforce_file_extensions(command):
            check_extensions, disallowed_extensions = sec.check_allowed_file_extensions(
                full_command, allowed_extensions
            )
            if check_extensions is False:
                return _deny(
                    reasons.FORBIDDEN_FILE_EXTENSION,
                    canonical_ast,
                    disallowed_extensions=disallowed_extensions,
                    full_command=full_command,
                    line=oline,
                )

    violation = _first_path_violation(
        oline,
        policy,
        check_current_dir=bool(check_current_dir),
    )
    if violation:
        return _deny(
            reasons.FORBIDDEN_PATH,
            canonical_ast,
            path=violation,
            line=oline,
        )

    return _allow(canonical_ast)


def authorize_line(
    line,
    policy,
    mode="runtime",
    ssh=False,
    check_current_dir=None,
    depth=0,
):
    """Convenience helper: parse -> normalize -> authorize."""
    parsed = engine_parser.parse(line)
    canonical = normalizer.normalize(parsed)
    return authorize(
        canonical,
        policy,
        mode=mode,
        ssh=ssh,
        check_current_dir=check_current_dir,
        depth=depth,
    )


__all__ = [
    "AuthorizationDecision",
    "authorize",
    "authorize_line",
    "forbidden_chars_decision",
]
