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
    """Split command line at top-level operators, preserving quoting/substitutions."""
    tokenized = split_command_sequence(line)
    if tokenized is None:
        return [line]

    operators = {"&&", "||", "|", ";", "&"}
    return [item for item in tokenized if item not in operators and item.strip()]


def split_command_sequence(line):
    """Return a tokenized top-level command sequence [cmd, op, cmd, ...]."""
    if not line or not line.strip():
        return []

    tokens = []
    current = []
    in_single = False
    in_double = False
    in_backtick = False
    escaped = False
    cmd_subst_depth = 0
    var_brace_depth = 0
    i = 0

    def flush_current():
        command = "".join(current).strip()
        if command:
            tokens.append(command)
        current.clear()

    while i < len(line):
        char = line[i]
        next_char = line[i + 1] if i + 1 < len(line) else ""

        if escaped:
            current.append(char)
            escaped = False
            i += 1
            continue

        if char == "\\" and not in_single:
            current.append(char)
            escaped = True
            i += 1
            continue

        if not in_double and not in_backtick and char == "'":
            in_single = not in_single
            current.append(char)
            i += 1
            continue

        if not in_single and not in_backtick and char == '"':
            in_double = not in_double
            current.append(char)
            i += 1
            continue

        if not in_single and char == "`":
            in_backtick = not in_backtick
            current.append(char)
            i += 1
            continue

        if not in_single and not in_backtick and char == "$" and next_char == "(":
            cmd_subst_depth += 1
            current.append(char)
            current.append(next_char)
            i += 2
            continue

        if not in_single and not in_backtick and char == "$" and next_char == "{":
            var_brace_depth += 1
            current.append(char)
            current.append(next_char)
            i += 2
            continue

        if cmd_subst_depth > 0 and not in_single and not in_backtick and char == ")":
            cmd_subst_depth -= 1
            current.append(char)
            i += 1
            continue

        if var_brace_depth > 0 and not in_single and not in_backtick and char == "}":
            var_brace_depth -= 1
            current.append(char)
            i += 1
            continue

        is_top_level = (
            not in_single
            and not in_double
            and not in_backtick
            and cmd_subst_depth == 0
            and var_brace_depth == 0
        )

        if is_top_level:
            op = None
            if char == "&" and next_char == "&":
                op = "&&"
            elif char == "|" and next_char == "|":
                op = "||"
            elif char == ";":
                op = ";"
            elif char == "|":
                op = "|"
            elif char == "&":
                prev_non_space = "".join(current).rstrip()
                prev_char = prev_non_space[-1] if prev_non_space else ""
                if prev_char not in [">", "<"]:
                    op = "&"

            if op:
                flush_current()
                tokens.append(op)
                i += len(op)
                continue

        current.append(char)
        i += 1

    if in_single or in_double or in_backtick or cmd_subst_depth or var_brace_depth:
        return None

    flush_current()

    if not tokens:
        return []
    operators = {"&&", "||", "|", ";", "&"}
    for idx in range(1, len(tokens)):
        if tokens[idx - 1] in operators and tokens[idx] in operators:
            return None
    if tokens[0] in {"&&", "||", "|", ";", "&"}:
        return None
    if tokens[-1] in {"&&", "||", "|"}:
        return None

    return tokens


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


_ENV_VAR_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _consume_env_var(text, start):
    """Parse a variable reference at text[start] where text[start] == '$'."""
    length = len(text)
    if start + 1 >= length:
        return None, 1

    next_char = text[start + 1]
    if next_char == "{":
        closing = text.find("}", start + 2)
        if closing == -1:
            return None, 1
        name = text[start + 2 : closing]
        if _ENV_VAR_NAME_RE.fullmatch(name):
            return os.environ.get(name, ""), (closing - start + 1)
        return None, 1

    match = _ENV_VAR_NAME_RE.match(text, start + 1)
    if match:
        name = match.group(0)
        return os.environ.get(name, ""), (match.end() - start)

    return None, 1


def expand_vars_quoted(line):
    """Expand environment variables while preserving single-quoted literals."""
    if not line:
        return line

    expanded = []
    in_single = False
    in_double = False
    escaped = False
    i = 0

    while i < len(line):
        char = line[i]

        if escaped:
            expanded.append(char)
            escaped = False
            i += 1
            continue

        if char == "\\" and not in_single:
            expanded.append(char)
            escaped = True
            i += 1
            continue

        if char == "'" and not in_double:
            in_single = not in_single
            expanded.append(char)
            i += 1
            continue

        if char == '"' and not in_single:
            in_double = not in_double
            expanded.append(char)
            i += 1
            continue

        if char == "$" and not in_single:
            replacement, consumed = _consume_env_var(line, i)
            if replacement is not None:
                expanded.append(replacement)
                i += consumed
                continue

        expanded.append(char)
        i += 1

    return "".join(expanded)


def _is_assignment_word(word):
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*=.*$", word))


def _parse_command(command):
    """Parse a command into executable/argument while honoring shell quoting."""
    try:
        split = shlex.split(command, posix=True)
    except ValueError:
        return None, None, None, None

    if not split:
        return "", "", [], []

    assignments = []
    position = 0
    while position < len(split) and _is_assignment_word(split[position]):
        name, value = split[position].split("=", 1)
        assignments.append((name, value))
        position += 1

    if position >= len(split):
        return "", "", split, assignments

    executable = split[position]
    args = split[position + 1 :]
    argument = " ".join(args)
    return executable, argument, split, assignments


def _is_allowed_command(executable, command, conf):
    """Check command authorization from lshell config."""
    return executable in conf["allowed"] or command in conf["allowed"]


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
        retcode = builtincmd.cmd_history(shell_context.conf, shell_context.log)
    elif executable == "cd":
        retcode, shell_context.conf = builtincmd.cmd_cd(argument, shell_context.conf)
    elif executable == "lpath":
        retcode = builtincmd.cmd_lpath(conf)
    elif executable == "lsudo":
        retcode = builtincmd.cmd_lsudo(conf)
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
    command_sequence = split_command_sequence(command_line)
    if command_sequence is None:
        shell_context.log.warn(f'INFO: unknown syntax -> "{command_line}"')
        sys.stderr.write(f"*** unknown syntax: {command_line}\n")
        return 1

    # Initialize return code
    retcode = 0

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
            # Previous command failed, skip this branch (including pipeline/background).
            j = i
            while (
                j + 2 < len(command_sequence)
                and command_sequence[j + 1] == "|"
                and command_sequence[j + 2]
                not in ["&&", "||", "|", "&", ";"]
            ):
                j += 2
            i = j + (2 if j + 1 < len(command_sequence) and command_sequence[j + 1] == "&" else 1)
            continue
        elif prev_operator == "||" and retcode == 0:
            # Previous command succeeded, skip this branch (including pipeline/background).
            j = i
            while (
                j + 2 < len(command_sequence)
                and command_sequence[j + 1] == "|"
                and command_sequence[j + 2]
                not in ["&&", "||", "|", "&", ";"]
            ):
                j += 2
            i = j + (2 if j + 1 < len(command_sequence) and command_sequence[j + 1] == "&" else 1)
            continue

        # Build a pipeline command sequence at top-level (`cmd1 | cmd2 | ...`).
        pipeline_parts = [current_item]
        j = i
        while (
            j + 2 < len(command_sequence)
            and command_sequence[j + 1] == "|"
            and command_sequence[j + 2]
            not in ["&&", "||", "|", "&", ";"]
        ):
            pipeline_parts.append(command_sequence[j + 2])
            j += 2

        # Expand `$?` for each command segment so sequences like
        # `cmd1; echo $?` reflect the exit code from `cmd1`.
        pipeline_parts = [replace_exit_code(part, retcode) for part in pipeline_parts]
        full_command = " | ".join(pipeline_parts)
        background = bool(j + 1 < len(command_sequence) and command_sequence[j + 1] == "&")

        parsed_parts = [_parse_command(part) for part in pipeline_parts]
        if any(part[0] is None for part in parsed_parts):
            shell_context.log.warn(f'INFO: unknown syntax -> "{full_command}"')
            sys.stderr.write(f"*** unknown syntax: {full_command}\n")
            return 1

        executable, argument, _, assignments = parsed_parts[0]
        if executable is None:
            shell_context.log.warn(f'INFO: unknown syntax -> "{current_item}"')
            sys.stderr.write(f"*** unknown syntax: {current_item}\n")
            return 1

        # Assignment-only command: persist in current shell environment.
        if not executable and assignments:
            for var_name, var_value in assignments:
                os.environ[var_name] = var_value
            retcode = 0
            i = j + (2 if background else 1)
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

        # Execute command
        if len(pipeline_parts) == 1 and executable in builtincmd.builtins_list and not background:
            retcode, shell_context.conf = handle_builtin_command(
                full_command, executable, argument, shell_context
            )
        elif all(
            executable_name
            and _is_allowed_command(executable_name, part, shell_context.conf)
            for (executable_name, _, _, _), part in zip(parsed_parts, pipeline_parts)
        ):
            if "path_noexec" in shell_context.conf:
                os.environ["LD_PRELOAD"] = shell_context.conf["path_noexec"]
            retcode = exec_cmd(full_command, background=background)
        else:
            shell_context.log.warn(f'INFO: unknown syntax -> "{full_command}"')
            sys.stderr.write(f"*** unknown syntax: {full_command}\n")

        i = j + (2 if background else 1)

    return retcode


def exec_cmd(cmd, background=False):
    """Execute a command exactly as entered, with support for backgrounding via Ctrl+Z."""
    proc = None

    class CtrlZException(Exception):
        """Custom exception to handle Ctrl+Z (SIGTSTP)."""

        pass

    def handle_sigtstp(signum, frame):
        """Handle SIGTSTP (Ctrl+Z) by sending the process to the background."""
        if proc and proc.poll() is None:  # Ensure process is running
            os.killpg(os.getpgid(proc.pid), signal.SIGSTOP)
            builtincmd.BACKGROUND_JOBS.append(proc)  # Add process to background jobs
            job_id = len(builtincmd.BACKGROUND_JOBS)
            sys.stdout.write(f"\n[{job_id}]+  Stopped        {cmd}\n")
            sys.stdout.flush()
            raise CtrlZException()  # Raise custom exception for SIGTSTP handling

    def handle_sigcont(signum, frame):
        """Handle SIGCONT to resume a stopped job in the foreground."""
        if proc and proc.poll() is None:
            os.killpg(os.getpgid(proc.pid), signal.SIGCONT)

    try:
        # Register SIGTSTP (Ctrl+Z) and SIGCONT (resume) signal handlers
        signal.signal(signal.SIGTSTP, handle_sigtstp)
        signal.signal(signal.SIGCONT, handle_sigcont)
        cmd_args = ["bash", "-c", cmd]
        if background:
            with open(os.devnull, "r") as devnull_in:
                proc = subprocess.Popen(
                    cmd_args,
                    stdin=devnull_in,  # Redirect input to /dev/null
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                    preexec_fn=os.setsid,
                )
            proc.lshell_cmd = cmd
            # add to background jobs and return
            builtincmd.BACKGROUND_JOBS.append(proc)
            job_id = len(builtincmd.BACKGROUND_JOBS)
            print(f"[{job_id}] {cmd} (pid: {proc.pid})")
            retcode = 0
        else:
            proc = subprocess.Popen(cmd_args, preexec_fn=os.setsid)
            proc.lshell_cmd = cmd
            proc.communicate()
            retcode = proc.returncode if proc.returncode is not None else 0

    except FileNotFoundError:
        sys.stderr.write(
            "Command execution failed: required shell interpreter not found.\n"
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
