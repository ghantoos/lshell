""" Utils for lshell """
# pylint: disable=too-many-lines

import re
import subprocess
import os
import sys
import random
import string
import shlex
import shutil
import threading
from getpass import getuser
from time import strftime, gmtime
import signal

# import lshell specifics
from lshell import variables
from lshell import builtincmd
from lshell import audit
from lshell import containment


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
_SHELL_BUILTINS = {
    ".",
    ":",
    "alias",
    "bg",
    "bind",
    "break",
    "builtin",
    "caller",
    "cd",
    "command",
    "compgen",
    "complete",
    "compopt",
    "continue",
    "declare",
    "dirs",
    "disown",
    "echo",
    "enable",
    "eval",
    "exec",
    "exit",
    "export",
    "false",
    "fc",
    "fg",
    "getopts",
    "hash",
    "help",
    "history",
    "jobs",
    "kill",
    "let",
    "local",
    "logout",
    "mapfile",
    "popd",
    "printf",
    "pushd",
    "pwd",
    "read",
    "readonly",
    "return",
    "set",
    "shift",
    "shopt",
    "source",
    "suspend",
    "test",
    "times",
    "trap",
    "true",
    "type",
    "typeset",
    "ulimit",
    "umask",
    "unalias",
    "unset",
    "wait",
    "[",
}


def _expand_braced_parameter(expr, support_advanced=True):
    """Expand ${...} expressions for the supported shell parameter forms."""
    if not expr:
        return None

    if not support_advanced:
        # Runtime parser mode: keep ${...} literal so policy checks can gate it.
        return None

    if expr.startswith("#"):
        name = expr[1:]
        if _ENV_VAR_NAME_RE.fullmatch(name):
            return str(len(os.environ.get(name, "")))
        return None

    match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)(:?[-+])(.*)", expr, re.DOTALL)
    if match:
        name, operator, operand = match.groups()
        value = os.environ.get(name)
        is_set = value is not None
        is_non_null = bool(value)

        if operator == ":-":
            return value if is_non_null else operand
        if operator == "-":
            return value if is_set else operand
        if operator == ":+":  # `${VAR:+word}` => word iff VAR is set and non-empty.
            return operand if is_non_null else ""
        if operator == "+":
            return operand if is_set else ""

    if _ENV_VAR_NAME_RE.fullmatch(expr):
        return os.environ.get(expr, "")

    return None


def _consume_env_var(text, start, support_advanced_braced=True):
    """Parse a variable reference at text[start] where text[start] == '$'."""
    length = len(text)
    if start + 1 >= length:
        return None, 1

    next_char = text[start + 1]
    if next_char == "{":
        closing = text.find("}", start + 2)
        if closing == -1:
            return None, 1
        expression = text[start + 2 : closing]
        expanded = _expand_braced_parameter(
            expression, support_advanced=support_advanced_braced
        )
        if expanded is not None:
            return expanded, (closing - start + 1)
        return None, 1

    match = _ENV_VAR_NAME_RE.match(text, start + 1)
    if match:
        name = match.group(0)
        return os.environ.get(name, ""), (match.end() - start)

    return None, 1


def expand_vars_quoted(line, support_advanced_braced=True):
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
            replacement, consumed = _consume_env_var(
                line, i, support_advanced_braced=support_advanced_braced
            )
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


def _command_exists(executable):
    """Return True when command token resolves to a runnable command."""
    if not executable:
        return False

    if executable in _SHELL_BUILTINS:
        return True

    if "/" in executable:
        return os.path.isfile(executable) and os.access(executable, os.X_OK)

    return shutil.which(executable) is not None


def handle_builtin_command(full_command, executable, argument, shell_context):
    """
    Handle built-in commands like cd, lpath, lsudo, etc.
    Returns tuple of (retcode, conf)
    """

    retcode = 0
    conf = shell_context.conf

    if executable == "help":
        shell_context.do_help(executable)
    elif executable == "policy-show":
        shell_context.do_policy_show(argument)
    elif executable == "exit":
        shell_context.do_exit(full_command)
    elif executable == "history":
        retcode = builtincmd.cmd_history(shell_context.conf, shell_context.log)
    elif executable == "cd":
        retcode, shell_context.conf = builtincmd.cmd_cd(argument, shell_context.conf)
    elif executable == "ls":
        retcode = exec_cmd(full_command, conf=shell_context.conf, log=shell_context.log)
    elif executable in ["lpath", "policy-path"]:
        retcode = builtincmd.cmd_lpath(conf)
    elif executable in ["lsudo", "policy-sudo"]:
        retcode = builtincmd.cmd_lsudo(conf)
    elif executable == "export":
        retcode, var = builtincmd.cmd_export(full_command)
        if retcode == 1:
            shell_context.log.critical(
                f"lshell: forbidden environment variable: {var}"
            )
    elif executable == "source":
        retcode = builtincmd.cmd_source(argument)
    elif executable == "fg":
        retcode = builtincmd.cmd_bg_fg(executable, argument)
    elif executable == "bg":
        retcode = builtincmd.cmd_bg_fg(executable, argument)
    elif executable == "jobs":
        retcode = builtincmd.cmd_jobs()

    return retcode, conf


def cmd_parse_execute(command_line, shell_context=None, trusted_protocol=False):
    """Parse and execute a shell command line.

    trusted_protocol is only for protocol commands (scp/sftp-server)
    that were already validated in run_overssh.
    """
    from lshell.engine import executor as engine_executor  # pylint: disable=import-outside-toplevel

    return engine_executor.execute_for_shell(
        command_line,
        shell_context=shell_context,
        trusted_protocol=trusted_protocol,
    )


def exec_cmd(cmd, background=False, extra_env=None, conf=None, log=None):
    """Execute a command exactly as entered, with support for backgrounding via Ctrl+Z."""
    proc = None
    detached_session = True
    exec_env = dict(os.environ)
    runtime_limits = containment.get_runtime_limits(conf or {})
    command_timeout = runtime_limits.command_timeout
    unsupported_limits = containment.unsupported_rlimits(runtime_limits)
    if conf is not None and log and unsupported_limits:
        logged_key = "_runtime_unsupported_limits_logged"
        already_logged = set(conf.get(logged_key, []))
        pending = [item for item in unsupported_limits if item not in already_logged]
        if pending:
            log.warning(
                "lshell: runtime containment limits unsupported on this platform: "
                + ", ".join(sorted(pending))
            )
            conf[logged_key] = sorted(already_logged.union(pending))
    if extra_env:
        exec_env.update(extra_env)
    # Prevent non-interactive shell startup file injection.
    exec_env.pop("BASH_ENV", None)
    exec_env.pop("ENV", None)

    class CtrlZException(Exception):
        """Custom exception to handle Ctrl+Z (SIGTSTP)."""

        pass

    def handle_sigtstp(signum, frame):
        """Handle SIGTSTP (Ctrl+Z) by sending the process to the background."""
        if proc and proc.poll() is None:  # Ensure process is running
            if detached_session:
                os.killpg(os.getpgid(proc.pid), signal.SIGSTOP)
            else:
                os.kill(proc.pid, signal.SIGSTOP)
            # Keep one job entry per process to avoid duplicates on repeated suspend/resume.
            if proc in builtincmd.BACKGROUND_JOBS:
                job_id = builtincmd.BACKGROUND_JOBS.index(proc) + 1
            else:
                builtincmd.BACKGROUND_JOBS.append(proc)
                job_id = len(builtincmd.BACKGROUND_JOBS)
            sys.stdout.write(f"\n[{job_id}]+  Stopped        {cmd}\n")
            sys.stdout.flush()
            raise CtrlZException()  # Raise custom exception for SIGTSTP handling

    def handle_sigcont(signum, frame):
        """Handle SIGCONT to resume a stopped job in the foreground."""
        if proc and proc.poll() is None:
            if detached_session:
                os.killpg(os.getpgid(proc.pid), signal.SIGCONT)
            else:
                os.kill(proc.pid, signal.SIGCONT)

    def _kill_process_group(target):
        if not target or target.poll() is not None:
            return
        try:
            if detached_session:
                os.killpg(os.getpgid(target.pid), signal.SIGKILL)
            else:
                os.kill(target.pid, signal.SIGKILL)
        except OSError:
            return

    def _timeout_reason():
        return containment.reason_with_details(
            "runtime_limit.command_timeout_exceeded",
            timeout=command_timeout,
        )

    def _emit_timeout_event():
        if conf:
            audit.log_command_event(
                conf,
                cmd,
                allowed=False,
                reason=_timeout_reason(),
                level="warning",
            )
        if log:
            log.warning(
                "lshell: runtime containment timed out command: "
                f'timeout={command_timeout}s, command="{cmd}"'
            )
        sys.stderr.write(
            f"lshell: command timed out after {command_timeout}s: {cmd}\n"
        )

    previous_sigtstp_handler = signal.getsignal(signal.SIGTSTP)
    previous_sigcont_handler = signal.getsignal(signal.SIGCONT)

    try:
        # Register SIGTSTP (Ctrl+Z) and SIGCONT (resume) signal handlers
        signal.signal(signal.SIGTSTP, handle_sigtstp)
        signal.signal(signal.SIGCONT, handle_sigcont)
        cmd_args = ["bash", "-c", cmd]
        try:
            split_cmd = shlex.split(cmd, posix=True)
        except ValueError:
            split_cmd = []
        if split_cmd and split_cmd[0] in ("sudo", "su"):
            cmd_args = split_cmd
            if not background:
                detached_session = False
        preexec_fn = None
        needs_resource_limits = runtime_limits.max_processes > 0
        if os.name == "posix" and (detached_session or needs_resource_limits):
            preexec_fn = containment.build_preexec_fn(detached_session, runtime_limits)
        if background:
            with open(os.devnull, "r") as devnull_in:
                popen_kwargs = {
                    "stdin": devnull_in,
                    "stdout": sys.stdout,
                    "stderr": sys.stderr,
                    "env": exec_env,
                }
                if preexec_fn is not None:
                    popen_kwargs["preexec_fn"] = preexec_fn
                proc = subprocess.Popen(cmd_args, **popen_kwargs)
            proc.lshell_cmd = cmd
            proc.lshell_timeout_timer = None
            if command_timeout > 0:

                def _background_timeout():
                    if proc and proc.poll() is None:
                        proc.lshell_timeout_triggered = True
                        _kill_process_group(proc)
                        _emit_timeout_event()

                timeout_timer = threading.Timer(command_timeout, _background_timeout)
                timeout_timer.daemon = True
                timeout_timer.start()
                proc.lshell_timeout_timer = timeout_timer
            # add to background jobs and return
            builtincmd.BACKGROUND_JOBS.append(proc)
            job_id = len(builtincmd.BACKGROUND_JOBS)
            print(f"[{job_id}] {cmd} (pid: {proc.pid})")
            retcode = 0
        else:
            popen_kwargs = {"env": exec_env}
            if preexec_fn is not None:
                popen_kwargs["preexec_fn"] = preexec_fn
            proc = subprocess.Popen(cmd_args, **popen_kwargs)
            proc.lshell_cmd = cmd
            if command_timeout > 0:
                proc.communicate(timeout=command_timeout)
            else:
                proc.communicate()
            retcode = proc.returncode if proc.returncode is not None else 0

    except FileNotFoundError:
        sys.stderr.write(
            "Command execution failed: required shell interpreter not found.\n"
        )
        retcode = 127
    except subprocess.TimeoutExpired:
        _kill_process_group(proc)
        if proc:
            proc.communicate()
        _emit_timeout_event()
        retcode = 124
    except subprocess.SubprocessError as exception:
        reason = containment.reason_with_details(
            "runtime_limit.preexec_application_failed",
            error=str(exception),
        )
        if conf:
            audit.log_command_event(
                conf,
                cmd,
                allowed=False,
                reason=reason,
                level="warning",
            )
        if log:
            log.critical(
                "lshell: runtime containment denied command execution: "
                f"{reason}"
            )
        sys.stderr.write(
            "lshell: command denied: unable to apply runtime containment limits\n"
        )
        retcode = 126
    except CtrlZException:  # Handle Ctrl+Z
        retcode = 0
    except KeyboardInterrupt:  # Handle Ctrl+C
        if proc and proc.poll() is None:
            if detached_session:
                os.killpg(os.getpgid(proc.pid), signal.SIGINT)
            else:
                os.kill(proc.pid, signal.SIGINT)
        retcode = 130
    finally:
        if (
            proc is not None
            and getattr(proc, "lshell_timeout_timer", None) is not None
            and proc.poll() is not None
        ):
            proc.lshell_timeout_timer.cancel()
        signal.signal(signal.SIGTSTP, previous_sigtstp_handler)
        signal.signal(signal.SIGCONT, previous_sigcont_handler)

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
