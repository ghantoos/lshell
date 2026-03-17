"""Unit tests for lshell.parser module execution paths."""

import unittest

from pyparsing import ParseResults

from lshell.parser import LshellParser


class TestLshellParserModule(unittest.TestCase):
    """Cover parser grammar and validation logic outside fuzzing."""

    def setUp(self):
        self.parser = LshellParser()

    def test_parse_accepts_chained_command_with_quotes(self):
        """Parser should accept regular shell-like command chains."""
        parsed = self.parser.parse('echo "hello world" && printf ok')
        self.assertIsNotNone(parsed)
        self.assertTrue(self.parser.validate_command(parsed))

    def test_parse_rejects_invalid_operator_sequence(self):
        """Malformed operator chains should fail parsing cleanly."""
        parsed = self.parser.parse("echo &&&& ls")
        self.assertIsNone(parsed)

    def test_clean_input_removes_control_characters(self):
        """Control characters should be stripped before grammar parsing."""
        cleaned = self.parser._clean_input("echo\x00ok\x1f\t\n")
        self.assertEqual(cleaned, "echook\t\n")

    def test_validate_command_rejects_excessive_token_count(self):
        """Validation should reject token lists larger than maximum."""
        parsed = ParseResults([str(index) for index in range(21)])
        self.assertFalse(self.parser.validate_command(parsed))

    def test_validate_command_rejects_overlong_token(self):
        """Validation should reject tokens longer than configured cap."""
        parsed = ParseResults(["x" * 256])
        self.assertFalse(self.parser.validate_command(parsed))


if __name__ == "__main__":
    unittest.main()
