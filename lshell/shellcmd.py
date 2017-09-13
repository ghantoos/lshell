#
#  Limited command Shell (lshell)
#
#  Copyright (C) 2008-2013 Ignace Mouzannar (ghantoos) <ghantoos@ghantoos.org>
#
#  This file is part of lshell
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.

import cmd
import sys
import os
import re
import signal
import readline

# import lshell specifics
from lshell import utils
from lshell import builtins
from lshell import sec


class ShellCmd(cmd.Cmd, object):
    """ Main lshell CLI class
    """

    def __init__(self, userconf, args, stdin=None, stdout=None, stderr=None,
                 g_cmd=None, g_line=None):
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
        self.log = self.conf['logpath']

        # Set timer
        if self.conf['timer'] > 0:
            self.mytimer(self.conf['timer'])
        self.identchars = self.identchars + '+./-'
        self.log.error('Logged in')
        cmd.Cmd.__init__(self)

        # set prompt
        self.conf['promptprint'] = utils.updateprompt(os.getcwd(), self.conf)

        self.intro = self.conf['intro']

        # initialize oldpwd variable to home directory
        self.conf['oldpwd'] = self.conf['home_path']

        # initialize cli variables
        self.g_cmd = g_cmd
        self.g_line = g_line

        # initialize return code
        self.retcode = 0

    def __getattr__(self, attr):
        """ This method actually takes care of all the called method that are
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
        if self.conf['config_mtime'] != os.path.getmtime(
                self.conf['configfile']):
            from lshell.checkconfig import CheckConfig
            self.conf = CheckConfig(['--config', self.conf['configfile']],
                                    refresh=1).returnconf()
            self.conf['promptprint'] = utils.updateprompt(os.getcwd(),
                                                          self.conf)
            self.log = self.conf['logpath']

        if self.g_cmd in ['quit', 'exit', 'EOF']:
            self.log.error('Exited')
            if self.g_cmd == 'EOF':
                self.stdout.write('\n')
            if self.conf['disable_exit'] != 1:
                sys.exit(0)

        # check that commands/chars present in line are allowed/secure
        ret_check_secure, self.conf = sec.check_secure(
            self.g_line,
            self.conf,
            strict=self.conf['strict'])
        if ret_check_secure == 1:
            # see http://tldp.org/LDP/abs/html/exitcodes.html
            self.retcode = 126
            return object.__getattribute__(self, attr)

        # check that path present in line are allowed/secure
        ret_check_path, self.conf = sec.check_path(self.g_line,
                                                   self.conf,
                                                   strict=self.conf['strict'])
        if ret_check_path == 1:
            # see http://tldp.org/LDP/abs/html/exitcodes.html
            self.retcode = 126
            # in case request was sent by WinSCP, return error code has to be
            # sent via an specific echo command
            if self.conf['winscp'] and re.search('WinSCP: this is end-of-file',
                                                 self.g_line):
                utils.exec_cmd('echo "WinSCP: this is end-of-file: %s"'
                               % self.retcode)
            return object.__getattribute__(self, attr)
        if self.g_cmd in self.conf['allowed']:
            if self.conf['timer'] > 0:
                self.mytimer(0)
            self.g_arg = re.sub('^~$|^~/', '%s/' % self.conf['home_path'],
                                self.g_arg)
            self.g_arg = re.sub(' ~/', ' %s/' % self.conf['home_path'],
                                self.g_arg)
            # replace previous command exit code
            # in case multiple commands (using separators), only replace first
            # command. Regex replaces all occurrences of $?, before ;,&,|
            if re.search('[;&\|]', self.g_line):
                p = re.compile("(\s|^)(\$\?)([\s|$]?[;&|].*)")
            else:
                p = re.compile("(\s|^)(\$\?)(\s|$)")
            self.g_line = p.sub(r' %s \3' % self.retcode, self.g_line)

            if type(self.conf['aliases']) == dict:
                self.g_line = utils.get_aliases(self.g_line,
                                                self.conf['aliases'])

            self.log.info('CMD: "%s"' % self.g_line)

            if self.g_cmd == 'cd':
                # split cd <dir> and rest of command
                cmd_split = re.split(';|&&|&|\|\||\|', self.g_line, 1)
                # in case the are commands following cd, first change the
                # directory, then execute the command
                if len(cmd_split) == 2:
                    directory, command = cmd_split
                    # only keep cd's argument
                    directory = directory.split('cd', 1)[1].strip()
                    # change directory then, if success, execute the rest of
                    # the cmd line
                    self.retcode, self.conf = builtins.cd(directory,
                                                          self.conf)

                    if self.retcode == 0:
                        self.retcode = utils.exec_cmd(command)
                else:
                    # set directory to command line argument and change dir
                    directory = self.g_arg
                    self.retcode, self.conf = builtins.cd(directory,
                                                          self.conf)

            # built-in lpath function: list all allowed path
            elif self.g_cmd == 'lpath':
                self.retcode = builtins.lpath(self.conf)
            # built-in lsudo function: list all allowed sudo commands
            elif self.g_cmd == 'lsudo':
                self.retcode = builtins.lsudo(self.conf)
            # built-in history function: print command history
            elif self.g_cmd == 'history':
                self.retcode = builtins.history(self.conf, self.log)
            # built-in export function
            elif self.g_cmd == 'export':
                self.retcode, var = builtins.export(self.g_line)
                if self.retcode == 1:
                    self.log.critical("** forbidden environment variable '%s'"
                                      % var)
            # case 'cd' is in an alias e.g. {'toto':'cd /var/tmp'}
            elif self.g_line[0:2] == 'cd':
                self.g_cmd = self.g_line.split()[0]
                directory = ' '.join(self.g_line.split()[1:])
                self.retcode, self.conf = builtins.cd(directory,
                                                      self.conf)

            else:
                self.retcode = utils.exec_cmd(self.g_line)

        elif self.g_cmd not in ['', '?', 'help', None]:
            self.log.warn('INFO: unknown syntax -> "%s"' % self.g_line)
            self.stderr.write('*** unknown syntax: %s\n' % self.g_cmd)
        self.g_cmd, self.g_arg, self.g_line = ['', '', '']
        if self.conf['timer'] > 0:
            self.mytimer(self.conf['timer'])
        return object.__getattribute__(self, attr)

    def cmdloop(self, intro=None):
        """Repeatedly issue a prompt, accept input, parse an initial prefix
        off the received input, and dispatch to action methods, passing them
        the remainder of the line as argument.
        """

        self.preloop()
        if self.use_rawinput and self.completekey:
            try:
                readline.read_history_file(self.conf['history_file'])
                readline.set_history_length(self.conf['history_size'])
            except IOError:
                # if history file does not exist
                try:
                    open(self.conf['history_file'], 'w').close()
                    readline.read_history_file(self.conf['history_file'])
                except IOError:
                    pass
            readline.set_completer_delims(
                readline.get_completer_delims().replace('-', ''))
            self.old_completer = readline.get_completer()
            readline.set_completer(self.complete)
            readline.parse_and_bind(self.completekey + ": complete")
        try:
            if self.intro and isinstance(self.intro, str):
                self.stdout.write("%s\n" % self.intro)
            if self.conf['login_script']:
                utils.exec_cmd(self.conf['login_script'])
            stop = None
            while not stop:
                if self.cmdqueue:
                    line = self.cmdqueue.pop(0)
                else:
                    if self.use_rawinput:
                        try:
                            # raw_input renamed as input in py3
                            try:
                                line = raw_input(self.conf['promptprint'])
                            except NameError:
                                line = input(self.conf['promptprint'])
                        except EOFError:
                            line = 'EOF'
                        except KeyboardInterrupt:
                            self.stdout.write('\n')
                            line = ''
                    else:
                        self.stdout.write(self.conf['promptprint'])
                        self.stdout.flush()
                        line = self.stdin.readline()
                        if not len(line):
                            line = 'EOF'
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
                        readline.get_completer_delims().replace('-', ''))
                    readline.set_completer(self.old_completer)
                except ImportError:
                    pass
            try:
                readline.write_history_file(self.conf['history_file'])
            except IOError:
                self.log.error('WARN: couldn\'t write history '
                               'to file %s\n' % self.conf['history_file'])

    def complete(self, text, state):
        """Return the next possible completion for 'text'.
        If a command has not been entered, then complete against command list.
        Otherwise try to call complete_<command> to get list of completions.
        """
        if state == 0:
            origline = readline.get_line_buffer()
            line = origline.lstrip()
            # in case '|', ';', '&' used, take last part of line to complete
            line = re.split('&|\||;', line)[-1].lstrip()
            stripped = len(origline) - len(line)
            begidx = readline.get_begidx() - stripped
            endidx = readline.get_endidx() - stripped
            # complete with sudo allowed commands
            if line.split(' ')[0] == 'sudo' and len(line.split(' ')) <= 2:
                compfunc = self.completesudo
            # complete next argument with file or directory
            elif len(line.split(' ')) > 1 \
                    and line.split(' ')[0] in self.conf['allowed']:
                compfunc = self.completechdir
            elif begidx > 0:
                cmd, args, foo = self.parseline(line)
                if cmd == '':
                    compfunc = self.completedefault
                else:
                    try:
                        compfunc = getattr(self, 'complete_' + cmd)
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
        """ This method overrides the original default method.
        It was originally used to warn when an unknown command was entered
        (e.g. *** Unknown syntax: blabla).
        It has been implemented in the __getattr__ method.
        So it has no use here. Its output is now empty.
        """
        self.stdout.write('')

    def completenames(self, text, line, *ignored):
        """ This method overrides the original completenames method to overload
        it's output with the command available in the 'allowed' variable
        This is useful when typing 'tab-tab' in the command prompt
        """
        commands = self.conf['allowed']
        commands.append('help')
        if line.startswith('./'):
            return [cmd[2:] for cmd in commands if cmd.startswith('./%s'
                                                                  % text)]
        else:
            return [cmd for cmd in commands if cmd.startswith(text)]

    def completesudo(self, text, line, begidx, endidx):
        """ complete sudo command """
        return [a for a in self.conf['sudo_commands'] if a.startswith(text)]

    def completechdir(self, text, line, begidx, endidx):
        """ complete directories """
        toreturn = []
        tocomplete = line.split()[-1]
        # replace "~" with home path
        tocomplete = re.sub('^~', self.conf['home_path'], tocomplete)
        try:
            directory = os.path.realpath(tocomplete)
        except:
            directory = os.getcwd()

        if not os.path.isdir(directory):
            directory = directory.rsplit('/', 1)[0]
            if directory == '':
                directory = '/'
            if not os.path.isdir(directory):
                directory = os.getcwd()

        ret_check_path, self.conf = sec.check_path(directory,
                                                   self.conf,
                                                   completion=1)
        if ret_check_path == 0:
            for instance in os.listdir(directory):
                if os.path.isdir(os.path.join(directory, instance)):
                    instance = instance + '/'
                else:
                    instance = instance + ' '
                if instance.startswith('.'):
                    if text.startswith('.'):
                        toreturn.append(instance)
                    else:
                        pass
                else:
                    toreturn.append(instance)
            return [a for a in toreturn if a.startswith(text)]
        else:
            return None

    def onecmd(self, line):
        """ This method overrides the original onecmd method, to put the cmd,
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
        if cmd == '':
            return self.default(line)
        else:
            try:
                func = getattr(self, 'do_' + cmd)
            except AttributeError:
                return self.default(line)
            return func(arg)

    def emptyline(self):
        """ This method overrides the original emptyline method, so it doesn't
        repeat the last command if last command was empty.
        I just found this annoying..
        """
        if self.lastcmd:
            return 0

    def do_help(self, arg):
        """ This method overrides the original do_help method.
        Instead of printing out the that are documented or not, it returns the
        list of allowed commands when '?' or 'help' is entered.
        Of course, it doesn't override the help function: any help_* method
        will be called (e.g. help_help(self) )
        """
        if arg:
            self.help_help()
        else:
            # Get list of allowed commands, remove duplicate 'help' then sort
            list_tmp = list(dict.fromkeys(self.completenames('', '')).keys())
            list_tmp.sort()
            self.columnize(list_tmp)

    def help_help(self):
        """ Print Help on Help """
        self.stdout.write('Help! Help! Help! Help! '
                          "Please contact your system's administrator.\n")

    def mytimer(self, timeout):
        """ This function is kicks you out the the lshell after
        the 'timer' variable expires. 'timer' is set in seconds.
        """
        # set timer
        signal.signal(signal.SIGALRM, self._timererror)
        signal.alarm(timeout)

    def _timererror(self, signum, frame):
        raise LshellTimeOut("lshell timer timeout")


class LshellTimeOut(Exception):
    """ Custom exception used for timer timeout
    """

    def __init__(self, value="Timed Out"):
        self.value = value

    def __str__(self):
        return repr(self.value)
