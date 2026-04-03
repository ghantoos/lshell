"""Shared expansion scanner/inspector used by sec and authorizer."""

import re
from typing import NamedTuple


MAX_EXPANSION_RECURSION = 8
MAX_EXPANSION_SCAN_CHARS = 32768
MAX_EXPANSION_TOKENS = 512

_PARAMETER_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PARAMETER_LENGTH_RE = re.compile(r"^#[A-Za-z_][A-Za-z0-9_]*$")
_PARAMETER_OPERATOR_RE = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_]*)(:?[-+=?])(.*)$", re.DOTALL
)


class _ShellExpansion(NamedTuple):
    """Parsed shell expansion from an input line."""

    kind: str
    body: str


class _ExpansionInspection(NamedTuple):
    """Security-oriented view of shell expansions in one command line."""

    executable_expansions: tuple
    parameter_path_probes: tuple
    malformed: bool


def _read_backtick_expansion(line, start):
    """Read a backtick expansion beginning at start and return (end, body)."""
    i = start + 1
    escaped = False
    while i < len(line):
        char = line[i]
        if escaped:
            escaped = False
            i += 1
            continue
        if char == "\\":
            escaped = True
            i += 1
            continue
        if char == "`":
            return i + 1, line[start + 1 : i]
        i += 1
    return None, None


def _read_parenthesized_expansion(line, start, prefix_len=2):
    """Read a balanced (...) expansion body for $(), <(), >()."""
    i = start + prefix_len
    in_single = False
    in_double = False
    in_backtick = False
    escaped = False
    paren_depth = 1
    parameter_depth = 0

    while i < len(line):
        char = line[i]
        next_char = line[i + 1] if i + 1 < len(line) else ""

        if escaped:
            escaped = False
            i += 1
            continue

        if char == "\\" and not in_single:
            escaped = True
            i += 1
            continue

        if char == "'" and not in_double and not in_backtick:
            in_single = not in_single
            i += 1
            continue

        if char == '"' and not in_single and not in_backtick:
            in_double = not in_double
            i += 1
            continue

        if char == "`" and not in_single:
            in_backtick = not in_backtick
            i += 1
            continue

        if in_single or in_double or in_backtick:
            i += 1
            continue

        if char == "$" and next_char == "{":
            parameter_depth += 1
            i += 2
            continue

        if char == "}" and parameter_depth > 0:
            parameter_depth -= 1
            i += 1
            continue

        if parameter_depth > 0:
            i += 1
            continue

        if char == "(":
            paren_depth += 1
            i += 1
            continue

        if char == ")":
            paren_depth -= 1
            if paren_depth == 0:
                return i + 1, line[start + prefix_len : i]
            if paren_depth < 0:
                return None, None
            i += 1
            continue

        i += 1

    return None, None


def _read_parameter_expansion(line, start):
    """Read a balanced ${...} expansion body from start."""
    i = start + 2
    in_single = False
    in_double = False
    in_backtick = False
    escaped = False
    parameter_depth = 1

    while i < len(line):
        char = line[i]
        next_char = line[i + 1] if i + 1 < len(line) else ""

        if escaped:
            escaped = False
            i += 1
            continue

        if char == "\\" and not in_single:
            escaped = True
            i += 1
            continue

        if char == "'" and not in_double and not in_backtick:
            in_single = not in_single
            i += 1
            continue

        if char == '"' and not in_single and not in_backtick:
            in_double = not in_double
            i += 1
            continue

        if char == "`" and not in_single:
            in_backtick = not in_backtick
            i += 1
            continue

        if in_single or in_double or in_backtick:
            i += 1
            continue

        if char == "$" and next_char == "{":
            parameter_depth += 1
            i += 2
            continue

        if char == "}":
            parameter_depth -= 1
            if parameter_depth == 0:
                return i + 1, line[start + 2 : i]
            if parameter_depth < 0:
                return None, None
            i += 1
            continue

        i += 1

    return None, None


def _read_arithmetic_expansion(line, start):
    """Read a balanced $((...)) arithmetic expansion body from start."""
    i = start + 3
    in_single = False
    in_double = False
    in_backtick = False
    escaped = False
    paren_depth = 1
    parameter_depth = 0

    while i < len(line):
        char = line[i]
        next_char = line[i + 1] if i + 1 < len(line) else ""

        if escaped:
            escaped = False
            i += 1
            continue

        if char == "\\" and not in_single:
            escaped = True
            i += 1
            continue

        if char == "'" and not in_double and not in_backtick:
            in_single = not in_single
            i += 1
            continue

        if char == '"' and not in_single and not in_backtick:
            in_double = not in_double
            i += 1
            continue

        if char == "`" and not in_single:
            in_backtick = not in_backtick
            i += 1
            continue

        if in_single or in_double or in_backtick:
            i += 1
            continue

        if char == "$" and next_char == "{":
            parameter_depth += 1
            i += 2
            continue

        if char == "}" and parameter_depth > 0:
            parameter_depth -= 1
            i += 1
            continue

        if parameter_depth > 0:
            i += 1
            continue

        if char == "(":
            paren_depth += 1
            i += 1
            continue

        if char == ")":
            paren_depth -= 1
            if paren_depth == 0:
                if next_char != ")":
                    return None, None
                return i + 2, line[start + 3 : i]
            if paren_depth < 0:
                return None, None
            i += 1
            continue

        i += 1

    return None, None


def _scan_shell_expansions_with_status(
    line,
    command_context=True,
    allow_process_substitution=True,
):
    """Parse shell expansions and report malformed/unsupported markers."""
    if len(line) > MAX_EXPANSION_SCAN_CHARS:
        return [], True

    expansions = []
    malformed = False
    i = 0
    in_single = False
    in_double = False
    escaped = False

    while i < len(line):
        if len(expansions) > MAX_EXPANSION_TOKENS:
            malformed = True
            break

        char = line[i]
        next_char = line[i + 1] if i + 1 < len(line) else ""

        if escaped:
            escaped = False
            i += 1
            continue

        if char == "\\" and not in_single:
            escaped = True
            i += 1
            continue

        if char == "'" and not in_double:
            in_single = not in_single
            i += 1
            continue

        if char == '"' and not in_single:
            in_double = not in_double
            i += 1
            continue

        if in_single:
            i += 1
            continue

        if char == "$" and next_char in {"'", '"'}:
            malformed = True
            break

        if command_context and not in_double:
            if line.startswith("<<<", i) or line.startswith("<<-", i) or line.startswith(
                "<<", i
            ):
                malformed = True
                break

        if char == "$" and next_char == "(" and i + 2 < len(line) and line[i + 2] == "(":
            end, body = _read_arithmetic_expansion(line, i)
            if end is None:
                malformed = True
                break
            if body:
                expansions.append(_ShellExpansion("arithmetic_expansion", body))
            i = end
            continue

        if char == "$" and next_char == "(":
            end, body = _read_parenthesized_expansion(line, i, prefix_len=2)
            if end is None:
                malformed = True
                break
            if body:
                expansions.append(_ShellExpansion("command_substitution", body))
            i = end
            continue

        if char == "$" and next_char == "{":
            end, body = _read_parameter_expansion(line, i)
            if end is None:
                malformed = True
                break
            if body:
                expansions.append(_ShellExpansion("parameter_expansion", body))
            i = end
            continue

        if (
            allow_process_substitution
            and not in_double
            and char in {"<", ">"}
            and next_char == "("
        ):
            end, body = _read_parenthesized_expansion(line, i, prefix_len=2)
            if end is None:
                malformed = True
                break
            if body:
                expansions.append(_ShellExpansion("process_substitution", body))
            i = end
            continue

        if char == "`":
            end, body = _read_backtick_expansion(line, i)
            if end is None:
                malformed = True
                break
            if body:
                expansions.append(_ShellExpansion("backtick", body))
            i = end
            continue

        i += 1

    return expansions, malformed


def _scan_shell_expansions(line):
    """Parse shell expansions in-order while honoring quotes/escapes."""
    expansions, _malformed = _scan_shell_expansions_with_status(line)
    return expansions


def inspect_shell_expansions(line, max_parameter_depth=MAX_EXPANSION_RECURSION):
    """Collect recursive expansion checks for security policy evaluation."""
    executable_expansions = []
    parameter_path_probes = []
    malformed = False
    scanned_expansions = 0

    def _walk(current_line, depth, command_context, allow_process_substitution):
        nonlocal malformed, scanned_expansions

        if depth > max_parameter_depth:
            malformed = True
            return

        expansions, scan_malformed = _scan_shell_expansions_with_status(
            current_line,
            command_context=command_context,
            allow_process_substitution=allow_process_substitution,
        )
        if scan_malformed:
            malformed = True

        for expansion in expansions:
            scanned_expansions += 1
            if scanned_expansions > MAX_EXPANSION_TOKENS:
                malformed = True
                return

            if expansion.kind in {
                "command_substitution",
                "backtick",
                "process_substitution",
            }:
                body = expansion.body.strip()
                if body:
                    executable_expansions.append(
                        _ShellExpansion(expansion.kind, body)
                    )
                continue

            if expansion.kind == "arithmetic_expansion":
                body = expansion.body.strip()
                if body:
                    _walk(
                        body,
                        depth + 1,
                        command_context=False,
                        allow_process_substitution=False,
                    )
                continue

            if expansion.kind != "parameter_expansion":
                continue

            supported, probe = _analyze_parameter_expansion(expansion.body)
            if not supported:
                malformed = True
                continue

            probe = probe.strip()
            if probe:
                parameter_path_probes.append(probe)

            body = expansion.body.strip()
            if body:
                _walk(
                    body,
                    depth + 1,
                    command_context=False,
                    allow_process_substitution=True,
                )

    _walk(
        line,
        depth=0,
        command_context=True,
        allow_process_substitution=True,
    )
    return _ExpansionInspection(
        executable_expansions=tuple(executable_expansions),
        parameter_path_probes=tuple(parameter_path_probes),
        malformed=malformed,
    )


def _parameter_expansion_path_probe(expression):
    """Return the value-side text from supported ${...} forms."""
    supported, probe = _analyze_parameter_expansion(expression)
    if not supported:
        return ""
    return probe


def _analyze_parameter_expansion(expression):
    """Return (supported, probe_text) for parameter-expansion expressions."""
    stripped = expression.strip()
    if not stripped:
        return False, ""

    if _PARAMETER_NAME_RE.fullmatch(stripped):
        return True, ""

    if _PARAMETER_LENGTH_RE.fullmatch(stripped):
        return True, ""

    match = _PARAMETER_OPERATOR_RE.fullmatch(stripped)
    if match:
        _name, _operator, operand = match.groups()
        return True, operand

    return False, ""


__all__ = [
    "MAX_EXPANSION_RECURSION",
    "_ShellExpansion",
    "_scan_shell_expansions",
    "inspect_shell_expansions",
    "_parameter_expansion_path_probe",
]
