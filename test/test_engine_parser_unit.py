"""Unit tests for canonical engine parser entrypoints."""

import unittest

from lshell.engine import parser as engine_parser


class TestEngineParser(unittest.TestCase):
    """Cover direct parse() behavior for canonical engine parser."""

    def test_parse_accepts_chained_command_with_quotes(self):
        """Parser should accept standard shell-style chains with quoted text."""
        parsed = engine_parser.parse('echo "hello world" && printf ok')
        self.assertFalse(parsed.parse_error)
        self.assertEqual(parsed.sequence, ('echo "hello world"', "&&", "printf ok"))

    def test_parse_rejects_invalid_operator_sequence(self):
        """Malformed top-level operator chains should produce unknown syntax."""
        parsed = engine_parser.parse("echo &&&& ls")
        self.assertTrue(parsed.parse_error)
        self.assertEqual(parsed.sequence, tuple())
        self.assertEqual(parsed.error, "unknown syntax")

    def test_parse_handles_none_input_as_empty_command(self):
        """None input should normalize to a non-error empty parse."""
        parsed = engine_parser.parse(None)
        self.assertFalse(parsed.parse_error)
        self.assertEqual(parsed.sequence, tuple())
        self.assertEqual(parsed.line, "")
        self.assertEqual(parsed.error, "")

    def test_parse_preserves_control_chars_for_downstream_security_checks(self):
        """Parser does not sanitize control chars; authorizer handles that later."""
        parsed = engine_parser.parse("echo\x00ok\x1f\t\n")
        self.assertFalse(parsed.parse_error)
        self.assertEqual(len(parsed.sequence), 1)
        self.assertIn("\x00", parsed.sequence[0])


if __name__ == "__main__":
    unittest.main()
