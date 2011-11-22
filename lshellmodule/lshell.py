#!/usr/bin/env python
#
#    Limited command Shell (lshell)
#  
#    $Id: lshell.py,v 1.80 2010-10-26 22:35:28 ghantoos Exp $
#
#    Copyright (C) 2008-2009 Ignace Mouzannar (ghantoos) <ghantoos@ghantoos.org>
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
"""lshell restricts a user's shell environment to limited sets of commands
lshell is a shell coded in Python that lets you restrict a user's environment
to limited sets of commands, choose to enable/disable any command over SSH
(e.g. SCP, SFTP, rsync, etc.), log user's commands, implement timing 
"""

import cmd
import sys
import os
import ConfigParser
from getpass import getpass, getuser
import string
import re
import getopt
import logging
import signal
import readline
import grp
import time

__author__ = "Ignace Mouzannar (ghantoos) <ghantoos@ghantoos.org>"
__version__ = "0.9.15"

# Required config variable list per user
required_config = ['allowed', 'forbidden', 'warning_counter'] 
#                                                    'timer', 'scp', 'sftp']

# set configuration file path depending on sys.exec_prefix
# on *Linux sys.exec_prefix = '/usr' and default path must be in '/etc'
# on *BSD sys.exec_prefix = '/usr/{pkg,local}/' and default path 
# is '/usr/{pkg,local}/etc'
if sys.exec_prefix != '/usr':
    # for *BSD
    conf_prefix = sys.exec_prefix
else:
    # for *Linux
    conf_prefix = ''
config_file = conf_prefix + '/etc/lshell.conf'

# history file
history_file = ".lhistory"

# lock_file
lock_file = ".lshell_lock"

# help text
usage = """Usage: lshell [OPTIONS]
  --config <file> : Config file location (default %s)
  --log    <dir>  : Log files directory
  -h, --help      : Show this help message
  --version       : Show version
""" % config_file

help_help = """Limited Shell (lshell) limited help.
Cheers.
"""

# Intro Text
intro = """You are in a limited shell.
Type '?' or 'help' to get the list of allowed commands"""

class ShellCmd(cmd.Cmd, object): 
    """ Main lshell CLI class
    """

    def __init__(self, userconf, stdin=None, stdout=None, stderr=None,         \
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

        self.conf = userconf
        self.log = self.conf['logpath']

        # Set timer
        if self.conf['timer'] > 0: self.mytimer(self.conf['timer'])
        self.identchars = self.identchars + '+./-'
        self.log.error('Logged in')
        cmd.Cmd.__init__(self)
        if self.conf.has_key('prompt'):
            self.promptbase = self.conf['prompt']
            self.promptbase = self.promptbase.replace('%u', getuser())
            self.promptbase = self.promptbase.replace('%h', \
                                                    os.uname()[1].split('.')[0])
        else:
            self.promptbase = getuser()

        self.prompt = '%s:~$ ' % self.promptbase

        self.intro = self.conf['intro']

        # initialize cli variables
        self.g_cmd = g_cmd
        self.g_line = g_line

    def __getattr__(self, attr):
        """ This method actually takes care of all the called method that are  \
        not resolved (i.e not existing methods). It actually will simulate     \
        the existance of any method    entered in the 'allowed' variable list. \

        e.g. You just have to add 'uname' in list of allowed commands in       \
        the 'allowed' variable, and lshell will react as if you had            \
        added a do_uname in the ShellCmd class!
        """
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
            else:
                os.system(self.g_line)
        elif self.g_cmd not in ['', '?', 'help', None]: 
            self.log.warn('INFO: unknown syntax -> "%s"' %self.g_line)
            self.stderr.write('*** unknown syntax: %s\n' %self.g_cmd)
        self.g_cmd, self.g_arg, self.g_line = ['', '', ''] 
        return object.__getattribute__(self, attr)

    def lpath(self):
        """ lists allowed and forbidden path
        """
        if self.conf['path'][0]:
            sys.stdout.write("Allowed:\n")
            for path in self.conf['path'][0].split('|'):
                if path:
                    sys.stdout.write(" %s\n" %path[:-2])
        if self.conf['path'][1]:
            sys.stdout.write("Denied:\n")
            for path in self.conf['path'][1].split('|'):
                if path:
                    sys.stdout.write(" %s\n" %path[:-2])

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
                self.log.error('WARN: couldn\'t write history '                \
                                   'to file %s\n' % self.conf['history_file'])
            f = open(self.conf['history_file'], 'r')
            i = 1
            for item in f.readlines():
                sys.stdout.write("%d:  %s" % (i, item) )
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
                os.environ.update({var:value})

    def cd(self):
        """ implementation of the "cd" command
        """
        if len(self.g_arg) >= 1:
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

        for item in self.conf['forbidden']:
            # allow '&&' and '||' even if singles are forbidden
            if item in ['&', '|']:
                if re.findall("[^\%s]\%s[^\%s]" %(item, item, item), line):
                    if not ssh:
                        self.counter_update('syntax')
                    return 1
            else:
                if item in line:
                    if not ssh:
                        self.counter_update('syntax')
                    return 1

        returncode = 0
        # check if the line contains $(foo) executions, and check them
        executions = re.findall('\$\([^)]+[)]', line)
        for item in executions:
            returncode += self.check_path(item[2:-1].strip(), strict = strict)
            returncode += self.check_secure(item[2:].strip(), strict=1)

        # check fot executions using back quotes '`'
        executions = re.findall('\`[^`]+[`]', line)
        for item in executions:
            returncode += self.check_secure(item[1:-1].strip(), strict=1)

        # check if the line contains ${foo=bar}, and check them
        curly = re.findall('\$\{[^}]+[}]', line)
        for item in curly:
            # split to get get variable only, and remove last character "}"
            variable = re.split('=|\+|\?|\-', item, 1)
            returncode += self.check_path(variable[1][:-1], strict = strict)
            
        # if unknown commands where found, return 1 and don't execute the line
        if returncode > 0:
            return 1
        # in case the $(foo) or `foo` command passed the above tests
        elif line.startswith('$(') or line.startswith('`'):
            return 0

        # in case ';', '|' or '&' are not forbidden, check if in line
        lines = re.split('&|\||;', line)
        # remove trailing parenthesis
        line = re.sub('\)$', '', line)
        for sperate_line in lines:
            splitcmd = sperate_line.strip().split(' ')
            command = splitcmd[0]
            if len(splitcmd) > 1:
                cmdargs = splitcmd
            else: cmdargs = None

            # in case of a sudo command, check in sudo_commands list if allowed
            if command == 'sudo':
                if type(cmdargs) == list:
                    if cmdargs[1] not in self.conf['sudo_commands'] and cmdargs:
                        if self.conf['strict'] == 1:
                            if not ssh:
                                self.counter_update('command')
                        else:
                            self.log.critical('*** forbidden sudo -> %s'       \
                                                    % line )
                        return 1
            # if over SSH, replaced allowed list with the one of overssh
            if ssh:
                self.conf['allowed'] = self.conf['overssh']
            
            # for all other commands check in allowed list
            if command not in self.conf['allowed'] and command:
                if strict:
                    if not ssh:
                        self.counter_update('command', line)
                else:
                    self.log.critical('*** unknown command: %s' %command)
                return 1
        return 0
         
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

        line = line.strip().split()
        for item in line:
            # remove potential quotes
            try:
                item = eval(item)
            except:
                pass
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
                    if not ssh:
                        if strict: 
                            self.counter_update('path', tomatch)
                        else: 
                            self.log.critical('*** Forbidden path: %s'        \
                                                        % tomatch)
                return 1    
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
        elif re.findall(self.conf['home_path'], path) :
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
            self.old_completer = readline.get_completer()
            readline.set_completer(self.complete)
            readline.parse_and_bind(self.completekey+": complete")
        try:
            if intro is not None:
                self.intro = intro
            if self.conf['intro']:
                self.stdout.write(str(self.conf['intro'])+"\n")
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
        raise LshellTimeOut, "lshell timer timeout"

class CheckConfig:
    """ Check the configuration file.
    """

    def __init__(self, args, stdin=None, stdout=None, stderr=None):
        """ Force the calling of the methods below
        """ 
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

        self.conf = {}
        self.conf, self.arguments = self.getoptions(args, self.conf)
        self.check_file(self.conf['configfile'])
        self.get_global()
        self.check_log()
        self.get_config()
        self.check_user_integrity()
        self.get_config_user()
        self.check_env()
        self.check_scp_sftp()
        self.check_passwd()

    def getoptions(self, arguments, conf):
        """ This method checks the usage. lshell.py must be called with a      \
        configuration file.
        If no configuration file is specified, it will set the configuration   \
        file path to /etc/lshell.confelf.conf['allowed'].append('exit')
        """
        # uncomment the following to set the -c/--config as mandatory argument
        #if '-c' not in arguments and '--config' not in arguments:
        #    usage()

        # set config_file as default configuration file
        conf['configfile'] = config_file

        try:
            optlist, args = getopt.getopt(arguments,                           \
                                    'hc:',                                     \
                                    ['config=','log=','help','version'])
        except getopt.GetoptError:
            self.stderr.write('Missing or unknown argument(s)\n')
            self.usage()


        for option, value in optlist:
            if  option in ['--config']:
                conf['configfile'] = os.path.realpath(value)
            if  option in ['--log']:
                conf['logpath'] = os.path.realpath(value)
            if  option in ['-c']:
                conf['ssh'] = value
            if option in ['-h', '--help']:
                self.usage()
            if option in ['--version']:
                self.version()

        # put the expanded path of configfile and logpath (if exists) in 
        # LSHELL_ARGS environment variable
        args = ['--config', conf['configfile']]
        if conf.has_key('logpath'): args += ['--log', conf['logpath']]
        os.environ['LSHELL_ARGS'] = str(args)

        # if lshell is invoked using shh autorized_keys file e.g.
        # command="/usr/bin/lshell", ssh-dss ....
        if os.environ.has_key('SSH_ORIGINAL_COMMAND'):
            conf['ssh'] = os.environ['SSH_ORIGINAL_COMMAND']

        return conf, args

    def usage(self):
        """ Prints the usage """
        sys.stderr.write(usage)
        sys.exit(0)

    def version(self):
        """ Prints the version """
        sys.stderr.write('lshell-%s - Limited Shell\n' %__version__)
        sys.exit(0)

    def check_env(self):
        """ Load environment variable set in configuration file """
        if self.conf.has_key('env_vars'):
            env_vars = self.conf['env_vars']
            for key in env_vars.keys():
                os.environ[key] = str(env_vars[key])

    def check_file(self, file):
        """ This method checks the existence of the "argumently" given         \
        configuration file.
        """
        if not os.path.exists(file): 
            self.stderr.write("Error: Config file doesn't exist\n")
            self.stderr.write(usage)
            sys.exit(0)
        else: self.config = ConfigParser.ConfigParser()

    def get_global(self):
        """ Loads the [global] parameters from the configuration file 
        """
        try:
            self.config.read(self.conf['configfile'])
        except (ConfigParser.MissingSectionHeaderError,                        \
                                    ConfigParser.ParsingError), argument:
            self.stderr.write('ERR: %s\n' %argument)
            sys.exit(0)

        if not self.config.has_section('global'):
            self.stderr.write('Config file missing [global] section\n')
            sys.exit(0)

        for item in self.config.items('global'):
            if not self.conf.has_key(item[0]):
                self.conf[item[0]] = item[1]

    def check_log(self):
        """ Sets the log level and log file 
        """
        # define log levels dict
        self.levels = { 1 : logging.CRITICAL, 
                        2 : logging.ERROR, 
                        3 : logging.WARNING,
                        4 : logging.DEBUG }

        # create logger for lshell application
        if self.conf.has_key('syslogname'):
            try:
                logname = eval(self.conf['syslogname'])
            except:
                logfilename = self.conf['syslogname']
        else:
            logname = 'lshell'

        logger = logging.getLogger(logname)
        formatter = logging.Formatter('%%(asctime)s (%s): %%(message)s' \
                                                % getuser() )
        syslogformatter = logging.Formatter('%s[%s]: %s: %%(message)s' \
                                                % (logname, os.getpid(), getuser() ))

        logger.setLevel(logging.DEBUG)

        # set log to output error on stderr
        logsterr = logging.StreamHandler()
        logger.addHandler(logsterr)
        logsterr.setFormatter(logging.Formatter('%(message)s'))
        logsterr.setLevel(logging.CRITICAL)

        # log level must be 1, 2, 3 , 4 or 0
        if not self.conf.has_key('loglevel'): self.conf['loglevel'] = 0
        try:
            self.conf['loglevel'] = int(self.conf['loglevel'])
        except ValueError:
            self.conf['loglevel'] = 0
        if self.conf['loglevel'] > 4: self.conf['loglevel'] = 4
        elif self.conf['loglevel'] < 0: self.conf['loglevel'] = 0

        # read logfilename is exists, and set logfilename
        if self.conf.has_key('logfilename'):
            try:
                logfilename = eval(self.conf['logfilename'])
            except:
                logfilename = self.conf['logfilename']
            currentime = time.localtime()
            logfilename = logfilename.replace('%y','%s'   %currentime[0])
            logfilename = logfilename.replace('%m','%02d' %currentime[1])
            logfilename = logfilename.replace('%d','%02d' %currentime[2])
            logfilename = logfilename.replace('%h','%02d%02d' % (currentime[3] \
                                                              , currentime[4]))
            logfilename = logfilename.replace('%u', getuser())
        else: 
            logfilename = getuser()

        if self.conf['loglevel'] > 0:
            try:
                if logfilename == "syslog":
                    from logging.handlers import SysLogHandler
                    syslog = SysLogHandler(address='/dev/log')
                    syslog.setFormatter(syslogformatter)
                    syslog.setLevel(self.levels[self.conf['loglevel']])
                    logger.addHandler(syslog)
                else:
                    # if log file is writable add new log file handler
                    logfile = os.path.join(self.conf['logpath'], \
                                                            logfilename+'.log')
                    fp = open(logfile,'a').close()
                    self.logfile = logging.FileHandler(logfile)
                    self.logfile.setFormatter(formatter)
                    self.logfile.setLevel(self.levels[self.conf['loglevel']])
                    logger.addHandler(self.logfile)

            except IOError:
                # uncomment the 2 following lines to warn if log file is not   \
                # writable 
                #sys.stderr.write('Warning: Cannot write in log file: '
                #                                        'Permission denied.\n')
                #sys.stderr.write('Warning: Actions will not be logged.\n')
                pass

        self.conf['logpath'] = logger
        self.log = logger

    def get_config(self):
        """ Load default, group and user configuation. Then merge them all. 
        The loadpriority is done in the following order:
            1- User section
            2- Group section
            3- Default section
        """
        self.config.read(self.conf['configfile'])
        self.user = getuser()

        self.conf_raw = {}

        # get 'default' configuration if any
        self.get_config_sub('default')

        # get groups configuration if any.
        # for each group the user belongs to, check if specific configuration  \
        # exists.  The primary group has the highest priority. 
        grplist = os.getgroups()
        grplist.reverse()
        for gid in grplist:
            grpname = grp.getgrgid(gid)[0]
            section = 'grp:' + grpname
            self.get_config_sub(section)

        # get user configuration if any
        self.get_config_sub(self.user)

    def get_config_sub(self, section):
        """ this function is used to interpret the configuration +/-, 
            'all' etc.
        """
        if self.config.has_section(section):
            for item in self.config.items(section):
                key = item[0]
                value = item[1]
                split = re.split('([\+\-\s]+\[[^\]]+\])', value.replace(' ',   \
                                                                            ''))
                if len(split) > 1 and key in ['path',                          \
                                              'overssh',                       \
                                              'allowed',                       \
                                              'forbidden']:
                    for stuff in split:
                        if stuff.startswith('-') or stuff.startswith('+'):
                            self.conf_raw.update(self.minusplus(self.conf_raw, \
                                                                    key,stuff))
                        elif stuff == "'all'":
                            self.conf_raw.update({key:self.expand_all()})
                        elif stuff and key == 'path':
                            liste = ['', '']
                            for path in eval(stuff):
                                liste[0] += os.path.realpath(path) + '/.*|'
                            self.conf_raw.update({key:str(liste)})
                        elif stuff and type(eval(stuff)) is list:
                            self.conf_raw.update({key:stuff})
                # case allowed is set to 'all'
                elif key == 'allowed' and split[0] == "'all'":
                    self.conf_raw.update({key:self.expand_all()})
                elif key == 'path':
                    liste = ['', '']
                    for path in self.myeval(value, 'path'):
                        liste[0] += os.path.realpath(path) + '/.*|'
                    self.conf_raw.update({key:str(liste)})
                else:
                    self.conf_raw.update(dict([item]))

    def minusplus(self, confdict, key, extra):
        """ update configuration lists containing -/+ operators
        """
        if confdict.has_key(key):
            liste = self.myeval(confdict[key])
        elif key == 'path':
            liste = ['', '']
        else:
            liste = []

        sublist = self.myeval(extra[1:], key)
        if extra.startswith('+'):
            if key == 'path':
                for path in sublist:
                    liste[0] += os.path.realpath(path) + '/.*|' 
            else:
                for item in sublist:
                    liste.append(item)
        elif extra.startswith('-'):
            if key == 'path':
                for path in sublist:
                    liste[1] += os.path.realpath(path) + '/.*|'
            else:
                for item in sublist:
                    if item in liste:
                        liste.remove(item)
                    else:
                        self.log.error("CONF: -['%s'] ignored in '%s' list."   \
                                                                 %(item,key))
        return {key:str(liste)}

    def expand_all(self):
        """ expand allowed, if set to 'all'
        """
        # initialize list to common shell builtins
        expanded_all = ['bg', 'break', 'case', 'cd', 'continue', 'eval', \
                        'exec', 'exit', 'fg', 'if', 'jobs', 'kill', 'login', \
                        'logout', 'set', 'shift', 'stop', 'suspend', 'umask', \
                        'unset', 'wait', 'while' ]
        for directory in os.environ['PATH'].split(':'):
            if os.path.exists(directory):
                for item in os.listdir(directory):
                    if os.access(os.path.join(directory, item), os.X_OK):
                        expanded_all.append(item)
            else: self.log.error('CONF: PATH entry "%s" does not exist'        \
                                                                    % directory)

        return str(expanded_all)
 
    def myeval(self, value, info=''):
        """ if eval returns SyntaxError, log it as critical iconf missing """
        try:
            evaluated = eval(value)
            return evaluated
        except SyntaxError:
            self.log.critical('CONF: Incomplete %s field in configuration file'\
                                                            % info)
            sys.exit(1)

    def check_user_integrity(self):
        """ This method checks if all the required fields by user are present  \
        for the present user.
        In case fields are missing, the user is notified and exited from lshell.
        """
        for item in required_config:
            if item not in self.conf_raw.keys():
                self.log.critical('ERROR: Missing parameter \'' \
                                                        + item + '\'')
                self.log.critical('ERROR: Add it in the in the [%s] '
                                    'or [default] section of conf file.'
                                    % self.user)
                sys.exit(0)

    def get_config_user(self):
        """ Once all the checks above have passed, the configuration files     \
        values are entered in a dict to be used by the command line it self.
        The lshell command line is then launched!
        """
        # first, check user's loglevel
        if self.conf_raw.has_key('loglevel'):
            try:
                self.conf['loglevel'] = int(self.conf_raw['loglevel'])
            except ValueError:
                pass
            if self.conf['loglevel'] > 4: self.conf['loglevel'] = 4
            elif self.conf['loglevel'] < 0: self.conf['loglevel'] = 0

            # if log file exists:
            try:
                self.logfile.setLevel(self.levels[self.conf['loglevel']])
            except AttributeError:
                pass

        for item in ['allowed',
                    'forbidden',
                    'sudo_commands',
                    'warning_counter',
                    'env_vars',
                    'timer',
                    'scp',
                    'scp_upload',
                    'scp_download',
                    'sftp',
                    'overssh',
                    'strict',
                    'aliases',
                    'prompt',
                    'history_size']:
            try:
                self.conf[item] = self.myeval(self.conf_raw[item], item)
            except KeyError:
                if item in ['allowed', 'overssh', 'sudo_commands']:
                    self.conf[item] = []
                elif item in ['history_size']:
                    self.conf[item] = -1
                # default scp is allowed
                elif item in ['scp_upload', 'scp_download']:
                    self.conf[item] = 1
                elif item in ['aliases','env_vars']:
                    self.conf[item] = {}
                # do not set the variable
                elif item in ['prompt']:
                    continue
                else:
                    self.conf[item] = 0
            except TypeError:
                self.log.critical('ERR: in the -%s- field. Check the'          \
                                                ' configuration file.' %item )
                sys.exit(0)

        self.conf['username'] = self.user

        if self.conf_raw.has_key('home_path'):
            self.conf_raw['home_path'] = self.conf_raw['home_path'].replace(   \
                                                   "%u", self.conf['username'])
            self.conf['home_path'] = os.path.normpath(self.myeval(self.conf_raw\
                                                    ['home_path'],'home_path'))
        else:
            self.conf['home_path'] = os.environ['HOME']

        if self.conf_raw.has_key('path'):
            self.conf['path'] = eval(self.conf_raw['path'])
            self.conf['path'][0] += self.conf['home_path'] + '.*'
        else:
            self.conf['path'] = ['', '']
            self.conf['path'][0] = self.conf['home_path'] + '.*'

        if self.conf_raw.has_key('env_path'):
            self.conf['env_path'] = self.myeval(self.conf_raw['env_path'],     \
                                                                    'env_path')
        else:
            self.conf['env_path'] = ''

        if self.conf_raw.has_key('scpforce'):
            self.conf_raw['scpforce'] = self.myeval(                           \
                                                self.conf_raw['scpforce'])
            try:
                if os.path.exists(self.conf_raw['scpforce']):
                    self.conf['scpforce'] = self.conf_raw['scpforce']
                else:
                    self.log.error('CONF: scpforce no such directory: %s'      \
                                                    % self.conf_raw['scpforce'])
            except TypeError:
                self.log.error('CONF: scpforce must be a string!')

        if self.conf_raw.has_key('intro'):
            self.conf['intro'] = self.myeval(self.conf_raw['intro'])
        else:
            self.conf['intro'] = intro

        # check if user account if locked
        if self.conf_raw.has_key('lock_counter'):
            self.conf['lock_counter'] = self.conf_raw['lock_counter']
            self.account_lock(self.user, self.conf['lock_counter'], 1)

        if os.path.isdir(self.conf['home_path']):
            os.chdir(self.conf['home_path'])
        else:
            self.log.critical('ERR: home directory "%s" does not exist.'       \
                                                    % self.conf['home_path'])
            sys.exit(0)

        if self.conf_raw.has_key('history_file'):
            try:
                self.conf['history_file'] =                                    \
                               eval(self.conf_raw['history_file'].replace(     \
                                                  "%u", self.conf['username']))
            except:
                self.log.error('CONF: history file error: %s'                  \
                                                % self.conf['history_file'])
        else:
            self.conf['history_file'] = history_file

        if not self.conf['history_file'].startswith('/'):
            self.conf['history_file'] = "%s/%s" % ( self.conf['home_path'],    \
                                                    self.conf['history_file'])

        os.environ['PATH'] = os.environ['PATH'] + self.conf['env_path']

        # append default commands to allowed list
        self.conf['allowed'].append('exit')
        self.conf['allowed'].append('lpath')
        self.conf['allowed'].append('lsudo')
        self.conf['allowed'].append('history')
        self.conf['allowed'].append('clear')

        if self.conf['sudo_commands']:
            self.conf['allowed'].append('sudo')

    def account_lock(self, user, lock_counter, check=None):
        """ check if user account is locked, in which case, exit """
        ### TODO ###
        # check if account is locked
        if check:
            pass
        # increment account lock
        else:
            pass

    def check_scp_sftp(self):
        """ This method checks if the user is trying to SCP a file onto the    \
        server. If this is the case, it checks if the user is allowed to use   \
        SCP or not, and    acts as requested. : )
        """
        if self.conf.has_key('ssh'):
            if os.environ.has_key('SSH_CLIENT')                                \
                                        and not os.environ.has_key('SSH_TTY'):

                # check if sftp is requested and allowed
                if 'sftp-server' in self.conf['ssh']:
                    if self.conf['sftp'] is 1:
                        self.log.error('SFTP connect')
                        os.system(self.conf['ssh'])
                        self.log.error('SFTP disconnect')
                        sys.exit(0)
                    else:
                        self.log.error('*** forbidden SFTP connection')
                        sys.exit(0)

                # initialise cli session
                cli = ShellCmd(self.conf, None, None, None, None,              \
                                                            self.conf['ssh'])
                if cli.check_path(self.conf['ssh'], None, ssh=1):
                    self.ssh_warn('path over SSH', self.conf['ssh'])

                # check path first
                allowed_path_re = str(self.conf['path'][0])
                denied_path_re = str(self.conf['path'][1][:-1])
                for item in self.conf['ssh'].strip().split(' '):
                    tomatch = os.path.realpath(item) + '/'
                    match_allowed = re.findall(allowed_path_re, tomatch)
                    if denied_path_re:
                        match_denied = re.findall(denied_path_re, tomatch)
                    else: match_denied = None
                    if not match_allowed or match_denied:
                        self.ssh_warn('path over SSH', self.conf['ssh'])

                # check if scp is requested and allowed
                if self.conf['ssh'].startswith('scp '):
                    if self.conf['scp'] is 1 or 'scp' in self.conf['overssh']: 
                        if ' -f ' in self.conf['ssh']:
                            # case scp download is allowed
                            if self.conf['scp_download']:
                                self.log.error('SCP: GET "%s"' \
                                                            % self.conf['ssh'])
                            # case scp download is forbidden
                            else:
                                self.log.error('SCP: download forbidden: "%s"' \
                                                            % self.conf['ssh'])
                                sys.exit(0)
                        elif ' -t ' in self.conf['ssh']:
                            # case scp upload is allowed
                            if self.conf['scp_upload']:
                                if self.conf.has_key('scpforce'):
                                    cmdsplit = self.conf['ssh'].split(' ')
                                    scppath = os.path.realpath(cmdsplit[-1])
                                    forcedpath = os.path.realpath(self.conf
                                                                   ['scpforce'])
                                    if scppath != forcedpath:
                                        self.log.error('SCP: forced SCP '      \
                                                       + 'directory: %s'       \
                                                                    %scppath)
                                        cmdsplit.pop(-1)
                                        cmdsplit.append(forcedpath)
                                        self.conf['ssh'] = string.join(cmdsplit)
                                self.log.error('SCP: PUT "%s"'                 \
                                                        %self.conf['ssh'])
                            # case scp upload is forbidden
                            else:
                                self.log.error('SCP: upload forbidden: "%s"'   \
                                                            % self.conf['ssh']) 
                                sys.exit(0)
                        os.system(self.conf['ssh'])
                        self.log.error('SCP disconnect')
                        sys.exit(0)
                    else:
                        self.ssh_warn('SCP connection', self.conf['ssh'], 'scp')

                # check if command is in allowed overssh commands
                elif self.conf['ssh']:
                    # replace aliases
                    self.conf['ssh'] = get_aliases(self.conf['ssh'],           \
                                                         self.conf['aliases'])
                    # if command is not "secure", exit
                    if cli.check_secure(self.conf['ssh'], strict=1, ssh=1):
                        self.ssh_warn('char/command over SSH', self.conf['ssh'])
                    # else
                    self.log.error('Over SSH: "%s"' %self.conf['ssh'])
                    # if command is "help"
                    if self.conf['ssh'] == "help":
                        cli.do_help(None)
                    else:
                        os.system(self.conf['ssh'])
                    self.log.error('Exited')
                    sys.exit(0)

                # else warn and log
                else:
                    self.ssh_warn('command over SSH', self.conf['ssh'])

            else :
                # case of shell escapes
                self.ssh_warn('shell escape', self.conf['ssh'])

    def ssh_warn(self, message, command='', key=''):
        """ log and warn if forbidden action over SSH """
        if key == 'scp':
            self.log.critical('*** forbidden %s' %message)
            self.log.error('*** SCP command: %s' %command)
        else:
            self.log.critical('*** forbidden %s: "%s"' %(message, command))
        self.stderr.write('This incident has been reported.\n')
        self.log.error('Exited')
        sys.exit(0)

    def check_passwd(self):
        """ As a passwd field is required by user. This method checks in the   \
        configuration file if the password is empty, in wich case, no password \
        check is required. In the other case, the password is asked to be      \
        entered. 
        If the entered password is wrong, the user is exited from lshell.
        """
        if self.config.has_section(self.user):
            if self.config.has_option(self.user, 'passwd'):
                passwd = self.config.get(self.user, 'passwd')
            else: 
                passwd = None
        else: 
            passwd = None

        if passwd:
            password = getpass("Enter "+self.user+"'s password: ")
            if password != passwd:
                self.stderr.write('Error: Wrong password \nExiting..\n')
                self.log.critical('WARN: Wrong password')
                sys.exit(0)
        else: return 0

    def returnconf(self):
        """ returns the configuration dict """
        return self.conf

class LshellTimeOut(Exception):
    """ Custum exception used for timer timeout
    """

    def __init__(self, value = "Timed Out"):
        self.value = value
    def __str__(self):
        return repr(self.value)

def get_aliases(line, aliases):
    """ Replace all configured aliases in the line
    """
    for item in aliases.keys():
        reg = '(^|; |;)%s([ ;&\|]+|$)' % item
        while re.findall(reg, line):
            beforecommand = re.findall(reg, line)[0][0]
            aftercommand = re.findall(reg, line)[0][1]
            line = re.sub(reg, "%s%s%s" % (beforecommand, aliases[item],       \
                                                     aftercommand), line, 1)
            # if line does not change after sub, exit loop
            linesave = line
            if linesave == line:
                break
    for char in [';', '&', '|']:
        # remove all remaining double char
        line = line.replace('%s%s' %(char, char), '%s' %char)
    return line

def main():
    """ main function """
    # set SHELL and get LSHELL_ARGS env variables
    os.environ['SHELL'] = os.path.realpath(sys.argv[0])
    if os.environ.has_key('LSHELL_ARGS'):
        args = sys.argv[1:] + eval(os.environ['LSHELL_ARGS'])
    else: args = sys.argv[1:]

    userconf = CheckConfig(args).returnconf()

    try:
        cli = ShellCmd(userconf)
        cli.cmdloop()

    except (KeyboardInterrupt, EOFError):
        sys.stdout.write('\nExited on user request\n')
        sys.exit(0)
    except LshellTimeOut:
        userconf['logpath'].error('Timer expired')
        sys.stdout.write('\nTime is up.\n')

if __name__ == '__main__':
    main()
