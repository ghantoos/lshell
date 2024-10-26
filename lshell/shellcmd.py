""" This module contains the main class of lshell, it is the class that is
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

        self.args = args
        self.conf = userconf
        self.log = self.conf["logpath"]

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

        # initialize return code
        self.retcode = 0

    def __getattr__(self, attr):
        """This method actually takes care of all the called method that are
        not resolved (i.e not existing methods). It actually will simulate
        the existence of any method    entered in the 'allowed' variable list.

        e.g. You just have to add 'uname' in list of allowed commands in
        the 'allowed' variable, and lshell will react as if you had
        added a do_uname in the ShellCmd class!
        """

        # expand environment variables in command line
        self.g_cmd = os.path.expandvars(self.g_cmd)
        self.g_line = os.path.expandvars(self.g_line)
        self.g_arg = os.path.expandvars(self.g_arg)

        # in case the configuration file has been modified, reload it
        if self.conf["config_mtime"] != os.path.getmtime(self.conf["configfile"]):
            self.conf = CheckConfig(
                ["--config", self.conf["configfile"]], refresh=1
            ).returnconf()
            self.conf["promptprint"] = utils.updateprompt(os.getcwd(), self.conf)
            self.log = self.conf["logpath"]

        self.check_scp_sftp()

        if self.g_cmd in ["quit", "exit", "EOF"]:
            self.do_exit()

        # check that commands/chars present in line are allowed/secure
        ret_check_secure, self.conf = sec.check_secure(
            self.g_line, self.conf, strict=self.conf["strict"]
        )
        if ret_check_secure == 1:
            # see http://tldp.org/LDP/abs/html/exitcodes.html
            self.retcode = 126
            return object.__getattribute__(self, attr)

        # check that path present in line are allowed/secure
        ret_check_path, self.conf = sec.check_path(
            self.g_line, self.conf, strict=self.conf["strict"]
        )
        if ret_check_path == 1:
            # see http://tldp.org/LDP/abs/html/exitcodes.html
            self.retcode = 126
            # in case request was sent by WinSCP, return error code has to be
            # sent via an specific echo command
            if self.conf["winscp"] and re.search(
                "WinSCP: this is end-of-file", self.g_line
            ):
                utils.exec_cmd(f'echo "WinSCP: this is end-of-file: {self.retcode}"')
            return object.__getattribute__(self, attr)
        if self.g_cmd in self.conf["allowed"] or self.g_line in self.conf["allowed"]:
            if self.conf["timer"] > 0:
                self.mytimer(0)
            self.g_arg = re.sub("^~$|^~/", f"{self.conf['home_path']}/", self.g_arg)
            self.g_arg = re.sub(" ~/", f" {self.conf['home_path']}/", self.g_arg)
            # replace previous command exit code
            # in case multiple commands (using separators), only replace first
            # command. Regex replaces all occurrences of $?, before ;,&,|
            if re.search(r"[;&\|]", self.g_line):
                p = re.compile(r"(\s|^)(\$\?)([\s|$]?[;&|].*)")
            else:
                p = re.compile(r"(\s|^)(\$\?)(\s|$)")
            self.g_line = p.sub(rf" {self.retcode} \3", self.g_line)

            if isinstance(self.conf["aliases"], dict):
                self.g_line = utils.get_aliases(self.g_line, self.conf["aliases"])

            self.log.info(f'CMD: "{self.g_line}"')

            if self.g_cmd == "cd":
                # split cd <dir> and rest of command
                cmd_split = re.split(r";|&&|&|\|\||\|", self.g_line, 1)
                # in case the are commands following cd, first change the
                # directory, then execute the command
                if len(cmd_split) == 2:
                    directory, command = cmd_split
                    # only keep cd's argument
                    directory = directory.split("cd", 1)[1].strip()
                    # change directory then, if success, execute the rest of
                    # the cmd line
                    self.retcode, self.conf = builtincmd.cd(directory, self.conf)

                    if self.retcode == 0:
                        cmd_split = re.split(r";|&&|&|\|\||\|", command)
                        for command in cmd_split:
                            self.retcode = utils.cmd_parse_execute(command, self)
                else:
                    # set directory to command line argument and change dir
                    directory = self.g_arg
                    self.retcode, self.conf = builtincmd.cd(directory, self.conf)

            # built-in lpath function: list all allowed path
            elif self.g_cmd == "lpath":
                self.retcode = builtincmd.lpath(self.conf)
            # built-in lsudo function: list all allowed sudo commands
            elif self.g_cmd == "lsudo":
                self.retcode = builtincmd.lsudo(self.conf)
            # built-in history function: print command history
            elif self.g_cmd == "history":
                self.retcode = builtincmd.history(self.conf, self.log)
            # built-in export function
            elif self.g_cmd == "export":
                self.retcode, var = builtincmd.export(self.g_line)
                if self.retcode == 1:
                    self.log.critical(f"** forbidden environment variable '{var}'")
            # case 'cd' is in an alias e.g. {'toto':'cd /var/tmp'}
            elif self.g_line[0:2] == "cd":
                self.g_cmd = self.g_line.split()[0]
                directory = " ".join(self.g_line.split()[1:])
                self.retcode, self.conf = builtincmd.cd(directory, self.conf)

            else:
                self.retcode = utils.cmd_parse_execute(self.g_line, self)

        elif self.g_cmd not in ["", "?", "help", None]:
            self.log.warn(f'INFO: unknown syntax -> "{self.g_line}"')
            self.stderr.write(f"*** unknown syntax: {self.g_cmd}\n")
        self.g_cmd, self.g_arg, self.g_line = ["", "", ""]
        if self.conf["timer"] > 0:
            self.mytimer(self.conf["timer"])
        return object.__getattribute__(self, attr)

    def check_scp_sftp(self):
        """This method checks if the user is trying to SCP a file onto the
        server. If this is the case, it checks if the user is allowed to use
        SCP or not, and    acts as requested. : )
        """

        if "ssh" in self.conf:
            if "SSH_CLIENT" in os.environ and "SSH_TTY" not in os.environ:
                # check if sftp is requested and allowed
                if "sftp-server" in self.conf["ssh"]:
                    if self.conf["sftp"] == 1:
                        self.log.error("SFTP connect")
                        retcode = utils.cmd_parse_execute(self.conf["ssh"])
                        self.log.error("SFTP disconnect")
                        sys.exit(retcode)
                    else:
                        self.log.error("*** forbidden SFTP connection")
                        sys.exit(1)

                # initialize cli session
                cli = ShellCmd(self.conf, None, None, None, None, self.conf["ssh"])
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
                        retcode = utils.cmd_parse_execute(self.conf["ssh"], cli)
                        self.log.error("SCP disconnect")
                        sys.exit(retcode)
                    else:
                        self.ssh_warn("SCP connection", self.conf["ssh"], "scp")

                # check if command is in allowed overssh commands
                elif self.conf["ssh"]:
                    # replace aliases
                    self.conf["ssh"] = utils.get_aliases(
                        self.conf["ssh"], self.conf["aliases"]
                    )
                    # if command is not "secure", exit
                    ret_check_secure, self.conf = sec.check_secure(
                        self.conf["ssh"], self.conf, strict=1, ssh=1
                    )
                    if ret_check_secure:
                        self.ssh_warn("char/command over SSH", self.conf["ssh"])
                    # else
                    self.log.error(f'Over SSH: "{self.conf["ssh"]}"')
                    # if command is "help"
                    if self.conf["ssh"] == "help":
                        cli.do_help(None)
                        retcode = 0
                    else:
                        retcode = utils.cmd_parse_execute(self.conf["ssh"], cli)
                    self.log.error("Exited")
                    sys.exit(retcode)

                # else warn and log
                else:
                    self.ssh_warn("command over SSH", self.conf["ssh"])

            else:
                # case of shell escapes
                self.ssh_warn("shell escape", self.conf["ssh"])

    def ssh_warn(self, message, command="", key=""):
        """log and warn if forbidden action over SSH"""
        if key == "scp":
            self.log.critical(f"*** forbidden {message}")
            self.log.error(f"*** SCP command: {command}")
        else:
            self.log.critical(f'*** forbidden {message}: "{command}"')
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
                utils.cmd_parse_execute(self.conf["login_script"], self)
            stop = None
            while not stop:
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
                            line = ""
                    else:
                        self.stdout.write(self.conf["promptprint"])
                        self.stdout.flush()
                        line = self.stdin.readline()
                        if not line:
                            line = "EOF"
                        else:
                            # chop \n
                            line = line[:-1]
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
            if line.split(" ")[0] == "sudo" and len(line.split(" ")) <= 2:
                compfunc = self.completesudo
            # complete next argument with file or directory
            elif (
                len(line.split(" ")) > 1 and line.split(" ")[0] in self.conf["allowed"]
            ):
                compfunc = self.completechdir
            elif begidx > 0:
                cmd, args, _ = self.parseline(line)
                if cmd == "":
                    compfunc = self.completedefault
                else:
                    try:
                        compfunc = getattr(self, "complete_" + cmd)
                    except AttributeError:
                        compfunc = self.completedefault
                    # exception called when using './' completion
                    except IndexError:
                        compfunc = self.completenames
                    # exception called when using './' completion
                    except TypeError:
                        compfunc = self.completenames
            else:
                # call the lshell allowed commands completion
                compfunc = self.completenames

            self.completion_matches = compfunc(text, line, begidx, endidx)
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
        """This method overrides the original completenames method to overload
        it's output with the command available in the 'allowed' variable
        This is useful when typing 'tab-tab' in the command prompt
        """
        commands = self.conf["allowed"]
        if line.startswith("./"):
            return [cmd[2:] for cmd in commands if cmd.startswith(f"./{text}")]
        else:
            return [cmd for cmd in commands if cmd.startswith(text)]

    def completesudo(self, text, line, begidx, endidx):
        """complete sudo command"""
        return [a for a in self.conf["sudo_commands"] if a.startswith(text)]

    def completechdir(self, text, line, begidx, endidx):
        """complete directories"""
        toreturn = []
        tocomplete = line.split()[-1]
        # replace "~" with home path
        tocomplete = re.sub("^~", self.conf["home_path"], tocomplete)
        try:
            directory = os.path.realpath(tocomplete)
        except OSError:
            directory = os.getcwd()

        if not os.path.isdir(directory):
            directory = directory.rsplit("/", 1)[0]
            if directory == "":
                directory = "/"
            if not os.path.isdir(directory):
                directory = os.getcwd()

        ret_check_path, self.conf = sec.check_path(directory, self.conf, completion=1)
        if ret_check_path == 0:
            for instance in os.listdir(directory):
                if os.path.isdir(os.path.join(directory, instance)):
                    instance = instance + "/"
                else:
                    instance = instance + " "
                if instance.startswith("."):
                    if text.startswith("."):
                        toreturn.append(instance)
                    else:
                        pass
                else:
                    toreturn.append(instance)
            return [a for a in toreturn if a.startswith(text)]
        else:
            return None

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
        self.log.error("Exited")
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
