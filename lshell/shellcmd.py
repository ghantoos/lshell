"""This module contains the main class of lshell, it is the class that is
responsible for the command line interface. It inherits from the cmd.Cmd class
from the Python standard library. It offers the default methods to add
security checks, logging, etc.
"""

import cmd
import ctypes
import ctypes.util
import sys
import os
import re
import signal
import readline
import shutil

# import lshell specifics
from lshell.config.runtime import CheckConfig
from lshell import utils
from lshell import builtincmd
from lshell import messages
from lshell import sec
from lshell import completion
from lshell import variables
from lshell.config import diagnostics as policy_mode
from lshell import audit
from lshell import history as history_utils


READLINE_HISTORY_SEARCH_BINDINGS = (
    '"\\e[A": history-search-backward',
    '"\\eOA": history-search-backward',
    '"\\e[B": history-search-forward',
    '"\\eOB": history-search-forward',
)
READLINE_INCREMENTAL_SEARCH_BINDINGS = (
    '"\\C-r": reverse-search-history',
    '"\\C-s": forward-search-history',
)

_READLINE_LIB = None
_READLINE_COMMAND_FUNC = None
_READLINE_HISTORY_SEARCH_CALLBACKS = []
_ACTIVE_HISTORY_SEARCH_SHELL = None
_ACTIVE_COMPLETION_SHELL = None


def _readline_uses_gnu_backend():
    """Return True only when Python readline is backed by GNU readline."""
    doc = readline.__doc__ or ""
    return "libedit" not in doc.lower()


def _get_readline_library():
    """Return the loaded GNU readline shared library when available."""
    global _READLINE_LIB, _READLINE_COMMAND_FUNC

    if _READLINE_LIB is not None:
        return _READLINE_LIB

    if not _readline_uses_gnu_backend():
        return None

    library_name = ctypes.util.find_library("readline")
    if not library_name:
        return None

    try:
        readline_lib = ctypes.CDLL(library_name)
    except OSError:
        return None

    _READLINE_COMMAND_FUNC = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_int)
    readline_lib.rl_bind_keyseq.argtypes = [ctypes.c_char_p, _READLINE_COMMAND_FUNC]
    readline_lib.rl_bind_keyseq.restype = ctypes.c_int
    readline_lib.rl_replace_line.argtypes = [ctypes.c_char_p, ctypes.c_int]
    readline_lib.rl_replace_line.restype = None
    readline_lib.rl_redisplay.argtypes = []
    readline_lib.rl_redisplay.restype = None

    _READLINE_LIB = readline_lib
    return _READLINE_LIB


def _replace_readline_buffer(text):
    """Replace the active readline buffer with text and move cursor to the end."""
    readline_lib = _get_readline_library()
    if readline_lib is None:
        return

    encoded = text.encode("utf-8")
    readline_lib.rl_replace_line(encoded, 0)
    encoded_length = len(encoded)
    ctypes.c_int.in_dll(readline_lib, "rl_point").value = encoded_length
    ctypes.c_int.in_dll(readline_lib, "rl_end").value = encoded_length
    readline_lib.rl_redisplay()


def _readline_point():
    """Return the current cursor position in the active readline buffer."""
    readline_lib = _get_readline_library()
    if readline_lib is None:
        return len(readline.get_line_buffer())
    return ctypes.c_int.in_dll(readline_lib, "rl_point").value


def _readline_char_point(text):
    """Map readline's byte cursor offset to a Python string character index."""
    point = _readline_point()
    encoded = text.encode("utf-8")
    if point >= len(encoded):
        return len(text)
    return len(encoded[:point].decode("utf-8", "ignore"))


def _dispatch_history_search(backward):
    """Route readline up/down callbacks to the active shell instance."""
    shell = _ACTIVE_HISTORY_SEARCH_SHELL
    if shell is None:
        return 0

    try:
        return shell.history_search(backward)
    except Exception:
        shell.reset_history_search_state()
        return 0


def _history_search_backward(unused_count, unused_key):
    """Readline callback for backward prefix history search."""
    return _dispatch_history_search(backward=True)


def _history_search_forward(unused_count, unused_key):
    """Readline callback for forward prefix history search."""
    return _dispatch_history_search(backward=False)


def _bind_custom_history_search(shell):
    """Bind arrow keys to lshell-managed prefix history search callbacks."""
    global _ACTIVE_HISTORY_SEARCH_SHELL

    readline_lib = _get_readline_library()
    if readline_lib is None or _READLINE_COMMAND_FUNC is None:
        return False

    backward = _READLINE_COMMAND_FUNC(_history_search_backward)
    forward = _READLINE_COMMAND_FUNC(_history_search_forward)
    _READLINE_HISTORY_SEARCH_CALLBACKS[:] = [backward, forward]
    _ACTIVE_HISTORY_SEARCH_SHELL = shell

    bindings = (
        (b"\\e[A", backward),
        (b"\\eOA", backward),
        (b"\\e[B", forward),
        (b"\\eOB", forward),
    )
    return all(readline_lib.rl_bind_keyseq(keyseq, callback) == 0 for keyseq, callback in bindings)


def _display_completion_matches(substitution, matches, longest_match_length):
    """Render completion matches with a concise, sorted lshell-specific header."""
    shell = _ACTIVE_COMPLETION_SHELL
    if shell is None:
        return
    shell.display_completion_matches(substitution, matches, longest_match_length)


class ShellCmd(cmd.Cmd, object):
    """Main lshell CLI class"""

    def __init__(
        self,
        userconf,
        args,
        stdin=None,
        stdout=None,
        stderr=None,
        g_cmd=None,
        g_line=None,
    ):
        if stdin is None:
            self.stdin = sys.stdin
        else:
            self.stdin = stdin
        if stdout is None:
            self.stdout = sys.stdout
        else:
            self.stdout = stdout
        if stderr is None:
            self.stderr = sys.stderr
        else:
            self.stderr = stderr

        self.conf = userconf
        self.log = self.conf["logpath"]
        self.kill_jobs_at_exit = False

        # Set timer
        if self.conf["timer"] > 0:
            self.mytimer(self.conf["timer"])
        self.identchars = self.identchars + "+./-"
        self.log.error("Logged in")
        cmd.Cmd.__init__(self)

        # set prompt
        self.conf["promptprint"] = utils.updateprompt(os.getcwd(), self.conf)

        self.intro = self.conf["intro"]

        # initialize oldpwd variable to home directory
        self.conf["oldpwd"] = self.conf["home_path"]

        # initialize cli variables
        self.g_cmd = g_cmd
        self.g_line = g_line
        self.args = args

        # initialize return code
        self.retcode = 0
        self.reset_history_search_state()
        self.completion_display_context = "Allowed completions"
        self.old_display_matches_hook = None

        # run overssh, if needed
        self.run_overssh()

    def __getattr__(self, attr):
        """This method actually takes care of all the called method that are
        not resolved (i.e not existing methods). It actually will simulate
        the existence of any method    entered in the 'allowed' variable list.

        e.g. You just have to add 'uname' in list of allowed commands in
        the 'allowed' variable, and lshell will react as if you had
        added a do_uname in the ShellCmd class!
        """

        # in case the configuration file has been modified, reload it
        if self.conf["config_mtime"] != os.path.getmtime(self.conf["configfile"]):
            session_id = self.conf.get("session_id")
            self.conf = CheckConfig(
                ["--config", self.conf["configfile"]], refresh=1
            ).returnconf()
            if session_id:
                self.conf["session_id"] = session_id
            self.conf["promptprint"] = utils.updateprompt(os.getcwd(), self.conf)
            self.log = self.conf["logpath"]

        if self.conf["timer"] > 0:
            self.mytimer(0)

        # replace $? with the exit code
        self.g_line = utils.replace_exit_code(self.g_line, self.retcode)

        if isinstance(self.conf["aliases"], dict):
            self.g_line = utils.get_aliases(self.g_line, self.conf["aliases"])

        self.log.info(f'CMD: "{self.g_line}"')

        self.retcode = utils.cmd_parse_execute(self.g_line, shell_context=self)

        self.g_cmd, self.g_arg, self.g_line = ["", "", ""]

        if self.conf["timer"] > 0:
            self.mytimer(self.conf["timer"])
        return object.__getattribute__(self, attr)

    def run_overssh(self):
        """This method checks if the user is trying to SCP a file onto the
        server. If this is the case, it checks if the user is allowed to use
        SCP or not, and    acts as requested. : )
        """
        def _execute_trusted_ssh_protocol(trusted_protocol=False):
            # Protocol commands are still validated in run_overssh, then
            # executed through the regular command path so policy settings
            # (path/sudo/allowed_cmd_path/env/umask) stay consistent.
            return utils.cmd_parse_execute(
                self.conf["ssh"],
                shell_context=self,
                trusted_protocol=trusted_protocol,
            )

        def _validate_ssh_command(check_path=True):
            ret_check_secure, self.conf = sec.check_secure(
                self.conf["ssh"], self.conf, strict=1, ssh=1
            )
            if ret_check_secure:
                self.ssh_warn("char/command over SSH", self.conf["ssh"])

            if check_path:
                ret_check_path, self.conf = sec.check_path(
                    self.conf["ssh"], self.conf, strict=1, ssh=1
                )
                if ret_check_path == 1:
                    self.ssh_warn("path over SSH", self.conf["ssh"])

        def _with_protocol_in_overssh(protocol_commands):
            overssh = list(self.conf.get("overssh", []))
            changed = False
            for item in protocol_commands:
                if item and item not in overssh:
                    overssh.append(item)
                    changed = True
            if changed:
                self.conf["overssh"] = overssh

        def _aliases_for_ssh_command():
            aliases = self.conf["aliases"]
            if self.conf.get("_auto_ls_alias") and isinstance(aliases, dict):
                aliases = dict(aliases)
                aliases.pop("ls", None)
            return aliases

        if "ssh" in self.conf:
            if "SSH_CLIENT" in os.environ and "SSH_TTY" not in os.environ:
                # Apply aliases consistently for all SSH command paths.
                self.conf["ssh"] = utils.get_aliases(
                    self.conf["ssh"], _aliases_for_ssh_command()
                ).strip()

                # check if sftp is requested and allowed
                if "sftp-server" in self.conf["ssh"]:
                    if self.conf["sftp"] == 1:
                        _with_protocol_in_overssh(
                            variables.TRUSTED_SFTP_PROTOCOL_BINARIES
                        )
                        # sftp-server binary path may live outside restricted
                        # user paths; keep command-level checks but skip path ACL.
                        _validate_ssh_command(check_path=False)
                        self.log.error("SFTP connect")
                        retcode = _execute_trusted_ssh_protocol(trusted_protocol=True)
                        self.log.error("SFTP disconnect")
                        sys.exit(retcode)
                    else:
                        self.log.error("*** forbidden SFTP connection")
                        audit.log_command_event(
                            self.conf,
                            self.conf["ssh"],
                            allowed=False,
                            reason="forbidden SFTP connection",
                        )
                        sys.exit(1)

                # check if scp is requested and allowed
                if self.conf["ssh"].startswith("scp "):
                    if self.conf["scp"] == 1 or "scp" in self.conf["overssh"]:
                        _with_protocol_in_overssh(["scp"])

                        if " -f " in self.conf["ssh"]:
                            # case scp download is allowed
                            if self.conf["scp_download"]:
                                self.log.error(f'SCP: GET "{self.conf["ssh"]}"')
                            # case scp download is forbidden
                            else:
                                self.log.error(
                                    f'SCP: download forbidden: "{self.conf["ssh"]}"'
                                )
                                audit.log_command_event(
                                    self.conf,
                                    self.conf["ssh"],
                                    allowed=False,
                                    reason="forbidden SCP download",
                                )
                                sys.exit(1)
                        elif " -t " in self.conf["ssh"]:
                            # case scp upload is allowed
                            if self.conf["scp_upload"]:
                                if "scpforce" in self.conf:
                                    cmdsplit = self.conf["ssh"].split(" ")
                                    scppath = os.path.realpath(cmdsplit[-1])
                                    forcedpath = os.path.realpath(self.conf["scpforce"])
                                    if scppath != forcedpath:
                                        self.log.error(
                                            f"SCP: forced SCP directory: {scppath}"
                                        )
                                        cmdsplit.pop(-1)
                                        cmdsplit.append(forcedpath)
                                        self.conf["ssh"] = " ".join(cmdsplit)
                                self.log.error(f'SCP: PUT "{self.conf["ssh"]}"')
                            # case scp upload is forbidden
                            else:
                                self.log.error(
                                    f'SCP: upload forbidden: "{self.conf["ssh"]}"'
                                )
                                audit.log_command_event(
                                    self.conf,
                                    self.conf["ssh"],
                                    allowed=False,
                                    reason="forbidden SCP upload",
                                )
                                sys.exit(1)
                        _validate_ssh_command()
                        retcode = _execute_trusted_ssh_protocol(trusted_protocol=False)
                        self.log.error("SCP disconnect")
                        sys.exit(retcode)
                    else:
                        self.ssh_warn("SCP connection", self.conf["ssh"], "scp")

                # check if command is in allowed overssh commands
                elif self.conf["ssh"]:
                    _validate_ssh_command()
                    self.log.error(f'Over SSH: "{self.conf["ssh"]}"')
                    # if command is "help"
                    if self.conf["ssh"] == "help":
                        self.do_help(None)
                        retcode = 0
                    else:
                        retcode = utils.cmd_parse_execute(
                            self.conf["ssh"], shell_context=self
                        )
                    self.log.error("Exited")
                    sys.exit(retcode)

                # else warn and log
                else:
                    self.ssh_warn("command over SSH", self.conf["ssh"])
            else:
                # case of local shell escapes (e.g. pager/editor invoking
                # the login shell with -c). Validate against normal policy.
                self.conf["ssh"] = utils.get_aliases(
                    self.conf["ssh"], _aliases_for_ssh_command()
                )
                ret_check_secure, self.conf = sec.check_secure(
                    self.conf["ssh"],
                    self.conf,
                    strict=self.conf["strict"],
                )
                if ret_check_secure:
                    self.log.error(f'*** forbidden shell escape: "{self.conf["ssh"]}"')
                    audit.log_command_event(
                        self.conf,
                        self.conf["ssh"],
                        allowed=False,
                        reason=audit.pop_decision_reason(
                            self.conf, "forbidden shell escape"
                        ),
                    )
                    sys.exit(1)

                self.log.error(f'Shell escape: "{self.conf["ssh"]}"')
                retcode = utils.cmd_parse_execute(
                    self.conf["ssh"], shell_context=self
                )
                self.log.error("Exited")
                sys.exit(retcode)
            return retcode

    def ssh_warn(self, message, command="", key=""):
        """log and warn if forbidden action over SSH"""
        audit.log_command_event(
            self.conf,
            command,
            allowed=False,
            reason=f"forbidden over SSH: {message}",
        )
        if key == "scp":
            self.log.critical(
                messages.get_message(self.conf, "forbidden_scp_over_ssh", message=message)
            )
            self.log.error(f"lshell: SCP command: {command}")
        else:
            self.log.critical(
                messages.get_message(
                    self.conf,
                    "forbidden_command_over_ssh",
                    message=message,
                    command=command,
                )
            )
        sys.stderr.write(messages.get_message(self.conf, "incident_reported") + "\n")
        self.log.error("Exited")
        sys.exit(1)

    def run_script_mode(self, script):
        """Process commands from a script."""
        with open(script, "r") as script_file:
            for line in script_file:
                line = line.strip()
                if line:
                    line = self.precmd(line)
                    stop = self.onecmd(line)
                    stop = self.postcmd(stop, line)
                    if stop:
                        sys.exit(1)

    def _configure_readline(self):
        """Initialize readline history, completion, and safe history search."""
        try:
            readline.read_history_file(self.conf["history_file"])
        except IOError:
            # if history file does not exist
            try:
                open(self.conf["history_file"], "w").close()
                readline.read_history_file(self.conf["history_file"])
            except IOError:
                pass
        readline.set_history_length(self.conf["history_size"])
        readline.set_completer_delims(readline.get_completer_delims().replace("-", ""))
        self.old_completer = readline.get_completer()
        readline.set_completer(self.complete)
        readline.parse_and_bind(self.completekey + ": complete")
        if hasattr(readline, "set_completion_display_matches_hook"):
            global _ACTIVE_COMPLETION_SHELL
            _ACTIVE_COMPLETION_SHELL = self
            readline.set_completion_display_matches_hook(_display_completion_matches)
        for binding in READLINE_INCREMENTAL_SEARCH_BINDINGS:
            readline.parse_and_bind(binding)
        if not _bind_custom_history_search(self):
            for binding in READLINE_HISTORY_SEARCH_BINDINGS:
                readline.parse_and_bind(binding)

    def reset_history_search_state(self):
        """Clear state used for prefix history navigation on arrow keys."""
        self.history_search_state = {
            "prefix": None,
            "matches": [],
            "index": None,
            "original_line": "",
        }

    def _collect_history_prefix_matches(self, prefix):
        """Return unique history entries matching prefix, newest first."""
        seen = set()
        matches = []
        history_length = readline.get_current_history_length()
        for index in range(history_length, 0, -1):
            entry = readline.get_history_item(index)
            if not entry or not entry.startswith(prefix) or entry in seen:
                continue
            seen.add(entry)
            matches.append(entry)
        return matches

    def history_search(self, backward):
        """Navigate unique history entries that match the current line prefix."""
        current_line = readline.get_line_buffer()
        state = self.history_search_state
        active_match = None
        if state["matches"] and state["index"] is not None:
            active_match = state["matches"][state["index"]]

        continuing = current_line in (state["original_line"], active_match)
        if not continuing:
            if not backward:
                self.reset_history_search_state()
                return 0

            prefix = current_line[: _readline_char_point(current_line)]
            matches = self._collect_history_prefix_matches(prefix)
            if not matches:
                self.reset_history_search_state()
                return 0

            self.history_search_state = {
                "prefix": prefix,
                "matches": matches,
                "index": 0,
                "original_line": current_line,
            }
            _replace_readline_buffer(matches[0])
            return 0

        if backward:
            if state["index"] < len(state["matches"]) - 1:
                state["index"] += 1
                _replace_readline_buffer(state["matches"][state["index"]])
            return 0

        if state["index"] > 0:
            state["index"] -= 1
            _replace_readline_buffer(state["matches"][state["index"]])
            return 0

        _replace_readline_buffer(state["original_line"])
        self.reset_history_search_state()
        return 0

    def _completion_context_label(self, compfunc):
        """Return a user-facing label for the current completion source."""
        if compfunc == completion.complete_sudo:
            return "Allowed sudo commands"
        if compfunc == completion.complete_change_dir:
            return "Allowed directories"
        if compfunc == completion.complete_list_dir:
            return "Allowed paths"
        if compfunc == completion.completenames:
            return "Allowed commands"
        return "Allowed completions"

    def display_completion_matches(self, substitution, matches, longest_match_length):
        """Show a compact header and sorted completion candidates."""
        del substitution

        rendered_matches = sorted(dict.fromkeys(matches), key=lambda item: item.lower())
        if not rendered_matches:
            return

        terminal_width = shutil.get_terminal_size((80, 24)).columns
        column_width = max(longest_match_length + 2, 2)
        columns = max(1, terminal_width // column_width)
        lines = []
        for start in range(0, len(rendered_matches), columns):
            row = rendered_matches[start : start + columns]
            if len(row) == 1:
                lines.append(row[0])
                continue
            lines.append("".join(item.ljust(column_width) for item in row).rstrip())

        sys.stdout.write(
            f"\n[{self.completion_display_context}: {len(rendered_matches)}]\n"
        )
        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()
        readline_lib = _get_readline_library()
        if readline_lib is not None:
            readline_lib.rl_redisplay()

    def _prepare_history_before_write(self):
        """Apply persisted-history policies before writing the history file."""
        history_utils.prepare_history_for_write()

    def _write_history_file(self):
        """Persist readline history after applying lshell history policies."""
        self._prepare_history_before_write()
        readline.write_history_file(self.conf["history_file"])

    def cmdloop(self, intro=None):
        """Repeatedly issue a prompt, accept input, parse an initial prefix
        off the received input, and dispatch to action methods, passing them
        the remainder of the line as argument.
        """

        if self.conf.get("script"):
            self.run_script_mode(self.conf["script"])
            return

        self.preloop()
        if self.use_rawinput and self.completekey:
            self._configure_readline()
        try:
            if self.intro and isinstance(self.intro, str):
                self.stdout.write(f"{self.intro}\n")
            if self.conf["login_script"]:
                utils.cmd_parse_execute(self.conf["login_script"], shell_context=self)
            self.prompt2 = "> "  # PS2 prompt
            # for long commands, a user may escape the new line
            # by giving a bash like '\' character at the end of
            # the line. cmdloop() needs to recognize that and
            # create an appended line before sending it to onecmd()
            partial_line = ""
            stop = None
            while not stop:
                try:
                    # Check background jobs after each command
                    builtincmd.check_background_jobs()
                    line_from_eof = False
                    line_from_readline = False
                    if self.cmdqueue:
                        line = self.cmdqueue.pop(0)
                    else:
                        if self.use_rawinput:
                            global _ACTIVE_HISTORY_SEARCH_SHELL
                            _ACTIVE_HISTORY_SEARCH_SHELL = self
                            self.reset_history_search_state()
                            line_from_readline = True
                            try:
                                line = input(self.conf["promptprint"])
                            except EOFError:
                                line = "EOF"
                                line_from_eof = True
                            except KeyboardInterrupt:
                                self.stdout.write("\n")
                                if partial_line:
                                    partial_line = ""
                                    self.conf["promptprint"] = utils.updateprompt(
                                        os.getcwd(), self.conf
                                    )
                                continue
                        else:
                            self.stdout.write(self.conf["promptprint"])
                            self.stdout.flush()
                            line = self.stdin.readline()
                            if not line:
                                line = "EOF"
                            else:
                                # chop \n
                                line = line[:-1]
                        had_partial_line = bool(partial_line)
                        if len(line) > 1 and line.startswith("\\"):
                            # implying previous partial line
                            line = line[:1].replace("\\", "", 1)
                        if partial_line:
                            line = partial_line + line
                        if line.endswith("\\"):
                            # continuation character. First partial line.
                            # We shall expect the command to continue in
                            # a new line. Change to bash like PS2 prompt to
                            # indicate this continuation to the user
                            partial_line = line.strip("\\")
                            self.conf["promptprint"] = self.prompt2  # switching to PS2
                            continue
                        elif line.count('"') % 2 != 0 or line.count("'") % 2 != 0:
                            # unclosed quotes detected
                            partial_line = line
                            self.conf["promptprint"] = self.prompt2  # switching to PS2
                            continue
                        partial_line = ""
                        self.conf["promptprint"] = utils.updateprompt(
                            os.getcwd(), self.conf
                        )
                        if line_from_readline and not had_partial_line and not line_from_eof:
                            history_utils.prepare_latest_history_entry(line)
                    line = self.precmd(line)
                    stop = self.onecmd(line)
                    stop = self.postcmd(stop, line)
                except KeyboardInterrupt:
                    # Keep prompt handling local to cmdloop even when Ctrl+C
                    # races outside input() (e.g. background-job checks).
                    self.stdout.write("\n")
                    self.stdout.flush()
                    partial_line = ""
                    self.conf["promptprint"] = utils.updateprompt(
                        os.getcwd(), self.conf
                    )
                    continue
            self.postloop()
        finally:
            if self.use_rawinput and self.completekey:
                try:
                    readline.set_completer_delims(
                        readline.get_completer_delims().replace("-", "")
                    )
                    readline.set_completer(self.old_completer)
                    if hasattr(readline, "set_completion_display_matches_hook"):
                        readline.set_completion_display_matches_hook(None)
                except ImportError:
                    pass
            try:
                self._write_history_file()
            except IOError:
                self.log.error(
                    f"WARN: couldn't write history to file {self.conf['history_file']}\n"
                )

    def complete(self, text, state):
        """Return the next possible completion for 'text'.
        If a command has not been entered, then complete against command list.
        Otherwise try to call complete_<command> to get list of completions.
        """
        if state == 0:
            origline = readline.get_line_buffer()
            line = origline.lstrip()
            # in case '|', ';', '&' used, take last part of line to complete
            line = re.split(r"&|\||;", line)[-1].lstrip()
            stripped = len(origline) - len(line)
            begidx = readline.get_begidx() - stripped
            endidx = readline.get_endidx() - stripped
            # complete with sudo allowed commands
            command = line.split(" ")[0]
            if command == "sudo" and len(line.split(" ")) <= 2:
                compfunc = completion.complete_sudo
            # complete with directories
            elif command == "cd":
                compfunc = completion.complete_change_dir
            # complete local relative commands from allowed entries like ./foo
            elif command.startswith("./"):
                compfunc = completion.completenames
            # complete with files and directories
            elif (
                len(line.split(" ")) > 1 and line.split(" ")[0] in self.conf["allowed"]
            ):
                compfunc = completion.complete_list_dir
            elif begidx > 0:
                cmd, args, _ = self.parseline(line)
                if cmd == "":
                    compfunc = completion.completedefault
                else:
                    try:
                        compfunc = getattr(self, "complete_" + cmd)
                    except AttributeError:
                        compfunc = (
                            completion.completenames
                            if cmd.startswith("./")
                            else completion.completedefault
                        )
                    # exception called when using './' completion
                    except IndexError:
                        compfunc = completion.completenames
                    # exception called when using './' completion
                    except TypeError:
                        compfunc = completion.completenames
            else:
                # call the lshell allowed commands completion
                compfunc = completion.completenames

            self.completion_display_context = self._completion_context_label(compfunc)
            matches = compfunc(self.conf, text, line, begidx, endidx)
            self.completion_matches = sorted(
                dict.fromkeys(matches), key=lambda item: item.lower()
            )
        try:
            return self.completion_matches[state]
        except IndexError:
            return None

    def default(self, line):
        """This method overrides the original default method.
        It was originally used to warn when an unknown command was entered
        (e.g. *** Unknown syntax: blabla).
        It has been implemented in the __getattr__ method.
        So it has no use here. Its output is now empty.
        """
        self.stdout.write("")

    def completenames(self, text, line, *ignored):
        """Override the original completenames method."""
        return completion.completenames(self.conf, text, line, *ignored)

    def onecmd(self, line):
        """This method overrides the original onecmd method, to put the cmd,
        arg and line variables in class global variables: self.g_cmd,
        self.g_arg and self.g_line.
        Those variables are then used by the __getattr__ method
        """
        cmd, arg, line = self.parseline(line)
        self.g_cmd, self.g_arg, self.g_line = [cmd, arg, line]
        if not line:
            return self.emptyline()
        if cmd is None or cmd == "":
            stripped = line.lstrip()
            # Keep comment/shebang lines ignored (script compatibility),
            # but validate tokenization failures such as leading operators.
            if stripped and not stripped.startswith("#"):
                try:
                    getattr(self, "do___lshell_dispatch")
                except AttributeError:
                    pass
            return self.default(line)
        self.lastcmd = line
        try:
            func = getattr(self, "do_" + cmd)
        except AttributeError:
            return self.default(line)
        return func(arg)

    def emptyline(self):
        """This method overrides the original emptyline method, so it doesn't
        repeat the last command if last command was empty.
        I just found this annoying..
        """
        if self.lastcmd:
            return 0

    def do_help(self, arg=None):
        """This method overrides the original do_help method.
        Instead of printing out the that are documented or not, it returns the
        list of allowed commands when '?' or 'help' is entered.
        Of course, it doesn't override the help function: any help_* method
        will be called (e.g. help_help(self) )
        """

        # Get list of allowed commands, remove duplicate 'help' then sort
        list_tmp = list(dict.fromkeys(self.completenames("", "")).keys())
        list_tmp.sort()
        self.columnize(list_tmp)

    def do_EOF(self, arg=None):  # pylint: disable=invalid-name
        """Handle Ctrl+D / EOF exactly like exit."""
        return self.do_exit(arg)

    def do_quit(self, arg=None):
        """Handle quit exactly like exit."""
        return self.do_exit(arg)

    def do_lshow(self, arg=None):
        """Show current session policy values and optional command decision."""
        command_line = (arg or "").strip() or None
        # `lshow` runs inside an active shell session. Use the in-memory runtime
        # policy so command-line overrides (for example --allowed/--sudo_commands)
        # are reflected exactly as enforced in the current session.
        result = {"policy": self.conf}

        decision = None
        if command_line:
            decision = policy_mode.policy_command_decision(command_line, self.conf)

        policy_mode.print_user_view(result, command_line, decision)
        if decision is None:
            return 0
        return 0 if decision["allowed"] else 2

    def do_policy_show(self, arg=None):
        """Compatibility shim for legacy internal command name."""
        return self.do_lshow(arg)

    def do_exit(self, arg=None):
        """This method overrides the original do_exit method."""
        # Check for background jobs
        if hasattr(builtincmd, "BACKGROUND_JOBS") and builtincmd.BACKGROUND_JOBS:
            # Filter out completed jobs
            active_jobs = []
            for job_id, job in enumerate(builtincmd.BACKGROUND_JOBS, start=1):
                if job.poll() is None:
                    active_jobs.append((job_id, job))

            if active_jobs and self.kill_jobs_at_exit:
                for job_id, job in active_jobs:
                    try:
                        os.killpg(os.getpgid(job.pid), signal.SIGKILL)
                        builtincmd.BACKGROUND_JOBS.pop(job_id - 1)
                    except Exception as exception:
                        print(f"Failed to stop job [{job.pid}]: {exception}")
            else:
                # Warn the user and list the stopped jobs
                print(
                    "There are stopped jobs. Use 'jobs' to list them or 'exit' "
                    "to stop them and exit shell."
                )
                self.kill_jobs_at_exit = True
                return  # Return to the shell prompt instead of exiting

        # Proceed with exit if no active jobs or after stopping them
        if self.g_cmd == "EOF":
            self.stdout.write("\n")

        if self.conf["disable_exit"] != 1:
            sys.exit(0)

    def mytimer(self, timeout):
        """This function is kicks you out the the lshell after
        the 'timer' variable expires. 'timer' is set in seconds.
        """
        # set timer
        signal.signal(signal.SIGALRM, self._timererror)
        signal.alarm(timeout)

    def _timererror(self, signum, frame):
        raise LshellTimeOut("lshell timer timeout")


class LshellTimeOut(Exception):
    """Custom exception used for timer timeout"""

    def __init__(self, value="Timed Out"):
        self.value = value

    def __str__(self):
        return repr(self.value)
