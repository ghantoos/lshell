"""Command parser wrapper built on the canonical engine parser."""

from typing import Optional

from pyparsing import ParseResults

from lshell.engine import parser as engine_parser


class LshellParser:
    """Compatibility parser API backed by the canonical parser."""

    @staticmethod
    def _clean_input(command: str) -> str:
        """Clean control characters from input."""
        return "".join(char for char in command if ord(char) >= 32 or char in "\n\r\t")

    def parse(self, command: str) -> Optional[ParseResults]:
        """Parse command input and return legacy ParseResults tokens."""
        parsed_ast = engine_parser.parse(self._clean_input(command))
        if parsed_ast.parse_error:
            return None
        return ParseResults(list(parsed_ast.sequence))

    @staticmethod
    def validate_command(parsed_command: ParseResults) -> bool:
        """Basic command validation for token count and token length."""
        if not parsed_command:
            return False

        max_tokens = 20
        max_token_length = 255
        flattened = list(parsed_command)

        if len(flattened) > max_tokens:
            return False

        for token in flattened:
            if len(str(token)) > max_token_length:
                return False

        return True
