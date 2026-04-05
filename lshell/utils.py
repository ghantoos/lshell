"""Utils for lshell"""

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
from time import strftime, gmtime, monotonic
import signal

# import lshell specifics
from lshell import variables
from lshell import builtincmd
from lshell import audit
from lshell import containment
from lshell import expansion_inspector
from lshell.engine import executor as engine_executor


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
    proc_subst_depth = 0
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

        if (
            not in_single
            and not in_double
            and not in_backtick
            and char in {"<", ">"}
            and next_char == "("
        ):
            proc_subst_depth += 1
            current.append(char)
            current.append(next_char)
            i += 2
            continue

        if cmd_subst_depth > 0 and not in_single and not in_backtick and char == ")":
            cmd_subst_depth -= 1
            current.append(char)
            i += 1
            continue

        if proc_subst_depth > 0 and not in_single and not in_backtick and char == ")":
            proc_subst_depth -= 1
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
            and proc_subst_depth == 0
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

    if (
        in_single
        or in_double
        or in_backtick
        or cmd_subst_depth
        or var_brace_depth
        or proc_subst_depth
    ):
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


def _is_bash_function_env_name(name):
    """Return True for env vars used by Bash function import."""
    return name.startswith("BASH_FUNC_")


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

    if "/" in executable:
        return os.path.isfile(executable) and os.access(executable, os.X_OK)

    return shutil.which(executable) is not None


def handle_builtin_command(full_command, executable, argument, shell_context):
    """
    Handle built-in commands like cd and lshow.
    Returns tuple of (retcode, conf)
    """

    retcode = 0
    conf = shell_context.conf

    if executable == "help":
        shell_context.do_help(executable)
    elif executable == "lshow":
        shell_context.do_lshow(argument)
    elif executable == "exit":
        shell_context.do_exit(full_command)
    elif executable == "history":
        retcode = builtincmd.cmd_history(shell_context.conf, shell_context.log)
    elif executable == "cd":
        retcode, shell_context.conf = builtincmd.cmd_cd(argument, shell_context.conf)
    elif executable == "ls":
        retcode = exec_cmd(full_command, conf=shell_context.conf, log=shell_context.log)
    elif executable == "export":
        retcode, var = builtincmd.cmd_export(full_command)
        if retcode == 1:
            shell_context.log.critical(f"lshell: forbidden environment variable: {var}")
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
    return engine_executor.execute_for_shell(
        command_line,
        shell_context=shell_context,
        trusted_protocol=trusted_protocol,
    )


def _contains_unquoted_redirection(command):
    """Return True when unquoted shell redirection markers are present."""
    in_single = False
    in_double = False
    in_backtick = False
    escaped = False

    for char in command:
        if escaped:
            escaped = False
            continue

        if char == "\\" and not in_single:
            escaped = True
            continue

        if char == "'" and not in_double and not in_backtick:
            in_single = not in_single
            continue

        if char == '"' and not in_single and not in_backtick:
            in_double = not in_double
            continue

        if char == "`" and not in_single:
            in_backtick = not in_backtick
            continue

        if in_single or in_double or in_backtick:
            continue

        if char in {"<", ">"}:
            return True

    return False


def unsupported_runtime_syntax_reason(command):
    """Return user-facing reason when command relies on unsupported shell syntax."""
    expansion_info = expansion_inspector.inspect_shell_expansions(command)
    if expansion_info.malformed:
        return "unsupported shell expansion syntax"

    for expansion in expansion_info.executable_expansions:
        if expansion.kind == "command_substitution":
            return "command substitution ($(...))"
        if expansion.kind == "backtick":
            return "backtick command substitution (`...`)"
        if expansion.kind == "process_substitution":
            return "process substitution (<(...) or >(...))"

    if _contains_unquoted_redirection(command):
        return "redirection operators (<, >, <<, >>, <<<, 2>&1, ...)"

    return None


def _split_pipeline_for_execution(command):
    """Split one execution line into shellless pipeline stages."""
    sequence = split_command_sequence(command)
    if sequence is None:
        return None
    if not sequence:
        return []

    operators = {"&&", "||", ";", "&", "|"}
    stages = []
    expect_command = True

    for token in sequence:
        if expect_command:
            if token in operators:
                return None
            stages.append(token)
            expect_command = False
            continue

        if token != "|":
            return None
        expect_command = True

    if expect_command:
        return None

    return stages


def exec_cmd(cmd, background=False, extra_env=None, conf=None, log=None):
    """Execute command(s) with shell=False, including manual pipeline wiring."""
    proc = None
    pipeline_processes = []
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
    # Prevent function import from environment (e.g. BASH_FUNC_* poisoning).
    for key in list(exec_env):
        if _is_bash_function_env_name(key):
            exec_env.pop(key, None)

    stage_texts = _split_pipeline_for_execution(cmd)
    if stage_texts is None or not stage_texts:
        sys.stderr.write(f"lshell: unknown syntax: {cmd}\n")
        return 1

    stage_specs = []
    for stage_text in stage_texts:
        expanded_stage = expand_vars_quoted(stage_text, support_advanced_braced=True)
        unsupported_reason = unsupported_runtime_syntax_reason(expanded_stage)
        if unsupported_reason:
            sys.stderr.write(
                "lshell: unsupported shell syntax in command execution: "
                f"{unsupported_reason}\n"
            )
            return 126

        executable, _argument, split, assignments = _parse_command(expanded_stage)
        if executable is None:
            sys.stderr.write(f"lshell: unknown syntax: {stage_text}\n")
            return 1

        if not executable:
            sys.stderr.write(f"lshell: unknown syntax: {stage_text}\n")
            return 1

        stage_env = dict(exec_env)
        for var_name, var_value in assignments:
            stage_env[var_name] = var_value

        stage_specs.append(
            {
                "argv": split[len(assignments) :],
                "env": stage_env,
            }
        )

    if stage_specs and stage_specs[0]["argv"] and stage_specs[0]["argv"][0] in (
        "sudo",
        "su",
    ):
        if not background:
            detached_session = False

    class CtrlZException(Exception):
        """Custom exception to handle Ctrl+Z (SIGTSTP)."""

        pass

    def _pipeline_members(target):
        if target is None:
            return []
        members = getattr(target, "lshell_pipeline", None)
        if not members:
            return [target]
        return list(members)

    def _running_pipeline_members(target):
        return [member for member in _pipeline_members(target) if member.poll() is None]

    def _signal_pipeline(target, signum):
        for member in _running_pipeline_members(target):
            try:
                os.kill(member.pid, signum)
            except OSError:
                continue

    def _pipeline_pgid(target):
        pgid = getattr(target, "lshell_pgid", None)
        if pgid is not None:
            return pgid
        return os.getpgid(target.pid)

    def _make_preexec_fn(stage_index, pipeline_pgid, needs_resource_limits):
        if os.name != "posix":
            return None

        if len(stage_specs) == 1 and (detached_session or needs_resource_limits):
            return containment.build_preexec_fn(detached_session, runtime_limits)

        if not detached_session and not needs_resource_limits:
            return None

        def _preexec():
            if detached_session:
                if stage_index == 0:
                    os.setpgid(0, 0)
                else:
                    os.setpgid(0, pipeline_pgid)
            containment.apply_rlimits(runtime_limits)

        return _preexec

    def handle_sigtstp(signum, frame):
        """Handle SIGTSTP (Ctrl+Z) by sending the process to the background."""
        if proc and _running_pipeline_members(proc):  # Ensure process is running
            if detached_session and os.name == "posix":
                os.killpg(_pipeline_pgid(proc), signal.SIGSTOP)
            else:
                _signal_pipeline(proc, signal.SIGSTOP)
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
        if proc and _running_pipeline_members(proc):
            if detached_session and os.name == "posix":
                os.killpg(_pipeline_pgid(proc), signal.SIGCONT)
            else:
                _signal_pipeline(proc, signal.SIGCONT)

    def _kill_process_group(target):
        if not target or not _running_pipeline_members(target):
            return
        try:
            if detached_session and os.name == "posix":
                os.killpg(_pipeline_pgid(target), signal.SIGKILL)
            else:
                _signal_pipeline(target, signal.SIGKILL)
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
        sys.stderr.write(f"lshell: command timed out after {command_timeout}s: {cmd}\n")

    def _wait_process(target, timeout=None):
        """Wait for a subprocess using wait(), with communicate() compatibility fallback."""
        wait_method = getattr(target, "wait", None)
        if callable(wait_method):
            if timeout is None:
                return wait_method()
            return wait_method(timeout=timeout)

        communicate_method = getattr(target, "communicate", None)
        if callable(communicate_method):
            if timeout is None:
                communicate_method()
            else:
                try:
                    communicate_method(timeout=timeout)
                except TypeError:
                    communicate_method()
            return target.returncode

        raise AttributeError("process object has no wait() or communicate() method")

    def _terminate_pipeline_members(members):
        """Force-stop and reap any already-started pipeline members."""
        for member in members:
            if member.poll() is not None:
                continue
            try:
                if os.name == "posix" and detached_session:
                    os.killpg(os.getpgid(member.pid), signal.SIGKILL)
                else:
                    os.kill(member.pid, signal.SIGKILL)
            except OSError:
                try:
                    os.kill(member.pid, signal.SIGKILL)
                except OSError:
                    continue

        for member in members:
            try:
                _wait_process(member, timeout=1)
            except (subprocess.TimeoutExpired, OSError, AttributeError):
                continue

    previous_sigtstp_handler = signal.getsignal(signal.SIGTSTP)
    previous_sigcont_handler = signal.getsignal(signal.SIGCONT)

    try:
        # Register SIGTSTP (Ctrl+Z) and SIGCONT (resume) signal handlers
        signal.signal(signal.SIGTSTP, handle_sigtstp)
        signal.signal(signal.SIGCONT, handle_sigcont)

        if runtime_limits.max_processes > 0 and len(stage_specs) > runtime_limits.max_processes:
            reason = containment.reason_with_details(
                "runtime_limit.max_processes_exceeded",
                requested=len(stage_specs),
                limit=runtime_limits.max_processes,
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
                    f"requested_processes={len(stage_specs)}, "
                    f"limit={runtime_limits.max_processes}, command=\"{cmd}\""
                )
            sys.stderr.write(
                "lshell: command denied: "
                f"max_processes={runtime_limits.max_processes} "
                "is lower than required pipeline stages\n"
            )
            return 126

        needs_resource_limits = runtime_limits.max_processes > 0
        pipeline_pgid = None
        previous_stdout = None
        devnull_in = open(os.devnull, "r", encoding="utf-8") if background else None

        try:
            try:
                for index, stage in enumerate(stage_specs):
                    popen_kwargs = {"env": stage["env"]}
                    if index == 0:
                        if background and devnull_in is not None:
                            popen_kwargs["stdin"] = devnull_in
                    else:
                        popen_kwargs["stdin"] = previous_stdout

                    if index < len(stage_specs) - 1:
                        popen_kwargs["stdout"] = subprocess.PIPE
                    elif background:
                        popen_kwargs["stdout"] = sys.stdout
                        popen_kwargs["stderr"] = sys.stderr

                    preexec_fn = _make_preexec_fn(index, pipeline_pgid, needs_resource_limits)
                    if preexec_fn is not None:
                        popen_kwargs["preexec_fn"] = preexec_fn

                    stage_proc = subprocess.Popen(stage["argv"], **popen_kwargs)
                    pipeline_processes.append(stage_proc)

                    if previous_stdout is not None:
                        previous_stdout.close()
                    previous_stdout = (
                        stage_proc.stdout if index < len(stage_specs) - 1 else None
                    )

                    if (
                        index == 0
                        and detached_session
                        and os.name == "posix"
                        and len(stage_specs) > 1
                    ):
                        pipeline_pgid = stage_proc.pid
            except Exception:
                _terminate_pipeline_members(pipeline_processes)
                raise
        finally:
            if previous_stdout is not None:
                previous_stdout.close()
            if devnull_in is not None:
                devnull_in.close()

        proc = pipeline_processes[-1]
        proc.lshell_cmd = cmd
        proc.lshell_pipeline = tuple(pipeline_processes)
        proc.lshell_timeout_timer = None
        if detached_session and os.name == "posix":
            try:
                proc.lshell_pgid = pipeline_pgid or os.getpgid(proc.pid)
            except OSError:
                proc.lshell_pgid = pipeline_pgid

        if background:
            if command_timeout > 0:

                def _background_timeout():
                    if proc and _running_pipeline_members(proc):
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
            deadline = monotonic() + command_timeout if command_timeout > 0 else None
            if command_timeout > 0:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(proc.args, command_timeout)
                _wait_process(proc, timeout=remaining)
            else:
                _wait_process(proc)

            for member in pipeline_processes[:-1]:
                if command_timeout > 0:
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(member.args, command_timeout)
                    _wait_process(member, timeout=remaining)
                else:
                    _wait_process(member)
            retcode = proc.returncode if proc.returncode is not None else 0

    except FileNotFoundError as exception:
        missing = (
            str(exception.filename)
            if getattr(exception, "filename", None)
            else (proc.args[0] if proc and getattr(proc, "args", None) else cmd)
        )
        sys.stderr.write(f'lshell: command not found: "{missing}"\n')
        retcode = 127
    except subprocess.TimeoutExpired:
        _kill_process_group(proc)
        for member in _pipeline_members(proc):
            try:
                _wait_process(member, timeout=1)
            except (subprocess.TimeoutExpired, OSError, AttributeError):
                continue
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
                "lshell: runtime containment denied command execution: " f"{reason}"
            )
        sys.stderr.write(
            "lshell: command denied: unable to apply runtime containment limits\n"
        )
        retcode = 126
    except CtrlZException:  # Handle Ctrl+Z
        retcode = 0
    except KeyboardInterrupt:  # Handle Ctrl+C
        if proc and _running_pipeline_members(proc):
            if detached_session and os.name == "posix":
                os.killpg(_pipeline_pgid(proc), signal.SIGINT)
            else:
                _signal_pipeline(proc, signal.SIGINT)
        retcode = 130
    finally:
        if (
            proc is not None
            and getattr(proc, "lshell_timeout_timer", None) is not None
            and not _running_pipeline_members(proc)
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
