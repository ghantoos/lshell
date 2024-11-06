""" Utils for lshell """

import re
import subprocess
import os
import sys
import random
import string
import shlex
from getpass import getuser
from time import strftime, gmtime

# import lshell specifics
from lshell import variables
from lshell import builtincmd


def usage(exitcode=1):
    """Prints the usage"""
    sys.stderr.write(variables.USAGE)
    sys.exit(exitcode)


def version():
    """Prints the version"""
    sys.stderr.write(f"lshell-{variables.__version__} - Limited Shell\n")
    sys.exit(0)


def random_string(length):
    """generate a random string"""
    randstring = ""
    for char in range(length):
        char = random.choice(string.ascii_letters + string.digits)
        randstring += char

    return randstring


def get_aliases(line, aliases):
    """Replace all configured aliases in the line"""

    for item in aliases.keys():
        escaped_item = re.escape(item)
        reg1 = rf"(^|;|&&|\|\||\|)\s*{escaped_item}([ ;&\|]+|$)(.*)"
        reg2 = rf"(^|;|&&|\|\||\|)\s*{escaped_item}([ ;&\|]+|$)"

        # in case alias begins with the same command
        # (this is until i find a proper regex solution..)
        aliaskey = random_string(10)

        while re.findall(reg1, line):
            (before, after, rest) = re.findall(reg1, line)[0]
            linesave = line

            line = re.sub(reg2, f"{before} {aliaskey}{after}", line, 1)

            # if line does not change after sub, exit loop
            if linesave == line:
                break

        # replace the key by the actual alias
        line = line.replace(aliaskey, aliases[item])

    for char in [";"]:
        # remove all remaining double char
        line = line.replace(f"{char}{char}", f"{char}")
    return line


def split_commands(line):
    """Split the command line into separate commands based on the operators"""
    # in case ';', '|' or '&' are not forbidden, check if in line
    lines = []

    # Variable to track if we're inside quotes
    in_quotes = False

    # Starting position of the command segment
    if line[0] in ["&", "|", ";"]:
        start = 1
    else:
        start = 0

    # Iterate over the command line
    for i in range(1, len(line)):
        # Check for quotes to ignore splitting inside quoted strings
        if line[i] in ['"', "'"] and (i == 0 or line[i - 1] != "\\"):
            in_quotes = not in_quotes
            # Only split if we are not inside quotes and the current character
            # is an unescaped operator
        if line[i] in ["&", "|", ";"] and line[i - 1] != "\\" and not in_quotes:
            if start != i:
                lines.append(line[start:i])
            start = i + 1

    # Append the last segment of the command
    if start != len(line):
        lines.append(line[start:])

    return lines


def split_command_args(line):
    """Split the command line into cmd and args"""
    # Use shlex to split the command into parts
    tokens = shlex.split(line)

    if tokens:
        # The first token is the command
        cmd = tokens[0]
        # The rest are the arguments
        args = " ".join(tokens[1:])
    else:
        # If there are no tokens, return None for both
        cmd, args = "", ""

    return cmd, args


def replace_exit_code(line, retcode):
    """Replace the exit code in the command line. Replaces all occurrences of
    $? with the exit code."""
    if re.search(r"[;&\|]", line):
        p = re.compile(r"(\s|^)(\$\?)([\s|$]?[;&|].*)")
    else:
        p = re.compile(r"(\s|^)(\$\?)(\s|$)")

    line = p.sub(rf" {retcode} \3", line)

    return line


def cmd_parse_execute(command_line, shell_context=None):
    """Parse and execute a shell command line"""
    # Split command line by shell grammar: '&&', '||', and ';;'
    cmd_split = re.split(r"(;|&&|\|\|)", command_line)

    # Initialize return code
    retcode = 0

    # Iterate over commands and operators
    for i in range(0, len(cmd_split), 2):
        command = cmd_split[i].strip()
        operator = cmd_split[i - 1].strip() if i > 0 else None

        # Skip empty commands
        if not command:
            continue

        # Only execute commands based on the previous operator and return code
        if operator == "&&" and retcode != 0:
            continue
        elif operator == "||" and retcode == 0:
            continue

        # Get the executable command
        try:
            executable, argument = re.split(r"\s+", command, maxsplit=1)
        except ValueError:
            executable, argument = command, ""

        # Check if command is in built-ins list or execute it via exec_cmd
        if executable in variables.builtins_list:
            if executable == "help":
                shell_context.do_help(command)
            elif executable == "exit":
                shell_context.do_exit(command)
            elif executable == "history":
                builtincmd.history(shell_context.conf, shell_context.log)
            elif executable == "cd":
                retcode = builtincmd.cd(argument, shell_context.conf)
            else:
                retcode = getattr(builtincmd, executable)(shell_context.conf)
        else:
            if "path_noexec" in shell_context.conf:
                os.environ["LD_PRELOAD"] = shell_context.conf["path_noexec"]
            command = replace_exit_code(command, retcode)
            retcode = exec_cmd(command)

    return retcode


def exec_cmd(cmd):
    """Execute a command exactly as entered, without shell interpretation."""
    try:
        # Split the command to handle it as a list of arguments
        cmd_args = shlex.split(cmd)
        # Execute without shell=True to prevent shell interpretation
        proc = subprocess.Popen(cmd_args)
        proc.communicate()
        retcode = proc.returncode
    except KeyboardInterrupt:
        # Properly handle user interruption (SIGTERM)
        proc.terminate()
        proc.communicate()
        retcode = 130

    return retcode


def parse_ps1(ps1):
    """Parse and format $PS1-style prompt with lshell-compatible values"""
    user = getuser()
    host = os.uname()[1]
    cwd = os.getcwd()
    home = os.path.expanduser("~")
    prompt_symbol = "#" if os.geteuid() == 0 else "$"

    # Define LPS1 replacement mappings
    replacements = {
        r"\u": user,
        r"\h": host.split(".")[0],
        r"\H": host,
        r"\w": cwd.replace(home, "~", 1) if cwd.startswith(home) else cwd,
        r"\W": os.path.basename(cwd),
        r"\$": prompt_symbol,
        r"\\": "\\",
        r"\t": strftime("%H:%M:%S", gmtime()),
        r"\T": strftime("%I:%M:%S", gmtime()),
        r"\A": strftime("%H:%M", gmtime()),
        r"\@": strftime("%I:%M:%S%p", gmtime()),
        r"\d": strftime("%a %b %d", gmtime()),
    }
    # Replace each placeholder with its corresponding value
    for placeholder, value in replacements.items():
        ps1 = ps1.replace(placeholder, value)

    return ps1


def getpromptbase(conf):
    """Get the base prompt structure, using $PS1 or defaulting to config-based prompt"""
    ps1_env = os.getenv("LPS1")
    if ps1_env:
        # Use $LPS1 with placeholders if defined
        promptbase = parse_ps1(ps1_env)
    else:
        # Fallback to configured prompt if no $PS1 is defined
        promptbase = conf.get("prompt", "%u")
        promptbase = promptbase.replace("%u", getuser())
        promptbase = promptbase.replace("%h", os.uname()[1].split(".")[0])

    return promptbase


def updateprompt(path, conf):
    """Set the prompt with updated path and user privilege level, supporting $LPS1 format"""
    promptbase = getpromptbase(conf)
    prompt_symbol = "# " if os.geteuid() == 0 else "$ "

    # Determine dynamic path display if $LPS1 is not defined
    if os.getenv("LPS1"):
        prompt = promptbase
    else:
        if path == conf["home_path"]:
            current_path = "~"
        elif conf.get("prompt_short") == 1:
            current_path = os.path.basename(path)
        elif conf.get("prompt_short") == 2:
            current_path = path
        elif path.startswith(conf["home_path"]):
            current_path = f"~{path[len(conf['home_path']):]}"
        else:
            current_path = path
        prompt = f"{promptbase}:{current_path}{prompt_symbol}"

    return prompt
