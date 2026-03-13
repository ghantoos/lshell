#!/usr/bin/env python3
"""Atheris fuzz target for parser/policy security primitives."""

import sys
import tempfile

try:
    import atheris
except ImportError as exc:  # pragma: no cover - optional dependency
    raise SystemExit(
        "atheris is not installed. Install fuzz deps with: pip install -r requirements-fuzz.txt"
    ) from exc

with atheris.instrument_imports():
    from lshell import parser as lshell_parser
    from lshell import policy
    from lshell import sec
    from lshell import utils


class _NullLog:
    """Minimal logger required by security helpers during fuzzing."""

    def critical(self, _message):
        """Discard critical log messages during fuzzing."""
        return None

    def error(self, _message):
        """Discard error log messages during fuzzing."""
        return None

    def warning(self, _message):
        """Discard warning log messages during fuzzing."""
        return None

    def info(self, _message):
        """Discard info log messages during fuzzing."""
        return None


_FUZZ_TMP = tempfile.mkdtemp(prefix="lshell-fuzz-")
_FUZZ_PARSER = lshell_parser.LshellParser()


def _base_conf():
    """Build an isolated, permissive config for parser/policy fuzz entrypoints."""
    return {
        "allowed": [
            "echo",
            "printf",
            "cat",
            "ls",
            "pwd",
            "true",
            "false",
            "cd",
            "sudo",
        ],
        "allowed_file_extensions": [],
        "forbidden": [";", "&", "|", "`", ">", "<", "$(", "${"],
        "sudo_commands": ["ls"],
        "overssh": ["ls", "pwd", "echo"],
        "warning_counter": 64,
        "path": ["/|", ""],
        "home_path": _FUZZ_TMP,
        "promptprint": "",
        "logpath": _NullLog(),
    }


def _fuzz_one_line(line):
    """Exercise parser and security check surfaces on one fuzzed command line."""
    conf = _base_conf()
    runtime_policy = {
        "forbidden": conf["forbidden"],
        "allowed": conf["allowed"],
        "strict": 0,
        "sudo_commands": conf["sudo_commands"],
        "allowed_file_extensions": conf["allowed_file_extensions"],
        "path": conf["path"],
    }
    try:
        parsed = _FUZZ_PARSER.parse(line)
        if parsed is not None:
            _FUZZ_PARSER.validate_command(parsed)

        utils.split_command_sequence(line)
        utils.split_commands(line)
        utils.expand_vars_quoted(line, support_advanced_braced=True)
        utils.expand_vars_quoted(line, support_advanced_braced=False)
        sec._path_tokens_from_line(line)
        sec.check_forbidden_chars(line, conf, strict=0)
        sec.check_path(line, conf, completion=1, strict=0)
        sec.check_secure(line, conf, strict=0)
        sec.check_allowed_file_extensions(line, [".txt", ".log"])
        policy.policy_command_decision(line, runtime_policy)
    except SystemExit:
        # check_secure/check_path may terminate on warning exhaustion; ignore.
        pass


def test_one_input(data):
    """Atheris entrypoint."""
    line = data.decode("latin-1")
    if not line:
        return
    _fuzz_one_line(line[:512])


def main():
    """Run Atheris fuzzing loop."""
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
