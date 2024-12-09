""" Custom shell command parser with advanced tokenization and error handling """

from typing import Optional
from pyparsing import (
    Word,
    alphanums,
    quotedString,
    Group,
    ZeroOrMore,
    Literal,
    Optional as PyOptional,
    ParseException,
    oneOf,
    ParseResults,
    alphas,
    printables,
    OneOrMore,
    SkipTo,
)


class LshellParser:
    """Custom shell command parser"""

    def __init__(self):
        """Initialize the parser with custom settings"""
        # Improved tokenization
        self._escape_char = "\\"
        self._quote_chars = ['"', "'"]

    def _handle_escaped_chars(self, token: str) -> str:
        """
        Handle escaped characters in tokens
        Supports escaping of quote characters and special symbols
        """
        if not token:
            return token

        cleaned_token = []
        is_escaped = False

        for char in token:
            if is_escaped:
                # List of escapable characters
                escaped_map = {
                    "n": "\n",
                    "t": "\t",
                    "r": "\r",
                    '"': '"',
                    "'": "'",
                    "\\": "\\",
                }
                cleaned_token.append(escaped_map.get(char, char))
                is_escaped = False
            elif char == self._escape_char:
                is_escaped = True
            else:
                cleaned_token.append(char)

        return "".join(cleaned_token)

    def _advanced_quote_handler(self, token: str) -> str:
        """
        Advanced quote handling with nested quote support
        """
        if not token:
            return token

        # If it's a quoted string
        if token[0] in self._quote_chars and token[0] == token[-1]:
            # Keep the quotes, but handle escaped characters inside
            quoted_content = token[1:-1]
            unescaped_content = self._handle_escaped_chars(quoted_content)
            # Return with original quotes
            return token[0] + unescaped_content + token[-1]

        # For non-quoted strings, just handle escaped chars
        return self._handle_escaped_chars(token)

    def _build_grammar(self):
        """
        Construct a more robust parsing grammar with background support
        """
        # Variable assignment pattern
        var_name = Word(alphas + "_", alphanums + "_")
        var_value = Word(alphanums + "_/.-") | quotedString
        var_assignment = Group(var_name + Literal("=") + var_value)

        # Command substitution patterns
        cmd_subst_dollar = Group(
            Literal("$(") + SkipTo(Literal(")")) + Literal(")")
        ).setParseAction(
            lambda t: [" ".join(t[0])]
        )  # Preserve as single token

        cmd_subst_backtick = Group(
            Literal("`") + SkipTo(Literal("`")) + Literal("`")
        ).setParseAction(
            lambda t: [" ".join(t[0])]
        )  # Preserve as single token

        # Variable expansion pattern
        var_expansion = Group(
            Literal("${") + Word(alphanums + "_") + Literal("}")
        ).setParseAction(
            lambda t: [" ".join(t[0])]
        )  # Preserve as single token

        # Advanced word tokenization
        advanced_word = (
            cmd_subst_dollar
            | cmd_subst_backtick
            | var_expansion
            | Word(
                "$" + alphanums + "_" + "/.-?~" + self._escape_char
            )  # Environment variables and paths
            | Word(alphanums + "/.-_=")
            | quotedString.setParseAction(lambda t: self._advanced_quote_handler(t[0]))
        )

        # Operators with more flexible parsing
        operators = oneOf(["|", "&&", "||", ";"])

        # Redirection with enhanced support
        redirection_ops = oneOf([">", ">>", "<", "2>", "2>>", ">&"])

        # Background operator
        background_op = PyOptional(Literal("&"))

        # Trailing semicolon
        trailing_semicolon = PyOptional(Literal(";"))

        # Command structure with optional variable assignments
        command = Group(
            (
                # Either a command with optional var assignments
                (ZeroOrMore(var_assignment) + advanced_word + ZeroOrMore(advanced_word))
                # Or just variable assignments
                | OneOrMore(var_assignment)
            )
            + PyOptional(redirection_ops + advanced_word)  # Optional redirection
        )

        # Full command sequence with optional background at the end
        command_sequence = Group(
            command
            + ZeroOrMore(operators + command)
            + background_op
            + trailing_semicolon
        )

        return command_sequence

    def parse(self, command: str) -> Optional[ParseResults]:
        """
        Main parsing method with error handling
        """
        try:
            grammar = self._build_grammar()
            parsed_result = grammar.parseString(command, parseAll=True)
            return parsed_result
        except ParseException as error:
            print(f"Parsing Error: {error}")
            print(f"Error at line {error.lineno}, column {error.col}")
            return None

    def validate_command(self, parsed_command: ParseResults) -> bool:
        """
        Basic command validation
        Can be extended with more sophisticated checks
        """
        if not parsed_command:
            return False

        # Example validation rules
        max_tokens = 20
        max_token_length = 255

        flattened = list(parsed_command)

        # Check total number of tokens
        if len(flattened) > max_tokens:
            return False

        # Check individual token lengths
        for token in flattened:
            if len(str(token)) > max_token_length:
                return False

        return True


# Testing
if __name__ == "__main__":
    parser = LshellParser()

    test_commands = [
        'echo "hello world"',
        'grep "error" /var/log/syslog | sort -u > errors.txt',
        'find / -name "*.py" -print | xargs grep "def \\"test\\""',
        r'echo "escaped \"quote\""',
        'tar -czf backup.tar.gz /home/user/data && mv backup.tar.gz /mnt/backup/ || echo "Backup failed"',
        'find / -name "*.py" -print | xargs grep "def " > functions.txt; echo "Search complete" &',
        'grep "error" /var/log/syslog | sort -u > errors.txt && echo "Errors found" || echo "No errors"',
        'echo "hello" &',
        "ls nRVmmn8RGypVneYIp8HxyVAvaEaD55; echo $?",
    ]

    for cmd in test_commands:
        print(f"Parsing: {cmd}")
        result = parser.parse(cmd)
        if result:
            print("Parsed Successfully:")
            print(result)
            print("Validation:", parser.validate_command(result))
        print("-" * 40)
