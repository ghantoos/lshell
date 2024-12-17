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
import signal

# import lshell specifics
from lshell import variables
from lshell import builtincmd
from lshell import sec
from lshell.parser import LshellParser


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

            line = re.sub(reg2, f"{before} {aliaskey}{after}", line, count=1)

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
        pattern = re.compile(r"(\s|^)(\$\?)([\s|$]?[;&|].*)")
    else:
        pattern = re.compile(r"(\s|^)(\$\?)(\s|$)")

    line = pattern.sub(rf" {retcode} \3", line)

    return line


def expand_env_vars(arg):
    """
    Expand environment variables, replacing non-existing ones with empty string.
    Uses os.path.expandvars but handles non-existing variables.
    """
    # First find all environment variables in the string
    try:
        env_vars = re.findall(r"\$\{([^}]*)\}|\$([a-zA-Z0-9_]+)", arg)
    except re.error:
        # If there's an error in the regex, return the original string
        return arg

    # For each non-existing var, temporarily set it to empty string
    temp_vars = {}
    for var_braces, var_plain in env_vars:
        var_name = var_braces or var_plain
        if var_name not in os.environ:
            temp_vars[var_name] = ""
            os.environ[var_name] = ""

    try:
        # Use standard os.path.expandvars
        result = os.path.expandvars(arg)
    finally:
        # Clean up temporary environment variables
        for var_name in temp_vars:
            del os.environ[var_name]

    return result


def expand_command_group(command_group, retcode):
    """
    Expand environment variables in a command group.
    Returns a tuple of (executable, args, full_command)
    """
    # Handle variable assignment case
    if len(command_group) == 1:
        # Since command_group is [['a', '=', '1']], get the inner list
        inner_group = command_group[0]
        if len(inner_group) == 3 and inner_group[1] == "=":
            # This is a variable assignment
            var_name = inner_group[0]
            var_value = inner_group[2]
            # Return format that indicates this is a variable assignment
            return (
                "lshell-internal-env",
                f"{var_name}={var_value}",
                f"lshell-internal-env {var_name}={var_value}",
            )

    # Replace $? with the exit code first
    for i, arg in enumerate(command_group):
        if arg == "$?":
            command_group[i] = str(retcode)

    # Then expand any other environment variables
    expanded_group = []
    for arg in command_group:
        expanded_arg = expand_env_vars(arg)  # os.path.expandvars(arg)
        expanded_group.append(expanded_arg)

    executable = expanded_group[0]
    args = expanded_group[1:] if len(expanded_group) > 1 else []

    # Special handling for export command and '=' in arguments
    if executable == "export":
        # Join the arguments, removing spaces around '='
        argument = "".join(args)
        full_command = f"{executable} {''.join(args)}"
    else:
        argument = " ".join(args)
        full_command = " ".join(expanded_group)

    return executable, argument, full_command


def handle_builtin_command(full_command, executable, argument, shell_context):
    """
    Handle built-in commands like cd, lpath, lsudo, etc.
    Returns tuple of (retcode, conf)
    """

    retcode = 0
    conf = shell_context.conf

    if executable == "help":
        shell_context.do_help(executable)
    elif executable == "exit":
        shell_context.do_exit(full_command)
    elif executable == "history":
        builtincmd.cmd_history(shell_context.conf, shell_context.log)
    elif executable == "cd":
        retcode, shell_context.conf = builtincmd.cmd_cd(argument, shell_context.conf)
    elif executable == "lpath":
        retcode = builtincmd.cmd_lpath(conf)
    elif executable == "lsudo":
        retcode = builtincmd.cmd_lsudo(conf)
    elif executable == "history":
        retcode = builtincmd.cmd_history(conf, shell_context.log)
    elif executable == "export":
        retcode, var = builtincmd.cmd_export(full_command)
        if retcode == 1:
            shell_context.log.critical(f"** forbidden environment variable '{var}'")
    elif executable == "source":
        retcode = builtincmd.cmd_source(argument)
    elif executable == "fg":
        retcode = builtincmd.cmd_bg_fg(executable, argument)
    elif executable == "bg":
        retcode = builtincmd.cmd_bg_fg(executable, argument)
    elif executable == "jobs":
        retcode = builtincmd.cmd_jobs()

    return retcode, conf


def cmd_parse_execute(command_line, shell_context=None):
    """Parse and execute a shell command line"""
    parser = LshellParser()
    parsed = parser.parse(command_line)

    if parsed is None:
        # If parsing fails, return error code
        shell_context.log.warn(f'INFO: unknown syntax -> "{command_line}"')
        sys.stderr.write(f"*** unknown syntax: {command_line}\n")
        return 1

    # Initialize return code
    retcode = 0

    # Convert parsed result to command sequence
    command_sequence = parsed[0]  # First item contains the full sequence

    # Check for forbidden characters in the command line
    ret_forbidden_chars, shell_context.conf = sec.check_forbidden_chars(
        command_line, shell_context.conf, strict=shell_context.conf["strict"]
    )
    if ret_forbidden_chars == 1:
        # see http://tldp.org/LDP/abs/html/exitcodes.html
        retcode = 126
        return retcode

    # Iterate through the command sequence
    i = 0
    while i < len(command_sequence):
        # Get the current item
        current_item = command_sequence[i]

        # Skip if it's an operator
        if isinstance(current_item, str) and current_item in [
            "&&",
            "||",
            "|",
            "&",
            ";",
        ]:
            i += 1
            continue

        # Get the previous operator (if any)
        prev_operator = (
            command_sequence[i - 1]
            if i > 0 and isinstance(command_sequence[i - 1], str)
            else None
        )

        # Skip empty commands
        if not current_item:
            i += 1
            continue

        # Handle logical operators
        if prev_operator == "&&" and retcode != 0:
            # Previous command failed, skip this one
            i += 1
            continue
        elif prev_operator == "||" and retcode == 0:
            # Previous command succeeded, skip this one
            i += 1
            continue

        executable, argument, full_command = expand_command_group(current_item, retcode)

        # Handle variable assignment
        if executable == "lshell-internal-env":
            var_name, var_value = argument.split("=")
            os.environ[var_name] = var_value
            retcode = 0
            i += 1
            continue

        # check that commands/chars present in line are allowed/secure
        ret_check_secure, shell_context.conf = sec.check_secure(
            full_command, shell_context.conf, strict=shell_context.conf["strict"]
        )
        if ret_check_secure == 1:
            # see http://tldp.org/LDP/abs/html/exitcodes.html
            retcode = 126
            return retcode

        # check that path present in line are allowed/secure
        ret_check_path, shell_context.conf = sec.check_path(
            full_command, shell_context.conf, strict=shell_context.conf["strict"]
        )
        if ret_check_path == 1:
            # see http://tldp.org/LDP/abs/html/exitcodes.html
            retcode = 126
            # in case request was sent by WinSCP, return error code has to be
            # sent via a specific echo command
            if shell_context.conf["winscp"] and re.search(
                "WinSCP: this is end-of-file", command_line
            ):
                exec_cmd(f'echo "WinSCP: this is end-of-file: {retcode}"')
            return retcode

        # Extract command and arguments
        command_group = current_item
        executable = os.path.expandvars(command_group[0])
        # Expand vars in all arguments
        args = (
            [os.path.expandvars(arg) for arg in command_group[1:]]
            if len(command_group) > 1
            else []
        )
        argument = " ".join(args)

        # Execute command
        if executable in builtincmd.builtins_list:
            retcode, shell_context.conf = handle_builtin_command(
                full_command, executable, argument, shell_context
            )
        elif (
            executable in shell_context.conf["allowed"]
            or full_command in shell_context.conf["allowed"]
        ):
            if "path_noexec" in shell_context.conf:
                os.environ["LD_PRELOAD"] = shell_context.conf["path_noexec"]
            retcode = exec_cmd(full_command)
        else:
            shell_context.log.warn(f'INFO: unknown syntax -> "{full_command}"')
            sys.stderr.write(f"*** unknown syntax: {full_command}\n")

        i += 1

    return retcode


def exec_cmd(cmd):
    """Execute a command exactly as entered, with support for backgrounding via Ctrl+Z."""

    class CtrlZException(Exception):
        """Custom exception to handle Ctrl+Z (SIGTSTP)."""

        pass

    def handle_sigtstp(signum, frame):
        """Handle SIGTSTP (Ctrl+Z) by sending the process to the background."""
        if proc and proc.poll() is None:  # Ensure process is running
            proc.send_signal(signal.SIGSTOP)  # Stop the process
            builtincmd.BACKGROUND_JOBS.append(proc)  # Add process to background jobs
            job_id = len(builtincmd.BACKGROUND_JOBS)
            sys.stdout.write(f"\n[{job_id}]+  Stopped        {cmd}\n")
            sys.stdout.flush()
            raise CtrlZException()  # Raise custom exception for SIGTSTP handling

    def handle_sigcont(signum, frame):
        """Handle SIGCONT to resume a stopped job in the foreground."""
        if proc and proc.poll() is None:
            proc.send_signal(signal.SIGCONT)

    # Check if the command is to be run in the background
    background = cmd.strip().endswith("&")
    if background:
        # Remove '&' and strip any extra spaces
        cmd = cmd[:-1].strip()

    try:
        # Register SIGTSTP (Ctrl+Z) and SIGCONT (resume) signal handlers
        signal.signal(signal.SIGTSTP, handle_sigtstp)
        signal.signal(signal.SIGCONT, handle_sigcont)
        cmd_args = shlex.split(cmd)
        if background:
            with open(os.devnull, "r") as devnull_in:
                proc = subprocess.Popen(
                    cmd_args,
                    stdin=devnull_in,  # Redirect input to /dev/null
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                    preexec_fn=os.setsid,
                )
            # add to background jobs and return
            builtincmd.BACKGROUND_JOBS.append(proc)
            job_id = len(builtincmd.BACKGROUND_JOBS)
            print(f"[{job_id}] {cmd} (pid: {proc.pid})")
            retcode = 0
        else:
            proc = subprocess.Popen(cmd_args, preexec_fn=os.setsid)
            proc.communicate()
            retcode = proc.returncode if proc.returncode is not None else 0

    except FileNotFoundError:
        sys.stderr.write(
            f"Command '{cmd_args[0]}' not found in $PATH or not installed on the system.\n"
        )
        retcode = 127
    except CtrlZException:  # Handle Ctrl+Z
        retcode = 0
    except KeyboardInterrupt:  # Handle Ctrl+C
        if proc and proc.poll() is None:
            os.killpg(os.getpgid(proc.pid), signal.SIGINT)
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
