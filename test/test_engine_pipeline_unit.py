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

    def test_authorizer_parses_command_substitution_with_quoted_parenthesis(self):
        """Quoted ')' inside $() should not truncate nested command parsing."""
        decision = authorizer.authorize_line(
            "echo $(printf ')')",
            _policy(allowed=["echo", "printf"], forbidden=[], strict=0),
            mode="policy",
            check_current_dir=False,
        )
        self.assertTrue(decision.allowed)

    def test_authorizer_parses_nested_command_substitutions(self):
        """Nested $() expansions should recurse through inner allow-list checks."""
        decision = authorizer.authorize_line(
            "echo $(echo $(echo ok))",
            _policy(allowed=["echo"], forbidden=[], strict=0),
            mode="policy",
            check_current_dir=False,
        )
        self.assertTrue(decision.allowed)

    def test_runtime_authorizer_allows_substitutions_in_bash_compat(self):
        """bash_compat runtime mode should allow both substitution families."""
        policy = _policy(
            allowed=["echo", "printf", "cat", "tee"],
            forbidden=[],
            strict=0,
            runtime_executor="bash_compat",
        )
        command_cases = [
            "echo $(printf ok)",
            "echo `printf ok`",
            "cat <(printf ok)",
            "printf ok | tee >(cat)",
        ]
        for line in command_cases:
            with self.subTest(line=line):
                decision = authorizer.authorize_line(
                    line,
                    policy,
                    mode="runtime",
                    check_current_dir=False,
                )
                self.assertTrue(decision.allowed)

    def test_runtime_authorizer_keeps_nested_allowlist_checks_in_command_substitution(
        self,
    ):
        """Enabled substitution must still recurse into nested allow-list checks."""
        decision = authorizer.authorize_line(
            "echo $(id)",
            _policy(
                allowed=["echo"],
                forbidden=[],
                strict=1,
                runtime_executor="bash_compat",
            ),
            mode="runtime",
            check_current_dir=False,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason.code, reasons.FORBIDDEN_COMMAND)

    def test_authorizer_enforces_overssh_allowlist_inside_nested_expansions(self):
        """SSH-mode nested expansions must use overssh allow-list decisions."""
        decision = authorizer.authorize_line(
            "echo ${LSHELL_WORD:-$(id)}",
            _policy(
                allowed=["echo", "id"],
                overssh=["echo"],
                forbidden=[],
                strict=1,
            ),
            mode="policy",
            ssh=True,
            check_current_dir=False,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason.code, reasons.FORBIDDEN_COMMAND)

    def test_authorizer_handles_parameter_expansion_with_logical_operators(self):
        """${...} operands containing ||/&& should parse as a single expansion body."""
        decision = authorizer.authorize_line(
            "echo ${LSHELL_WORD:-a||b&&c}",
            _policy(allowed=["echo"], forbidden=[], strict=0),
            mode="policy",
            check_current_dir=False,
        )
        self.assertTrue(decision.allowed)

    def test_authorizer_rejects_parameter_expansion_with_nested_backtick_substitution(
        self,
    ):
        """Nested backticks in ${...} should enforce inner allow-list checks."""
        decision = authorizer.authorize_line(
            "echo ${LSHELL_WORD:-`id`}",
            _policy(allowed=["echo"], forbidden=[], strict=1),
            mode="policy",
            check_current_dir=False,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason.code, reasons.FORBIDDEN_COMMAND)

    def test_authorizer_allows_parameter_expansion_with_nested_backtick_when_allowlisted(
        self,
    ):
        """Allow nested backticks in ${...} only when inner command is allowlisted."""
        decision = authorizer.authorize_line(
            "echo ${LSHELL_WORD:-`printf ok`}",
            _policy(allowed=["echo", "printf"], forbidden=[], strict=1),
            mode="policy",
            check_current_dir=False,
        )
        self.assertTrue(decision.allowed)

    def test_authorizer_fails_closed_on_malformed_nested_parameter_substitution(
        self,
    ):
        """Malformed nested expansion markers in ${...} should be denied."""
        decision = authorizer.authorize_line(
            "echo ${LSHELL_WORD:-$(printf ok}",
            _policy(allowed=["echo", "printf"], forbidden=[], strict=1),
            mode="policy",
            check_current_dir=False,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason.code, reasons.UNKNOWN_SYNTAX)

    def test_authorizer_rejects_process_substitution_with_disallowed_inner_command(
        self,
    ):
        """Process substitutions must recurse into nested allow-list checks."""
        decision = authorizer.authorize_line(
            "echo <(id)",
            _policy(allowed=["echo"], forbidden=[], strict=1),
            mode="policy",
            check_current_dir=False,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason.code, reasons.FORBIDDEN_COMMAND)

    def test_authorizer_allows_process_substitution_when_inner_command_allowlisted(
        self,
    ):
        """Allow process substitution only when the nested command is allowlisted."""
        decision = authorizer.authorize_line(
            "echo <(printf ok)",
            _policy(allowed=["echo", "printf"], forbidden=[], strict=1),
            mode="policy",
            check_current_dir=False,
        )
        self.assertTrue(decision.allowed)

    def test_authorizer_fails_closed_on_malformed_process_substitution(self):
        """Unbalanced process substitutions should be denied."""
        decision = authorizer.authorize_line(
            "echo <(printf ok",
            _policy(allowed=["echo", "printf"], forbidden=[], strict=1),
            mode="policy",
            check_current_dir=False,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason.code, reasons.UNKNOWN_SYNTAX)

    def test_authorizer_rejects_disallowed_command_in_arithmetic_expansion(self):
        """$((...)) must recurse into nested substitutions for allow-list checks."""
        decision = authorizer.authorize_line(
            "echo $(( $(id) + 1 ))",
            _policy(allowed=["echo"], forbidden=[], strict=1),
            mode="policy",
            check_current_dir=False,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason.code, reasons.FORBIDDEN_COMMAND)

    def test_authorizer_allows_arithmetic_expansion_when_nested_command_allowlisted(
        self,
    ):
        """Allow arithmetic nested substitution only when inner command is allowed."""
        decision = authorizer.authorize_line(
            "echo $(( $(printf 1) + 1 ))",
            _policy(allowed=["echo", "printf"], forbidden=[], strict=1),
            mode="policy",
            check_current_dir=False,
        )
        self.assertTrue(decision.allowed)

    def test_authorizer_rejects_unsupported_here_string_syntax(self):
        """Fail closed on unsupported here-string syntax."""
        decision = authorizer.authorize_line(
            "echo <<< ok",
            _policy(allowed=["echo"], forbidden=[], strict=0),
            mode="policy",
            check_current_dir=False,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason.code, reasons.UNKNOWN_SYNTAX)

    def test_authorizer_rejects_unsupported_here_doc_syntax(self):
        """Fail closed on unsupported here-doc syntax."""
        decision = authorizer.authorize_line(
            "echo <<EOF",
            _policy(allowed=["echo"], forbidden=[], strict=0),
            mode="policy",
            check_current_dir=False,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason.code, reasons.UNKNOWN_SYNTAX)

    def test_authorizer_rejects_unsupported_ansi_c_quoting(self):
        """Fail closed on unsupported $'...' quoting forms."""
        decision = authorizer.authorize_line(
            "echo $'ok'",
            _policy(allowed=["echo"], forbidden=[], strict=0),
            mode="policy",
            check_current_dir=False,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason.code, reasons.UNKNOWN_SYNTAX)

    def test_authorizer_rejects_unsupported_locale_quoting(self):
        """Fail closed on unsupported $\"...\" locale-translation quoting."""
        decision = authorizer.authorize_line(
            'echo $"ok"',
            _policy(allowed=["echo"], forbidden=[], strict=0),
            mode="policy",
            check_current_dir=False,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason.code, reasons.UNKNOWN_SYNTAX)

    def test_authorizer_rejects_unsupported_parameter_indirection(self):
        """Fail closed on ${!var} forms that are not safely inspectable."""
        decision = authorizer.authorize_line(
            "echo ${!LSHELL_PTR}",
            _policy(allowed=["echo"], forbidden=[], strict=0),
            mode="policy",
            check_current_dir=False,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason.code, reasons.UNKNOWN_SYNTAX)

    def test_authorizer_rejects_unsupported_parameter_slicing(self):
        """Fail closed on unsupported ${var:offset} slicing forms."""
        decision = authorizer.authorize_line(
            "echo ${LSHELL_WORD:1}",
            _policy(allowed=["echo"], forbidden=[], strict=0),
            mode="policy",
            check_current_dir=False,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason.code, reasons.UNKNOWN_SYNTAX)

    def test_authorizer_rejects_unsupported_parameter_pattern_substitution(self):
        """Fail closed on unsupported ${var/pat/repl} parameter substitutions."""
        decision = authorizer.authorize_line(
            "echo ${LSHELL_WORD/foo/bar}",
            _policy(allowed=["echo"], forbidden=[], strict=0),
            mode="policy",
            check_current_dir=False,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason.code, reasons.UNKNOWN_SYNTAX)

    def test_authorizer_enforces_path_acl_on_each_brace_expansion_branch(self):
        """Brace-expanded path operands must validate every expanded branch."""
        with tempfile.TemporaryDirectory(prefix="lshell-engine-brace-path-") as tmpdir:
            allowed_dir = os.path.join(tmpdir, "allowed")
            blocked_dir = os.path.join(tmpdir, "blocked")
            os.makedirs(allowed_dir)
            os.makedirs(blocked_dir)

            decision = authorizer.authorize_line(
                f"ls {tmpdir}/{{allowed,blocked}}",
                _policy(
                    allowed=["ls"],
                    path=[f"{tmpdir}|", f"{blocked_dir}|"],
                    strict=1,
                ),
                mode="policy",
                check_current_dir=False,
            )
            self.assertFalse(decision.allowed)
            self.assertEqual(decision.reason.code, reasons.FORBIDDEN_PATH)

    def test_authorizer_rejects_extglob_path_operand_fail_closed(self):
        """Unsupported extglob path operands should be denied by path checks."""
        with tempfile.TemporaryDirectory(prefix="lshell-engine-extglob-path-") as tmpdir:
            os.makedirs(os.path.join(tmpdir, "allowed"))

            decision = authorizer.authorize_line(
                f"ls {tmpdir}/@(allowed)",
                _policy(
                    allowed=["ls"],
                    path=[f"{tmpdir}|", ""],
                    strict=1,
                ),
                mode="policy",
                check_current_dir=False,
            )
            self.assertFalse(decision.allowed)
            self.assertEqual(decision.reason.code, reasons.FORBIDDEN_PATH)

    def test_authorizer_ignores_single_quoted_command_substitution_literal(self):
        """Single-quoted $() text should remain literal and not recurse."""
        decision = authorizer.authorize_line(
            "echo '$(cat /etc/passwd)'",
            _policy(allowed=["echo"], forbidden=[], strict=0),
            mode="policy",
            check_current_dir=False,
        )
        self.assertTrue(decision.allowed)

    def test_authorizer_enforces_command_substitution_inside_double_quotes(self):
        """Double-quoted $() should still recurse and enforce allow-list."""
        decision = authorizer.authorize_line(
            'echo "$(cat /etc/passwd)"',
            _policy(allowed=["echo"], forbidden=[], strict=0),
            mode="policy",
            check_current_dir=False,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason.code, reasons.UNKNOWN_SYNTAX)

    def test_authorizer_ignores_escaped_command_substitution_marker(self):
        """Escaped '$(' should remain literal and not be parsed as substitution."""
        decision = authorizer.authorize_line(
            r"echo \$(cat /etc/passwd)",
            _policy(allowed=["echo"], forbidden=[], strict=0),
            mode="policy",
            check_current_dir=False,
        )
        self.assertTrue(decision.allowed)


if __name__ == "__main__":
    unittest.main()
