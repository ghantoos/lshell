import json
from pyparsing import (
    Word,
    alphas,
    alphanums,
    quotedString,
    Group,
    ZeroOrMore,
    Literal,
    Optional,
    Suppress,
)

# Define basic tokens
word = Word(alphanums + "/.-_") | quotedString
operator_pipe = Literal("|").setResultsName("pipe")
operator_logical = (Literal("&&") | Literal("||")).setResultsName("logical_operator")
operator_logical = (Literal("&&") | Literal("||")).setResultsName("logical_operator")

redirection = (Literal(">") | Literal(">>") | Literal("<")).setResultsName(
    "redirection_operator"
)  # Redirection
background = (~Literal("&&") + Literal("&")).setResultsName(
    "background"
)  # Background operator

# Define grammar rules
executable = word.setResultsName("executable")  # Command executable
argument = word.setResultsName("argument", listAllMatches=True)  # Command arguments

# Simple command: command + optional arguments + optional redirection + optional background
simple_command = Group(
    executable
    + ZeroOrMore(argument)
    + Optional(redirection + word.setResultsName("redirection_target"))
    + Optional(background)
).setResultsName("simple_command")

# Pipeline: multiple commands connected by "|"
pipeline = Group(
    simple_command.setResultsName("start_command")
    + ZeroOrMore(Group(operator_pipe + simple_command).setResultsName("pipeline_step"))
).setResultsName("pipeline")

# Conditional command: commands connected by "&&" or "||"
conditional_command = Group(
    pipeline.setResultsName("initial_pipeline")
    + ZeroOrMore(Group(operator_logical + pipeline).setResultsName("conditional_step"))
    + Optional(background)
).setResultsName("conditional_command")

# A full command can be simple, pipeline, or conditional
full_command = conditional_command | pipeline | simple_command

# Command sequence: full commands separated by ";" + optional background
command_sequence = Group(
    full_command.setResultsName("first_command")
    + ZeroOrMore(Suppress(";") + full_command.setResultsName("next_command"))
).setResultsName("command_sequence")

# Test parsing a command sequence
if __name__ == "__main__":
    # Example input
    test_input = 'echo "hello world" | ls -la || mkdir /tmp/test; cat /var/log/syslog &'
    # Example inputs
    test_inputs = [
        'grep "error" /var/log/syslog | sort -u > errors.txt && echo "Errors found" || echo "No errors"',
        'find / -name "*.py" -print | xargs grep "def " > functions.txt; echo "Search complete" &',
        'tar -czf backup.tar.gz /home/user/data && mv backup.tar.gz /mnt/backup/ || echo "Backup failed"',
    ]

    for test_input in test_inputs:
        # Parse the input
        parsed = command_sequence.parseString(test_input)
        parsed_dict = parsed.asList()

        # Pretty print the parsed structure
        print(f"Input: {test_input}")
        print("")
        print(json.dumps(parsed_dict[0][0], indent=2))
        print("\n" + "=" * 80 + "\n")
