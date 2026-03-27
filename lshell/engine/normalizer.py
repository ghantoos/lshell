"""Canonical AST normalizer for v2 engine."""

import re
import shlex

from lshell.engine.ast import OPERATORS, CanonicalAST, CanonicalCommand


_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")


def _is_assignment_word(word):
    return bool(_ASSIGNMENT_RE.match(word))


def _parse_command_words(command_text):
    """Parse one command segment into executable/args/assignment prefixes."""
    try:
        tokens = shlex.split(command_text, posix=True)
    except ValueError:
        return None

    if not tokens:
        return {
            "tokens": tuple(),
            "assignments": tuple(),
            "executable": "",
            "args": tuple(),
            "argument": "",
            "full_command": "",
        }

    assignments = []
    index = 0
    while index < len(tokens) and _is_assignment_word(tokens[index]):
        name, value = tokens[index].split("=", 1)
        assignments.append((name, value))
        index += 1

    if index >= len(tokens):
        return {
            "tokens": tuple(tokens),
            "assignments": tuple(assignments),
            "executable": "",
            "args": tuple(),
            "argument": "",
            "full_command": "",
        }

    executable = tokens[index]
    args = tuple(tokens[index + 1 :])
    return {
        "tokens": tuple(tokens),
        "assignments": tuple(assignments),
        "executable": executable,
        "args": args,
        "argument": " ".join(args),
        "full_command": " ".join((executable,) + args).strip(),
    }


def normalize(parsed_ast):
    """Normalize parse output into canonical command nodes."""
    if parsed_ast.parse_error:
        return CanonicalAST(
            line=parsed_ast.line,
            sequence=parsed_ast.sequence,
            commands=tuple(),
            parse_error=True,
            error=parsed_ast.error,
        )

    commands = []
    for index, item in enumerate(parsed_ast.sequence):
        if item in OPERATORS:
            continue

        normalized = re.sub(r"\)$", "", item)
        normalized = " ".join(normalized.split())
        parsed = _parse_command_words(normalized)
        if parsed is None:
            return CanonicalAST(
                line=parsed_ast.line,
                sequence=parsed_ast.sequence,
                commands=tuple(commands),
                parse_error=True,
                error="unknown syntax",
            )

        commands.append(
            CanonicalCommand(
                index=index,
                raw=item,
                normalized=normalized,
                tokens=parsed["tokens"],
                executable=parsed["executable"],
                argument=parsed["argument"],
                args=parsed["args"],
                assignments=parsed["assignments"],
                full_command=parsed["full_command"],
            )
        )

    return CanonicalAST(
        line=parsed_ast.line,
        sequence=parsed_ast.sequence,
        commands=tuple(commands),
        parse_error=False,
        error="",
    )
