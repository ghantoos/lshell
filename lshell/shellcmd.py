"""This module contains the main class of lshell, it is the class that is
responsible for the command line interface. It inherits from the cmd.Cmd class
from the Python standard library. It offers the default methods to add
security checks, logging, etc.
"""

import cmd
import sys
import os
import re
import signal
import readline

# import lshell specifics
from lshell.checkconfig import CheckConfig
from lshell import utils
from lshell import builtincmd
from lshell import sec
from lshell import completion


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

        # Expand only the full input line; command/arg are derived from it.
        self.g_cmd = utils.expand_vars_quoted(self.g_cmd)
        self.g_line = utils.expand_vars_quoted(self.g_line)
        self.g_arg = utils.expand_vars_quoted(self.g_arg)

        # in case the configuration file has been modified, reload it
        if self.conf["config_mtime"] != os.path.getmtime(self.conf["configfile"]):
            self.conf = CheckConfig(
                ["--config", self.conf["configfile"]], refresh=1
            ).returnconf()
            self.conf["promptprint"] = utils.updateprompt(os.getcwd(), self.conf)
            self.log = self.conf["logpath"]

        if self.g_cmd in ["quit", "exit", "EOF"]:
            self.do_exit()

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

        def _aliases_for_ssh_command():
            aliases = self.conf["aliases"]
            if self.conf.get("_auto_ls_alias") and isinstance(aliases, dict):
                aliases = dict(aliases)
                aliases.pop("ls", None)
            return aliases

        if "ssh" in self.conf:
            if "SSH_CLIENT" in os.environ and "SSH_TTY" not in os.environ:
                # check if sftp is requested and allowed
                if "sftp-server" in self.conf["ssh"]:
                    if self.conf["sftp"] == 1:
                        self.log.error("SFTP connect")
                        retcode = utils.cmd_parse_execute(
                            self.conf["ssh"], shell_context=self
                        )
                        self.log.error("SFTP disconnect")
                        sys.exit(retcode)
                    else:
                        self.log.error("*** forbidden SFTP connection")
                        sys.exit(1)

                ret_check_path, self.conf = sec.check_path(
                    self.conf["ssh"], self.conf, ssh=1
                )
                if ret_check_path == 1:
                    self.ssh_warn("path over SSH", self.conf["ssh"])

                # check if scp is requested and allowed
                if self.conf["ssh"].startswith("scp "):
                    if self.conf["scp"] == 1 or "scp" in self.conf["overssh"]:
                        if " -f " in self.conf["ssh"]:
                            # case scp download is allowed
                            if self.conf["scp_download"]:
                                self.log.error(f'SCP: GET "{self.conf["ssh"]}"')
                            # case scp download is forbidden
                            else:
                                self.log.error(
                                    f'SCP: download forbidden: "{self.conf["ssh"]}"'
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
                                sys.exit(1)
                        retcode = utils.cmd_parse_execute(
                            self.conf["ssh"], shell_context=self
                        )
                        self.log.error("SCP disconnect")
                        sys.exit(retcode)
                    else:
                        self.ssh_warn("SCP connection", self.conf["ssh"], "scp")

                # check if command is in allowed overssh commands
                elif self.conf["ssh"]:
                    # replace aliases
                    self.conf["ssh"] = utils.get_aliases(
                        self.conf["ssh"], _aliases_for_ssh_command()
                    )
                    # if command is not "secure", exit
                    ret_check_secure, self.conf = sec.check_secure(
                        self.conf["ssh"], self.conf, strict=1, ssh=1
                    )
                    if ret_check_secure:
                        self.ssh_warn("char/command over SSH", self.conf["ssh"])
                        sys.exit(1)
                    else:
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
        if key == "scp":
            self.log.critical(f"lshell: forbidden {message}")
            self.log.error(f"lshell: SCP command: {command}")
        else:
            self.log.critical(f'lshell: forbidden {message}: "{command}"')
        sys.stderr.write("This incident has been reported.\n")
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
            try:
                readline.read_history_file(self.conf["history_file"])
                readline.set_history_length(self.conf["history_size"])
            except IOError:
                # if history file does not exist
                try:
                    open(self.conf["history_file"], "w").close()
                    readline.read_history_file(self.conf["history_file"])
                except IOError:
                    pass
            readline.set_completer_delims(
                readline.get_completer_delims().replace("-", "")
            )
            self.old_completer = readline.get_completer()
            readline.set_completer(self.complete)
            readline.parse_and_bind(self.completekey + ": complete")
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
                # Check background jobs after each command
                builtincmd.check_background_jobs()
                if self.cmdqueue:
                    line = self.cmdqueue.pop(0)
                else:
                    if self.use_rawinput:
                        try:
                            line = input(self.conf["promptprint"])
                        except EOFError:
                            line = "EOF"
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
                line = self.precmd(line)
                stop = self.onecmd(line)
                stop = self.postcmd(stop, line)
            self.postloop()
        finally:
            if self.use_rawinput and self.completekey:
                try:
                    readline.set_completer_delims(
                        readline.get_completer_delims().replace("-", "")
                    )
                    readline.set_completer(self.old_completer)
                except ImportError:
                    pass
            try:
                readline.write_history_file(self.conf["history_file"])
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

            self.completion_matches = compfunc(self.conf, text, line, begidx, endidx)
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
        if cmd is None:
            return self.default(line)
        self.lastcmd = line
        if cmd == "":
            return self.default(line)
        else:
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
