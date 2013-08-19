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

import sys
import os
import ConfigParser
from getpass import getpass, getuser
import string
import re
import getopt
import logging
import grp
import time
import glob

from utils import get_aliases

__version__ = "0.9.16"

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
configfile = conf_prefix + '/etc/lshell.conf'

# history file
history_file = ".lhistory"

# lock_file
lock_file = ".lshell_lock"

# help text
usage = """Usage: lshell [OPTIONS]
  --config <file>   : Config file location (default %s)
  --<param> <value> : where <param> is *any* config file parameter
  -h, --help        : Show this help message
  --version         : Show version
""" % configfile

help_help = """Limited Shell (lshell) limited help.
Cheers.
"""

# Intro Text
intro = """You are in a limited shell.
Type '?' or 'help' to get the list of allowed commands"""

# configuration parameters
configparams = [ 'config=',
                 'help',
                 'version',
                 'quiet=',
                 'log=',
                 'logpath=',
                 'loglevel=',
                 'logfilename=',
                 'syslogname=',
                 'allowed=',
                 'forbidden=',
                 'sudo_commands=',
                 'warning_counter=',
                 'aliases=',
                 'intro=',
                 'prompt=',
                 'prompt_short=',
                 'timer=',
                 'path=',
                 'home_path=',
                 'env_path=',
                 'allowed_cmd_path=',
                 'env_vars=',
                 'scp=',
                 'scp_upload=',
                 'scp_download=',
                 'sftp=',
                 'overssh=',
                 'strict=',
                 'scpforce=',
                 'history_size=',
                 'history_file=' ]


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
        configfile = self.conf['configfile']
        self.conf['config_mtime'] = self.get_config_mtime(configfile)
        self.check_file(configfile)
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

        # set configfile as default configuration file
        conf['configfile'] = configfile

        try:
            optlist, args = getopt.getopt(arguments,
                                          'hc:',
                                          configparams)
        except getopt.GetoptError:
            self.stderr.write('Missing or unknown argument(s)\n')
            self.usage()

        for option, value in optlist:
            if  option in ['--config']:
                conf['configfile'] = os.path.realpath(value)
            if  option in ['--log']:
                conf['logpath'] = os.path.realpath(value)
            if  "%s=" %option[2:] in configparams:
                conf[option[2:]] = value
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
        sys.stderr.write('lshell-%s - Limited Shell\n' % __version__)
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
                logname = self.conf['syslogname']
        else:
            logname = 'lshell'

        logger = logging.getLogger("%s.%s" % (logname, \
                                                self.conf['config_mtime']))

        # close any logger handler/filters if exists
        # this is useful if configuration is reloaded
        for loghandler in logger.handlers:
            try:
              logging.shutdown(logger.handlers)
            except TypeError:
              pass
        for logfilter in logger.filters:
            logger.removeFilter(logfilter)

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
                    # create log file if it does not exist, and set permissions
                    fp = open(logfile,'a').close()
                    os.chmod(logfile, 0600)
                    # set logging handler
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
            try:
                grpname = grp.getgrgid(gid)[0]
                section = 'grp:' + grpname
                self.get_config_sub(section)
            except KeyError:
                pass

        # get user configuration if any
        self.get_config_sub(self.user)

    def get_config_sub(self, section):
        """ this function is used to interpret the configuration +/-, 
            'all' etc.
        """
        # convert commandline options from dict to list of tuples, in order to
        # merge them with the output of the config parser
        conf = []
        for key in self.conf:
            if key not in ['config_mtime', 'logpath']:
                conf.append((key,self.conf[key]))

        if self.config.has_section(section):
            conf = self.config.items(section) + conf
            for item in conf:
                key = item[0]
                value = item[1]
                # if string, then split
                if isinstance(value, str):
                    split = re.split('([\+\-\s]+\[[^\]]+\])', value.replace(' ',
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
                                for item in glob.glob(path):
                                    liste[0] += os.path.realpath(item) + '/.*|'
                            self.conf_raw.update({key:str(liste)})
                        elif stuff and type(eval(stuff)) is list:
                            self.conf_raw.update({key:stuff})
                # case allowed is set to 'all'
                elif key == 'allowed' and split[0] == "'all'":
                    self.conf_raw.update({key:self.expand_all()})
                elif key == 'path':
                    liste = ['', '']
                    for path in self.myeval(value, 'path'):
                        for item in glob.glob(path):
                            liste[0] += os.path.realpath(item) + '/.*|'
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
                    'prompt_short',
                    'allowed_cmd_path',
                    'history_size',
                    'login_script',
                    'quiet']:
            try:
                if len(self.conf_raw[item]) == 0:
                    self.conf[item] = ""
                else:
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

        # add all commands present in allowed_cmd_path if specified
        if self.conf['allowed_cmd_path']:
            for path in self.conf['allowed_cmd_path']:
                # add path to PATH env variable
                os.environ['PATH'] += ":%s" % path
                # find executable file, and add them to allowed commands
                for item in os.listdir(path):
                    cmd = os.path.join(path, item)
                    if os.access(cmd, os.X_OK):
                        self.conf['allowed'].append(item)


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
                from lshell.shellcmd import ShellCmd
                cli = ShellCmd(self.conf, None, None, None, None,              \
                                                            self.conf['ssh'])
                if cli.check_path(self.conf['ssh'], None, ssh=1) == 1:
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

    def get_config_mtime(self, configfile):
        """ get configuration file modification time, and store in the        \
            configuration dict. This should then be used to reload the 
            configuration dynamically upon file changes
        """
        return os.path.getmtime(configfile)

    def returnconf(self):
        """ returns the configuration dict """
        return self.conf
