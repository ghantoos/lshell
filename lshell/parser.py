""" Custom shell command parser with advanced tokenization and error handling """

from typing import Optional
from pyparsing import (
    Word,
    alphanums,
    quoted_string,
    Group,
    ZeroOrMore,
    Literal,
    Optional as PyOptional,
    ParseException,
    one_of,
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
        var_value = Word(alphanums + "_/.-") | quoted_string
        var_assignment = Group(var_name + Literal("=") + var_value)

        # Command substitution patterns
        cmd_subst_dollar = Group(
            Literal("$(") + SkipTo(Literal(")")) + Literal(")")
        ).set_parse_action(
            lambda t: [" ".join(t[0])]
        )  # Preserve as single token

        cmd_subst_backtick = Group(
            Literal("`") + SkipTo(Literal("`")) + Literal("`")
        ).set_parse_action(
            lambda t: [" ".join(t[0])]
        )  # Preserve as single token

        # Variable expansion pattern
        var_expansion = Group(
            Literal("${") + Word(alphanums + "_") + Literal("}")
        ).set_parse_action(
            lambda t: [" ".join(t[0])]
        )  # Preserve as single token

        # Advanced word tokenization - allow all printable chars except operators
        operator_chars = "|&;><"
        # Create allowed chars string: all printables except operators
        word_chars = "".join(c for c in printables if c not in operator_chars)

        # Define custom quoted string that preserves all spaces
        quoted_text = quoted_string.set_parse_action(lambda t: t[0])

        # Define tokens that can start a command (no operators)
        safe_chars = "".join(
            set(word_chars) - set(operator_chars)
        )  # Convert to sets for subtraction
        command_start = (
            cmd_subst_dollar  # Command substitution
            | cmd_subst_backtick  # Command substitution
            | var_expansion  # Variable expansion
            | quoted_text
            | Word("$" + word_chars)  # Environment variables and paths
            | Word(safe_chars)  # Regular words, excluding operators
        )

        # Advanced word tokenization
        advanced_word = (
            cmd_subst_dollar  # Command substitution
            | cmd_subst_backtick  # Command substitution
            | var_expansion  # Variable expansion
            | quoted_text
            | Word("$" + word_chars)  # Environment variables and paths
            | Word(word_chars)  # Regular words
        )

        # Operators with more flexible parsing
        operators = ["&&", "||", "|", ";"]

        # Redirection with enhanced support
        redirection_ops = [">", ">>", "<", "2>", "2>>", ">&"]

        # Background operator
        background_op = ~Literal("&&") + Literal("&")

        # Trailing semicolon
        trailing_semicolon = Literal(";")

        # Command structure with optional variable assignments
        command = Group(
            (
                # Either a command with optional var assignments
                (
                    ZeroOrMore(var_assignment)
                    + command_start
                    + ZeroOrMore(advanced_word)
                    + PyOptional(background_op)
                )
                # Or just variable assignments
                | OneOrMore(var_assignment)
            )
            + PyOptional(one_of(" ".join(redirection_ops)) + advanced_word)
        )

        # Full command sequence with optional background at the end
        command_sequence = Group(
            command
            + ZeroOrMore(one_of(" ".join(operators)) + command)
            + PyOptional(trailing_semicolon)
        )

        return command_sequence

    def _clean_input(self, command: str) -> str:
        """Clean control characters from input"""
        return "".join(char for char in command if ord(char) >= 32 or char in "\n\r\t")

    def parse(self, command: str) -> Optional[ParseResults]:
        """
        Main parsing method with error handling
        """
        try:
            # Clean the input first
            cleaned_command = self._clean_input(command)
            grammar = self._build_grammar()
            parsed_result = grammar.parse_string(cleaned_command, parse_all=True)
            ret = parsed_result
        except ParseException:
            ret = None
        return ret

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
        "tar -czf backup.tar.gz /home/user/data && mv backup.tar.gz /mnt/backup/ "
        '|| echo "Backup failed"',
        'find / -name "*.py" -print | xargs grep "def " > functions.txt; echo "Search complete" &',
        'grep "error" /var/log/syslog | sort -u > errors.txt && echo "Errors found" '
        '|| echo "No errors"',
        'echo "hello" &',
        "ls nRVmmn8RGypVneYIp8HxyVAvaEaD55; echo $?",
    ]

    for cmd in test_commands:
        print(f"Parsing: {cmd}")
        parsed_result = parser.parse(cmd)
        if parsed_result:
            print("Parsed Successfully:")
            print(parsed_result)
            print("Validation:", parser.validate_command(parsed_result))
        print("-" * 40)
