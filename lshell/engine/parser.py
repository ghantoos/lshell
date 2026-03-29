"""Canonical parser entrypoint for the v2 engine."""

from lshell.engine.ast import ParsedAST
from lshell import utils


def parse(line):
    """Parse command line into top-level command/operator sequence."""
    if line is None:
        line = ""

    sequence = utils.split_command_sequence(line)
    if sequence is None:
        return ParsedAST(line=line, sequence=tuple(), parse_error=True, error="unknown syntax")

    return ParsedAST(line=line, sequence=tuple(sequence), parse_error=False, error="")
