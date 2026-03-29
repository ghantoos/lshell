"""Canonical AST structures used by the v2 engine."""

from typing import NamedTuple, Tuple


OPERATORS = ("&&", "||", "|", ";", "&")


class ParsedAST(NamedTuple):
    """Result of parse(line) for the canonical engine."""

    line: str
    sequence: Tuple[str, ...]
    parse_error: bool = False
    error: str = ""


class CanonicalCommand(NamedTuple):
    """Canonical command segment extracted from a top-level sequence."""

    index: int
    raw: str
    normalized: str
    tokens: Tuple[str, ...]
    executable: str
    argument: str
    args: Tuple[str, ...]
    assignments: Tuple[Tuple[str, str], ...]
    full_command: str


class CanonicalAST(NamedTuple):
    """Normalized AST used by authorizer and executor."""

    line: str
    sequence: Tuple[str, ...]
    commands: Tuple[CanonicalCommand, ...]
    parse_error: bool = False
    error: str = ""
