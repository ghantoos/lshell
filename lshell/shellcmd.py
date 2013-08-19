#
#    Limited command Shell (lshell)
#  
#    Copyright (C) 2008-2013 Ignace Mouzannar (ghantoos) <ghantoos@ghantoos.org>
#
#    This file is part of lshell
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import cmd
import sys
import os
from getpass import getuser
import re
import signal
import readline
import glob

from utils import get_aliases


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
        if 'prompt' in self.conf:
            self.promptbase = self.conf['prompt']
            self.promptbase = self.promptbase.replace('%u', getuser())
            self.promptbase = self.promptbase.replace(
                '%h',
                os.uname()[1].split('.')[0])
        else:
            self.promptbase = getuser()

        self.prompt = '%s:~$ ' % self.promptbase

        self.intro = self.conf['intro']

        # initialize oldpwd variable to home directory
        self.oldpwd = self.conf['home_path']

        # initialize cli variables
        self.g_cmd = g_cmd
        self.g_line = g_line

    def __getattr__(self, attr):
        """ This method actually takes care of all the called method that are
        not resolved (i.e not existing methods). It actually will simulate
        the existance of any method    entered in the 'allowed' variable list.

        e.g. You just have to add 'uname' in list of allowed commands in
        the 'allowed' variable, and lshell will react as if you had
        added a do_uname in the ShellCmd class!
        """

        # in case the configuration file has been modified, reload it
        if self.conf['config_mtime'] != os.path.getmtime(self.conf['configfile']):
            from lshell.checkconfig import CheckConfig
            self.conf = CheckConfig(['--config', \
                                     self.conf['configfile']]).returnconf()
            self.prompt = '%s:~$ ' % self.setprompt(self.conf)
            self.log = self.conf['logpath']

        if self.g_cmd in ['quit', 'exit', 'EOF']:
            self.log.error('Exited')
            if self.g_cmd == 'EOF':
                self.stdout.write('\n')
            sys.exit(0)
        if self.check_secure(self.g_line, self.conf['strict']) == 1: 
            return object.__getattribute__(self, attr)
        if self.check_path(self.g_line, strict = self.conf['strict']) == 1:
            return object.__getattribute__(self, attr)
        if self.g_cmd in self.conf['allowed']:
            self.g_arg = re.sub('^~$|^~/', '%s/' %self.conf['home_path'],      \
                                                                   self.g_arg)
            self.g_arg = re.sub(' ~/', ' %s/'  %self.conf['home_path'],        \
                                                                   self.g_arg)
            if type(self.conf['aliases']) == dict:
                self.g_line = get_aliases(self.g_line, self.conf['aliases'])
            self.log.info('CMD: "%s"' %self.g_line)
            if self.g_cmd == 'cd':
                self.cd()
            # builtin lpath function: list all allowed path
            elif self.g_cmd == 'lpath':
                self.lpath()
            # builtin lsudo function: list all allowed sudo commands
            elif self.g_cmd == 'lsudo':
                self.lsudo()
            # builtin history function: print command history
            elif self.g_cmd == 'history':
                self.history()
            # builtin export function
            elif self.g_cmd == 'export':
                self.export()
            # case 'cd' is in an alias e.g. {'toto':'cd /var/tmp'}
            elif self.g_line[0:2] == 'cd':
                self.g_cmd = self.g_line.split()[0]
                self.g_arg = ' '.join(self.g_line.split()[1:])
                self.cd()
            else:
                os.system('set -m; %s' % self.g_line)
        elif self.g_cmd not in ['', '?', 'help', None]: 
            self.log.warn('INFO: unknown syntax -> "%s"' %self.g_line)
            self.stderr.write('*** unknown syntax: %s\n' %self.g_cmd)
        self.g_cmd, self.g_arg, self.g_line = ['', '', ''] 
        return object.__getattribute__(self, attr)

    def setprompt(self, conf):
        """ set prompt used by the shell
        """
        if conf.has_key('prompt'):
            promptbase = conf['prompt']
            promptbase = promptbase.replace('%u', getuser())
            promptbase = promptbase.replace('%h', os.uname()[1].split('.')[0])
        else:
            promptbase = getuser()

        return promptbase

    def lpath(self):
        """ lists allowed and forbidden path
        """
        if self.conf['path'][0]:
            sys.stdout.write("Allowed:\n")
            for path in self.conf['path'][0].split('|'):
                if path:
                    sys.stdout.write(" %s\n" % path[:-2])
        if self.conf['path'][1]:
            sys.stdout.write("Denied:\n")
            for path in self.conf['path'][1].split('|'):
                if path:
                    sys.stdout.write(" %s\n" % path[:-2])

    def lsudo(self):
        """ lists allowed sudo commands
        """
        if self.conf.has_key('sudo_commands'):
            sys.stdout.write("Allowed sudo commands:\n")
            for command in self.conf['sudo_commands']:
                sys.stdout.write(" - %s\n" % command)

    def history(self):
        """ print the commands history
        """
        try:
            try:
                readline.write_history_file(self.conf['history_file'])
            except IOError:
                self.log.error('WARN: couldn\'t write history ' \
                                   'to file %s\n' % self.conf['history_file'])
            f = open(self.conf['history_file'], 'r')
            i = 1
            for item in f.readlines():
                sys.stdout.write("%d:  %s" % (i, item))
                i += 1
        except:
            self.log.critical('** Unable to read the history file.')

    def export(self):
        """ export environment variables """
        # if command contains at least 1 space
        if self.g_line.count(' '):
            env = self.g_line.split(" ", 1)[1]
            # if it conatins the equal sign, consider only the first one
            if env.count('='):
                var, value = env.split(' ')[0].split('=')[0:2]
                # expand values, if variable is surcharged by other variables
                try:
                    import subprocess
                    p = subprocess.Popen( "`which echo` %s" % value,
                                          shell=True,
                                          stdin=subprocess.PIPE,
                                          stdout=subprocess.PIPE )
                    (cin, cout) = (p.stdin, p.stdout)
                except ImportError:
                    cin, cout = os.popen2('`which echo` %s' % value)
                value = cout.readlines()[0]

                os.environ.update({var: value})

    def cd(self):
        """ implementation of the "cd" command
        """
        if len(self.g_arg) >= 1:
            # add wildcard completion support to cd
            if self.g_arg.find('*'):
                # get all files and directories matching wildcard
                wildall = glob.glob(self.g_arg)
                wilddir = []
                # filter to only directories
                for item in wildall:
                    if os.path.isdir(item):
                        wilddir.append(item)
                # sort results
                wilddir.sort()
                # if any results are returned, pick first one
                if len(wilddir) >= 1:
                    self.g_arg = wilddir[0]
            # go previous directory
            if self.g_arg == '-':
                self.g_arg = self.oldpwd

            # store current directory in oldpwd variable
            self.oldpwd = os.getcwd()

            # change directory
            try:
                os.chdir(os.path.realpath(self.g_arg))
                self.updateprompt(os.getcwd())
            except OSError, (ErrorNumber, ErrorMessage):
                sys.stdout.write("lshell: %s: %s\n" %(self.g_arg, ErrorMessage))
        else:
            os.chdir(self.conf['home_path'])
            self.updateprompt(os.getcwd())

    def check_secure(self, line, strict=None, ssh=None):
        """This method is used to check the content on the typed command.      \
        Its purpose is to forbid the user to user to override the lshell       \
        command restrictions. 
        The forbidden characters are placed in the 'forbidden' variable.
        Feel free to update the list. Emptying it would be quite useless..: )

        A warining counter has been added, to kick out of lshell a user if he  \
        is warned more than X time (X beeing the 'warning_counter' variable).
        """

        # store original string
        oline = line

        # strip all spaces/tabs
        line = " ".join(line.split())

        # ignore quoted text
        line = re.sub(r'\"(.+?)\"', '', line)
        line = re.sub(r'\'(.+?)\'', '', line)

        if re.findall('[:cntrl:].*\n', line):
            if not ssh:
                if strict:
                    self.counter_update('syntax')
                else:
                    self.log.critical('*** forbidden syntax -> %s' % oline)
            return 1

        for item in self.conf['forbidden']:
            # allow '&&' and '||' even if singles are forbidden
            if item in ['&', '|']:
                if re.findall("[^\%s]\%s[^\%s]" %(item, item, item), line):
                    return self.warn_count('syntax', oline, strict, ssh)
            else:
                if item in line:
                    return self.warn_count('syntax', oline, strict, ssh)

        returncode = 0
        # check if the line contains $(foo) executions, and check them
        executions = re.findall('\$\([^)]+[)]', line)
        for item in executions:
            returncode += self.check_path(item[2:-1].strip(), strict = strict)
            returncode += self.check_secure(item[2:-1].strip(), strict = strict)

        # check fot executions using back quotes '`'
        executions = re.findall('\`[^`]+[`]', line)
        for item in executions:
            returncode += self.check_secure(item[1:-1].strip(), strict = strict)

        # check if the line contains ${foo=bar}, and check them
        curly = re.findall('\$\{[^}]+[}]', line)
        for item in curly:
            # split to get variable only, and remove last character "}"
            if re.findall(r'=|\+|\?|\-', item):
                variable = re.split('=|\+|\?|\-', item, 1)
            else:
                variable = item
            returncode += self.check_path(variable[1][:-1], strict = strict)
            
        # if unknown commands where found, return 1 and don't execute the line
        if returncode > 0:
            return 1
        # in case the $(foo) or `foo` command passed the above tests
        elif line.startswith('$(') or line.startswith('`'):
            return 0

        # in case ';', '|' or '&' are not forbidden, check if in line
        lines = []
        
        # corrected by Alojzij Blatnik #48
        # test first character
        if line[0] in ["&", "|", ";"]:
            start = 1
        else:
            start = 0
        
        # split remaining command line
        for i in range(1, len(line)):
            # in case \& or \| or \; don't split it
            if line[i] in ["&", "|", ";"] and line[i-1] != "\\":
                # if there is more && or || skip it
                if start != i:
                    lines.append(line[start:i])
                start = i+1

        # append remaining command line
        if start != len(line):
            lines.append(line[start:len(line)])
        
        # remove trailing parenthesis
        line = re.sub('\)$', '', line)
        for separate_line in lines:
            separate_line = " ".join(separate_line.split())
            splitcmd = separate_line.strip().split(' ')
            command = splitcmd[0]
            if len(splitcmd) > 1:
                cmdargs = splitcmd
            else: cmdargs = None

            # in case of a sudo command, check in sudo_commands list if allowed
            if command == 'sudo':
                if type(cmdargs) == list:
                    if cmdargs[1] not in self.conf['sudo_commands'] and cmdargs:
                        return self.warn_count('sudo command', oline, strict, ssh)

            # if over SSH, replaced allowed list with the one of overssh
            if ssh:
                self.conf['allowed'] = self.conf['overssh']
            
            # for all other commands check in allowed list
            if command not in self.conf['allowed'] and command:
                return self.warn_count('command', oline, strict, ssh, command)
        return 0

    def warn_count(self, messagetype, line=None, strict=None, ssh=None, command=None):
        """ Update the warning_counter, log and display a warning to the user
        """
        if not line:
            line = self.g_line
        if command:
            line = command

        if not ssh:
            if strict:
                self.conf['warning_counter'] -= 1
                if self.conf['warning_counter'] < 0:
                    self.log.critical('*** forbidden %s -> "%s"'                   \
                                                          % (messagetype ,line))
                    self.log.critical('*** Kicked out')
                    sys.exit(1)
                else:
                    self.log.critical('*** forbidden %s -> "%s"'                   \
                                                          % (messagetype ,line))
                    self.stderr.write('*** You have %s warning(s) left,'           \
                                        ' before getting kicked out.\n'            \
                                        %(self.conf['warning_counter']))
                    self.stderr.write('This incident has been reported.\n')
            else:
                if not self.conf['quiet']:
                    self.log.critical('*** forbidden %s: %s' % (messagetype, line))

        # if you are here, means that you did something wrong. Return 1.
        return 1

    def counter_update(self, messagetype, path=None):
        """ Update the warning_counter, log and display a warning to the user
        """
        if path:
            line = path
        else:
            line = self.g_line

        # if warning_counter is set to -1, just warn, don't kick
        if self.conf['warning_counter'] == -1:
            self.log.critical('*** forbidden %s -> "%s"'                       \
                                                      % (messagetype ,line))
        else:
            self.conf['warning_counter'] -= 1
            if self.conf['warning_counter'] < 0: 
                self.log.critical('*** forbidden %s -> "%s"'                   \
                                                      % (messagetype ,line))
                self.log.critical('*** Kicked out')
                sys.exit(1)
            else:
                self.log.critical('*** forbidden %s -> "%s"'                   \
                                                      % (messagetype ,line))
                self.stderr.write('*** You have %s warning(s) left,'           \
                                    ' before getting kicked out.\n'            \
                                    %(self.conf['warning_counter']))
                self.stderr.write('This incident has been reported.\n')

    def check_path(self, line, completion=None, ssh=None, strict=None):
        """ Check if a path is entered in the line. If so, it checks if user   \
        are allowed to see this path. If user is not allowed, it calls         \
        self.counter_update. I case of completion, it only returns 0 or 1.
        """
        allowed_path_re = str(self.conf['path'][0])
        denied_path_re = str(self.conf['path'][1][:-1])

        # split line depending on the operators
        sep=re.compile(r'\ |;|\||&')
        line = line.strip()
        line = sep.split(line)

        for item in line:
            # remove potential quotes
            item = re.sub(r'^["\']|["\']$', '', item)

            # if item has been converted to somthing other than a string
            # or an int, reconvert it to a string
            if type(item) not in ['str', 'int']:
                item = str(item)
            # replace "~" with home path
            item = os.path.expanduser(item)
            # if contains a shell variable
            if re.findall('\$|\*|\?', item):
                # remove quotes if available
                item = re.sub("\"|\'", "", item)
                # expand shell variables (method 1)
                #for var in re.findall(r'\$(\w+|\{[^}]*\})', item):
                #    # get variable value (if defined)
                #    if os.environ.has_key(var):
                #        value = os.environ[var]
                #    else: value = ''
                #    # replace the variable
                #    item = re.sub('\$%s|\${%s}' %(var, var), value, item)
                # expand shell variables and wildcards using "echo"
                # i know, this a bit nasty...
                try:
                    import subprocess
                    p = subprocess.Popen( "`which echo` %s" % item,
                                          shell=True,
                                          stdin=subprocess.PIPE,
                                          stdout=subprocess.PIPE )
                    (cin, cout) = (p.stdin, p.stdout)
                except ImportError:
                    cin, cout = os.popen2('`which echo` %s' % item)
                item = cout.readlines()[0].split(' ')[0].strip()
                item = os.path.expandvars(item)
            tomatch = os.path.realpath(item)
            if os.path.isdir(tomatch) and tomatch[-1] != '/': tomatch += '/'
            match_allowed = re.findall(allowed_path_re, tomatch)
            if denied_path_re: 
                match_denied = re.findall(denied_path_re, tomatch)
            else: match_denied = None
            if not match_allowed or match_denied:
                if not completion:
                    return self.warn_count('path', tomatch, strict, ssh)
        if not completion:
            if not re.findall(allowed_path_re, os.getcwd()+'/'):
                if not ssh:
                    if strict:
                        self.counter_update('path', os.getcwd())
                        os.chdir(self.conf['home_path'])
                        self.updateprompt(os.getcwd())
                    else:
                        self.log.critical('*** Forbidden path: %s'            \
                                                        %os.getcwd())
                return 1
        return 0

    def updateprompt(self, path):
        """ Update prompt when changing directory
        """

        if path is self.conf['home_path']:
            self.prompt = '%s:~$ ' % self.promptbase
        elif self.conf['prompt_short'] == 1:
            self.prompt = '%s: %s$ ' % (self.promptbase, path.split('/')[-1])
        elif re.findall(self.conf['home_path'], path):
            self.prompt = '%s:~%s$ ' % ( self.promptbase, \
                                         path.split(self.conf['home_path'])[1])
        else:
            self.prompt = '%s:%s$ ' % (self.promptbase, path)

    def cmdloop(self, intro=None):
        """Repeatedly issue a prompt, accept input, parse an initial prefix    \
        off the received input, and dispatch to action methods, passing them   \
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
            readline.set_completer_delims(readline.get_completer_delims().replace('-', ''))
            self.old_completer = readline.get_completer()
            readline.set_completer(self.complete)
            readline.parse_and_bind(self.completekey+": complete")
        try:
            if self.intro and isinstance(self.intro, str):
                self.stdout.write("%s\n" % self.intro)
            if self.conf['login_script']:
                os.system(self.conf['login_script'])
            stop = None
            while not stop:
                if self.cmdqueue:
                    line = self.cmdqueue.pop(0)
                else:
                    if self.use_rawinput:
                        try:
                            line = raw_input(self.prompt)
                        except EOFError:
                            line = 'EOF'
                        except KeyboardInterrupt:
                            self.stdout.write('\n')
                            line = ''
                    else:
                        self.stdout.write(self.prompt)
                        self.stdout.flush()
                        line = self.stdin.readline()
                        if not len(line):
                            line = 'EOF'
                        else:
                            line = line[:-1] # chop \n
                line = self.precmd(line)
                stop = self.onecmd(line)
                stop = self.postcmd(stop, line)
            self.postloop()
        finally:
            if self.use_rawinput and self.completekey:
                try:
                    readline.set_completer_delims(readline.get_completer_delims().replace('-', ''))
                    readline.set_completer(self.old_completer)
                except ImportError:
                    pass
            try:
                readline.write_history_file(self.conf['history_file'])
            except IOError:
                self.log.error('WARN: couldn\'t write history '                \
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
            if line.split(' ')[0] == 'sudo' and len(line.split(' ')) <= 2:
                compfunc = self.completesudo
            elif len (line.split(' ')) > 1 \
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
            else:
                compfunc = self.completenames
            self.completion_matches = compfunc(text, line, begidx, endidx)
        try:
            return self.completion_matches[state]
        except IndexError:
            return None

    def default(self, line):
        """ This method overrides the original default method. 
        It was originally used to warn when an unknown command was entered     \
        (e.g. *** Unknown syntax: blabla). 
        It has been implemented in the __getattr__ method.
        So it has no use here. Its output is now empty.
        """
        self.stdout.write('')

    def completenames(self, text, *ignored):
        """ This method overrides the original completenames method to overload\
        it's output with the command available in the 'allowed' variable       \
        This is useful when typing 'tab-tab' in the command prompt
        """
        dotext = 'do_'+text
        names = self.get_names()
        for command in self.conf['allowed']: 
            names.append('do_' + command)
        return [a[3:] for a in names if a.startswith(dotext)]

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
            if directory == '': directory = '/'
            if not os.path.isdir(directory):
                directory = os.getcwd()

        if self.check_path(directory, 1) == 0:
            for instance in os.listdir(directory):
                if os.path.isdir(os.path.join(directory, instance)):
                    instance = instance + '/'
                else: instance = instance + ' '
                if instance.startswith('.'):
                    if text.startswith('.'):
                        toreturn.append(instance)
                    else: pass
                else: toreturn.append(instance)
            return [a for a in toreturn if a.startswith(text)]
        else:
            return None

    def onecmd(self, line):
        """ This method overrides the original onecomd method, to put the cmd, \
        arg and line variables in class global variables: self.g_cmd,          \
        self.g_arg and self.g_line.
        Thos variables are then used by the __getattr__ method
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
        """ This method overrides the original emptyline method, so it doesn't \
        repeat the last command if last command was empty.
        I just found this annoying..
        """
        if self.lastcmd:
            return 0

    def do_help(self, arg):
        """ This method overrides the original do_help method. 
        Instead of printing out the that are documented or not, it returns the \
        list of allowed commands when '?' or 'help' is entered. 
        Of course, it doesn't override the help function: any help_* method    \
        will be called (e.g. help_help(self) )
        """ 
        if arg:
            try:
                func = getattr(self, 'help_' + arg)
            except AttributeError:
                try:
                    doc = getattr(self, 'do_' + arg).__doc__
                    if doc:
                        self.stdout.write("%s\n"%str(doc))
                        return
                except AttributeError:
                    pass
                self.stdout.write("%s\n"%str(self.nohelp % (arg,)))
                return
            func()
        else:
            # Get list of allowed commands, remove duplicate 'help' then sort it
            list_tmp = dict.fromkeys(self.completenames('')).keys()
            list_tmp.sort()
            self.columnize(list_tmp)

    def help_help(self):
        """ Print Help on Help """
        self.stdout.write(help_help)

    def mytimer(self, timeout):
        """ This function is kicks you out the the lshell after      \
        the 'timer' variable exprires. 'timer' is set in seconds.
        """
        # set timer
        signal.signal(signal.SIGALRM, self._timererror)
        signal.alarm(self.conf['timer'])

    def _timererror(self, signum, frame):
        raise LshellTimeOut("lshell timer timeout")


class LshellTimeOut(Exception):
    """ Custum exception used for timer timeout
    """

    def __init__(self, value="Timed Out"):
        self.value = value

    def __str__(self):
        return repr(self.value)
