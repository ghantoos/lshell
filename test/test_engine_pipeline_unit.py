"""Unit tests for v2 canonical engine parse/normalize/authorize pipeline."""

import os
import tempfile
import unittest

from lshell.engine import authorizer
from lshell.engine import normalizer
from lshell.engine import parser as engine_parser
from lshell.engine import reasons


def _policy(**overrides):
    policy = {
        "allowed": ["echo", "cd", "ls", "sudo"],
        "forbidden": [";"],
        "strict": 0,
        "sudo_commands": ["ls"],
        "allowed_file_extensions": [],
        "path": ["/|", ""],
    }
    policy.update(overrides)
    return policy


class TestEnginePipeline(unittest.TestCase):
    """Core parser/normalizer/authorizer behavior for v2 engine."""

    def test_parse_and_normalize_extracts_assignment_prefix(self):
        """parse+normalize should preserve sequence and assignment prefixes."""
        parsed = engine_parser.parse("A=1 echo ok && ls /tmp")
        self.assertFalse(parsed.parse_error)
        self.assertEqual(parsed.sequence, ("A=1 echo ok", "&&", "ls /tmp"))

        canonical = normalizer.normalize(parsed)
        self.assertFalse(canonical.parse_error)
        first = canonical.commands[0]
        second = canonical.commands[1]

        self.assertEqual(first.assignments, (("A", "1"),))
        self.assertEqual(first.executable, "echo")
        self.assertEqual(first.full_command, "echo ok")
        self.assertEqual(second.executable, "ls")
        self.assertEqual(second.args, ("/tmp",))

    def test_authorizer_accepts_exact_full_command_allow_rule(self):
        """Full-command allow-list entries should still be honored."""
        decision = authorizer.authorize_line(
            "echo only-this",
            _policy(allowed=["echo only-this"], strict=1),
            mode="policy",
            check_current_dir=False,
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason.code, reasons.ALLOWED)

    def test_authorizer_unknown_syntax_when_not_strict(self):
        """Non-strict unknown command should map to unknown_syntax."""
        decision = authorizer.authorize_line(
            "cat /etc/passwd",
            _policy(allowed=["echo"], strict=0),
            mode="policy",
            check_current_dir=False,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason.code, reasons.UNKNOWN_SYNTAX)

    def test_authorizer_forbidden_command_when_strict(self):
        """Strict mode should classify non-allowlisted command as forbidden."""
        decision = authorizer.authorize_line(
            "cat /etc/passwd",
            _policy(allowed=["echo"], strict=1),
            mode="policy",
            check_current_dir=False,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason.code, reasons.FORBIDDEN_COMMAND)

    def test_authorizer_enforces_path_acl(self):
        """Path ACL checks should deny paths outside allowed roots."""
        with tempfile.TemporaryDirectory(prefix="lshell-engine-path-") as tmpdir:
            allowed_dir = os.path.join(tmpdir, "allowed")
            blocked_dir = os.path.join(tmpdir, "blocked")
            os.makedirs(allowed_dir)
            os.makedirs(blocked_dir)

            decision_allowed = authorizer.authorize_line(
                f"ls {allowed_dir}",
                _policy(path=[f"{allowed_dir}|", ""]),
                mode="policy",
                check_current_dir=False,
            )
            decision_blocked = authorizer.authorize_line(
                f"ls {blocked_dir}",
                _policy(path=[f"{allowed_dir}|", ""]),
                mode="policy",
                check_current_dir=False,
            )

            self.assertTrue(decision_allowed.allowed)
            self.assertFalse(decision_blocked.allowed)
            self.assertEqual(decision_blocked.reason.code, reasons.FORBIDDEN_PATH)

    def test_quoted_literal_extraction_is_not_greedy(self):
        """Quoted-literal extraction should keep each quoted segment separate."""
        literals = authorizer._quoted_literals_without_assignment(
            'echo "a" "b" VAR="skip" \'c\''
        )
        self.assertEqual(literals, ["a", "b", "c"])

    def test_authorizer_blocks_quoted_executable_path_at_segment_start(self):
        """Quoted executable paths should still be path-ACL validated."""
        with tempfile.TemporaryDirectory(prefix="lshell-engine-quoted-cmd-") as tmpdir:
            allowed_dir = os.path.join(tmpdir, "allowed")
            blocked_dir = os.path.join(tmpdir, "blocked")
            os.makedirs(allowed_dir)
            os.makedirs(blocked_dir)

            blocked_exec = os.path.join(blocked_dir, "runme")
            with open(blocked_exec, "w", encoding="utf-8") as handle:
                handle.write("#!/bin/sh\nexit 0\n")

            decision = authorizer.authorize_line(
                f'"{blocked_exec}" arg',
                _policy(
                    allowed=[blocked_exec],
                    path=[f"{allowed_dir}|", ""],
                    strict=1,
                ),
                mode="policy",
                check_current_dir=False,
            )

            self.assertFalse(decision.allowed)
            self.assertEqual(decision.reason.code, reasons.FORBIDDEN_PATH)

    def test_authorizer_blocks_nested_double_quote_in_single_quote(self):
        """Nested quotes in single-quoted payloads should still trigger path ACL."""
        with tempfile.TemporaryDirectory(prefix="lshell-engine-nested-quote-") as tmpdir:
            allowed_dir = os.path.join(tmpdir, "allowed")
            blocked_exec = os.path.join(tmpdir, "blocked", "bash")
            os.makedirs(allowed_dir)
            os.makedirs(os.path.dirname(blocked_exec))

            decision = authorizer.authorize_line(
                f'awk \'BEGIN {{system("{blocked_exec}")}}\'',
                _policy(
                    allowed=["awk"],
                    path=[f"{allowed_dir}|", ""],
                    strict=1,
                ),
                mode="policy",
                check_current_dir=False,
            )

            self.assertFalse(decision.allowed)
            self.assertEqual(decision.reason.code, reasons.FORBIDDEN_PATH)


if __name__ == "__main__":
    unittest.main()
