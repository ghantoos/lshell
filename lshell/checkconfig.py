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

import sys
import os
try:
    import configparser
except ImportError:
    import ConfigParser as configparser
from getpass import getuser
import string
import re
import getopt
import logging
import grp
import time
import glob

# import lshell specifics
from lshell import utils
from lshell import variables
from lshell import sec


class CheckConfig:
    """ Check the configuration file.
    """

    def __init__(self, args, refresh=None,
                 stdin=None, stdout=None, stderr=None):
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

        self.refresh = refresh
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
        self.set_noexec()

    def getoptions(self, arguments, conf):
        """ This method checks the usage. lshell.py must be called with a
        configuration file.
        If no configuration file is specified, it will set the configuration
        file path to /etc/lshell.conf
        """
        # set configfile as default configuration file
        conf['configfile'] = variables.configfile

        try:
            optlist, args = getopt.getopt(arguments,
                                          'hc:',
                                          variables.configparams)
        except getopt.GetoptError:
            self.stderr.write('Missing or unknown argument(s)\n')
            utils.usage()

        for option, value in optlist:
            if option in ['--config']:
                conf['configfile'] = os.path.realpath(value)
            if option in ['--log']:
                conf['logpath'] = os.path.realpath(value)
            if "%s=" % option[2:] in variables.configparams:
                conf[option[2:]] = value
            if option in ['-c']:
                conf['ssh'] = value
            if option in ['-h', '--help']:
                utils.usage()
            if option in ['--version']:
                utils.version()

        # put the expanded path of configfile and logpath (if exists) in
        # LSHELL_ARGS environment variable
        args = ['--config', conf['configfile']]
        if 'logpath' in conf:
            args += ['--log', conf['logpath']]
        os.environ['LSHELL_ARGS'] = str(args)

        # if lshell is invoked using shh autorized_keys file e.g.
        # command="/usr/bin/lshell", ssh-dss ....
        if 'SSH_ORIGINAL_COMMAND' in os.environ:
            conf['ssh'] = os.environ['SSH_ORIGINAL_COMMAND']

        return conf, args

    def check_env(self):
        """ Load environment variable set in configuration file """
        if 'env_vars' in self.conf:
            env_vars = self.conf['env_vars']
            for key in env_vars.keys():
                os.environ[key] = str(env_vars[key])

    def check_file(self, file):
        """ This method checks the existence of the given configuration
            file passed via command line arguments
        """
        if not os.path.exists(file):
            self.stderr.write("Error: Config file doesn't exist\n")
            self.stderr.write(variables.usage)
            sys.exit(1)
        else:
            self.config = configparser.ConfigParser()

    def get_global(self):
        """ Loads the [global] parameters from the configuration file
        """
        try:
            self.config.read(self.conf['configfile'])
        except (configparser.MissingSectionHeaderError,
                configparser.ParsingError) as argument:
            self.stderr.write('ERR: %s\n' % argument)
            sys.exit(1)

        if not self.config.has_section('global'):
            self.stderr.write('Config file missing [global] section\n')
            sys.exit(1)

        for item in self.config.items('global'):
            if item[0] not in self.conf:
                self.conf[item[0]] = item[1]

    def check_log(self):
        """ Sets the log level and log file
        """
        # define log levels dict
        self.levels = {1: logging.CRITICAL,
                       2: logging.ERROR,
                       3: logging.WARNING,
                       4: logging.DEBUG}

        # create logger for lshell application
        if 'syslogname' in self.conf:
            try:
                logname = eval(self.conf['syslogname'])
            except:
                logname = self.conf['syslogname']
        else:
            logname = 'lshell'

        logger = logging.getLogger("%s.%s" % (logname,
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

        formatter = logging.Formatter('%%(asctime)s (%s): %%(message)s'
                                      % getuser())
        syslogformatter = logging.Formatter('%s[%s]: %s: %%(message)s'
                                            % (logname,
                                               os.getpid(),
                                               getuser()))

        logger.setLevel(logging.DEBUG)

        # set log to output error on stderr
        logsterr = logging.StreamHandler()
        logger.addHandler(logsterr)
        logsterr.setFormatter(logging.Formatter('%(message)s'))
        logsterr.setLevel(logging.CRITICAL)

        # log level must be 1, 2, 3 , 4 or 0
        if 'loglevel' not in self.conf:
            self.conf['loglevel'] = 0
        try:
            self.conf['loglevel'] = int(self.conf['loglevel'])
        except ValueError:
            self.conf['loglevel'] = 0
        if self.conf['loglevel'] > 4:
            self.conf['loglevel'] = 4
        elif self.conf['loglevel'] < 0:
            self.conf['loglevel'] = 0

        # read logfilename is exists, and set logfilename
        if 'logfilename' in self.conf:
            try:
                logfilename = eval(self.conf['logfilename'])
            except:
                logfilename = self.conf['logfilename']
            currentime = time.localtime()
            logfilename = logfilename.replace('%y', '%s' % currentime[0])
            logfilename = logfilename.replace('%m', '%02d' % currentime[1])
            logfilename = logfilename.replace('%d', '%02d' % currentime[2])
            logfilename = logfilename.replace('%h', '%02d%02d'
                                                    % (currentime[3],
                                                       currentime[4]))
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
                    logfile = os.path.join(self.conf['logpath'],
                                           logfilename + '.log')
                    # create log file if it does not exist, and set permissions
                    fp = open(logfile, 'a')
                    fp.close()
                    try:
                        os.chmod(logfile, 0o600)
                    except OSError:
                        pass
                    # set logging handler
                    self.logfile = logging.FileHandler(logfile)
                    self.logfile.setFormatter(formatter)
                    self.logfile.setLevel(self.levels[self.conf['loglevel']])
                    logger.addHandler(self.logfile)

            except IOError:
                pass

        self.conf['logpath'] = logger
        self.log = logger

    def get_config(self):
        """ Load default, group and user configuration. Then merge them all.
        The load priority is done in the following order:
            1- User section
            2- Group section
            3- Default section
        """
        self.config.read(self.conf['configfile'])

        # list the include_dir directory and read configuration files
        if 'include_dir' in self.conf:
            import glob
            self.conf['include_dir_conf'] = glob.glob("%s*" %
                                                      self.conf['include_dir'])
            self.config.read(self.conf['include_dir_conf'])

        self.user = getuser()

        self.conf_raw = {}

        # get 'default' configuration if any
        self.get_config_sub('default')

        # get groups configuration if any.
        # for each group the user belongs to, check if specific configuration
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
                conf.append((key, self.conf[key]))

        if self.config.has_section(section):
            conf = self.config.items(section) + conf
            for item in conf:
                key = item[0]
                value = item[1]
                # if string, then split
                split = ['']
                if isinstance(value, str):
                    split = re.split('([\+\-\s]+\[[^\]]+\])',
                                     value.replace(' ', ''))
                if len(split) > 1 and key in ['path',
                                              'overssh',
                                              'allowed',
                                              'allowed_shell_escape',
                                              'forbidden']:
                    for stuff in split:
                        if stuff.startswith('-') or stuff.startswith('+'):
                            self.conf_raw.update(self.minusplus(self.conf_raw,
                                                                key, stuff))
                        elif stuff == "'all'":
                            self.conf_raw.update({key: self.expand_all()})
                        elif stuff and key == 'path':
                            liste = ['', '']
                            for path in eval(stuff):
                                for item in glob.glob(path):
                                    liste[0] += os.path.realpath(item) + '/.*|'
                            # remove double slashes
                            liste[0] = liste[0].replace("//", "/")
                            self.conf_raw.update({key: str(liste)})
                        elif stuff and type(eval(stuff)) is list:
                            self.conf_raw.update({key: stuff})
                # case allowed is set to 'all'
                elif key == 'allowed' and split[0] == "'all'":
                    self.conf_raw.update({key: self.expand_all()})
                elif key == 'path':
                    liste = ['', '']
                    for path in self.myeval(value, 'path'):
                        for item in glob.glob(path):
                            liste[0] += os.path.realpath(item) + '/.*|'
                    # remove double slashes
                    liste[0] = liste[0].replace("//", "/")
                    self.conf_raw.update({key: str(liste)})
                else:
                    self.conf_raw.update(dict([item]))

    def minusplus(self, confdict, key, extra):
        """ update configuration lists containing -/+ operators
        """
        if key in confdict:
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
                        self.log.error("CONF: -['%s'] ignored in '%s' list."
                                       % (item, key))
        return {key: str(liste)}

    def expand_all(self):
        """ expand allowed, if set to 'all'
        """
        # initialize list to common shell built-ins
        expanded_all = ['bg', 'break', 'case', 'cd', 'continue', 'eval',
                        'exec', 'exit', 'fg', 'if', 'jobs', 'kill', 'login',
                        'logout', 'set', 'shift', 'stop', 'suspend', 'umask',
                        'unset', 'wait', 'while']
        for directory in os.environ['PATH'].split(':'):
            if os.path.exists(directory):
                for item in os.listdir(directory):
                    if os.access(os.path.join(directory, item), os.X_OK):
                        expanded_all.append(item)
            else:
                self.log.error('CONF: PATH entry "%s" does not exist'
                               % directory)

        return str(expanded_all)

    def myeval(self, value, info=''):
        """ if eval returns SyntaxError, log it as critical conf missing """
        try:
            evaluated = eval(value)
            return evaluated
        except SyntaxError:
            self.log.critical('CONF: Incomplete %s field in configuration file'
                              % info)
            sys.exit(1)

    def check_user_integrity(self):
        """ This method checks if all the required fields by user are present
        for the present user.
        In case fields are missing, the user is notified and exited from lshell
        """
        for item in variables.required_config:
            if item not in self.conf_raw.keys():
                self.log.critical("ERROR: Missing parameter '%s'" % item)
                self.log.critical('ERROR: Add it in the in the [%s] '
                                  'or [default] section of conf file.'
                                  % self.user)
                sys.exit(1)

    def get_config_user(self):
        """ Once all the checks above have passed, the configuration files
        values are entered in a dict to be used by the command line it self.
        The lshell command line is then launched!
        """
        # first, check user's loglevel
        if 'loglevel' in self.conf_raw:
            try:
                self.conf['loglevel'] = int(self.conf_raw['loglevel'])
            except ValueError:
                pass
            if self.conf['loglevel'] > 4:
                self.conf['loglevel'] = 4
            elif self.conf['loglevel'] < 0:
                self.conf['loglevel'] = 0

            # if log file exists:
            try:
                self.logfile.setLevel(self.levels[self.conf['loglevel']])
            except AttributeError:
                pass

        for item in ['allowed',
                     'allowed_shell_escape',
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
                     'winscp',
                     'disable_exit',
                     'quiet']:
            try:
                if len(self.conf_raw[item]) == 0:
                    self.conf[item] = ""
                else:
                    self.conf[item] = self.myeval(self.conf_raw[item], item)
            except KeyError:
                if item in ['allowed',
                            'allowed_shell_escape',
                            'overssh',
                            'sudo_commands']:
                    self.conf[item] = []
                elif item in ['history_size']:
                    self.conf[item] = -1
                # default scp is allowed
                elif item in ['scp_upload', 'scp_download']:
                    self.conf[item] = 1
                elif item in ['aliases', 'env_vars']:
                    self.conf[item] = {}
                # do not set the variable
                elif item in ['prompt']:
                    continue
                else:
                    self.conf[item] = 0
            except TypeError:
                self.log.critical('ERR: in the -%s- field. Check the'
                                  ' configuration file.' % item)
                sys.exit(1)

        self.conf['username'] = self.user

        if 'home_path' in self.conf_raw:
            home_path = self.conf_raw['home_path']
            home_path = home_path.replace("%u", self.conf['username'])
            self.conf_raw['home_path'] = home_path
            self.conf['home_path'] = os.path.normpath(
                self.myeval(
                    self.conf_raw['home_path'],
                    'home_path'))
        else:
            self.conf['home_path'] = os.environ['HOME']

        # initialize previous path to home path
        self.conf['oldpwd'] = self.conf['home_path']

        if 'path' in self.conf_raw:
            self.conf['path'] = eval(self.conf_raw['path'])
            self.conf['path'][0] += self.conf['home_path'] + '.*'
        else:
            self.conf['path'] = ['', '']
            self.conf['path'][0] = self.conf['home_path'] + '.*'

        if 'env_path' in self.conf_raw:
            self.conf['env_path'] = self.myeval(self.conf_raw['env_path'],
                                                'env_path')
        else:
            self.conf['env_path'] = ''

        if 'scpforce' in self.conf_raw:
            self.conf_raw['scpforce'] = self.myeval(
                self.conf_raw['scpforce'])
            try:
                if os.path.exists(self.conf_raw['scpforce']):
                    self.conf['scpforce'] = self.conf_raw['scpforce']
                else:
                    self.log.error('CONF: scpforce no such directory: %s'
                                   % self.conf_raw['scpforce'])
            except TypeError:
                self.log.error('CONF: scpforce must be a string!')

        if 'intro' in self.conf_raw:
            self.conf['intro'] = self.myeval(self.conf_raw['intro'])
        else:
            self.conf['intro'] = variables.intro

        if os.path.isdir(self.conf['home_path']):
            # change dir to home when initially loading the configuration
            if self.refresh is None:
                os.chdir(self.conf['home_path'])
            # if reloading the configuration, do not change directory
            else:
                pass
        else:
            self.log.critical('ERR: home directory "%s" does not exist.'
                              % self.conf['home_path'])
            sys.exit(1)

        if 'history_file' in self.conf_raw:
            try:
                self.conf['history_file'] = eval(
                    self.conf_raw['history_file'].replace(
                        "%u", self.conf['username']))
            except:
                self.log.error('CONF: history file error: %s'
                               % self.conf['history_file'])
        else:
            self.conf['history_file'] = variables.history_file

        if not self.conf['history_file'].startswith('/'):
            self.conf['history_file'] = "%s/%s" % (self.conf['home_path'],
                                                   self.conf['history_file'])

        os.environ['PATH'] = os.environ['PATH'] + self.conf['env_path']

        # append default commands to allowed list
        self.conf['allowed'] += list(set(variables.builtins_list) -
                                     set(['export']))

        # in case sudo_commands is not empty, append sudo to allowed commands
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

        # case sudo_commands set to 'all', expand to all 'allowed' commands
        if 'sudo_commands' in self.conf_raw \
           and self.conf_raw['sudo_commands'] == 'all':
            # exclude native commands and sudo(8)
            exclude = variables.builtins_list + ['sudo']
            self.conf['sudo_commands'] = [x for x in self.conf['allowed']
                                          if x not in exclude]

        # sort lsudo commands
        self.conf['sudo_commands'].sort()

        # in case winscp is set, load the needed configuration
        if 'winscp' in self.conf and self.conf['winscp'] == 1:
            # add minimum commands required for WinSCP to work
            self.conf['allowed'].extend(['scp', 'env', 'pwd',
                                         'groups', 'unset', 'unalias'])
            # remove duplicate commands, in case added in the above extension
            self.conf['allowed'] = list(set(self.conf['allowed']))
            # allow the use of semicolon
            if ';' in self.conf['forbidden']:
                self.conf['forbidden'].remove(';')

            self.log.error('WinSCP session started')

    def check_scp_sftp(self):
        """ This method checks if the user is trying to SCP a file onto the
        server. If this is the case, it checks if the user is allowed to use
        SCP or not, and    acts as requested. : )
        """
        if 'ssh' in self.conf:
            if 'SSH_CLIENT' in os.environ \
               and 'SSH_TTY' not in os.environ:

                # check if sftp is requested and allowed
                if 'sftp-server' in self.conf['ssh']:
                    if self.conf['sftp'] == 1:
                        self.log.error('SFTP connect')
                        retcode = utils.exec_cmd(self.conf['ssh'])
                        self.log.error('SFTP disconnect')
                        sys.exit(retcode)
                    else:
                        self.log.error('*** forbidden SFTP connection')
                        sys.exit(1)

                # initialize cli session
                from lshell.shellcmd import ShellCmd
                cli = ShellCmd(self.conf,
                               None, None, None, None,
                               self.conf['ssh'])
                ret_check_path, self.conf = sec.check_path(self.conf['ssh'],
                                                           self.conf,
                                                           ssh=1)
                if ret_check_path == 1:
                    self.ssh_warn('path over SSH', self.conf['ssh'])

                # check if scp is requested and allowed
                if self.conf['ssh'].startswith('scp '):
                    if self.conf['scp'] == 1 or 'scp' in self.conf['overssh']:
                        if ' -f ' in self.conf['ssh']:
                            # case scp download is allowed
                            if self.conf['scp_download']:
                                self.log.error('SCP: GET "%s"'
                                               % self.conf['ssh'])
                            # case scp download is forbidden
                            else:
                                self.log.error('SCP: download forbidden: "%s"'
                                               % self.conf['ssh'])
                                sys.exit(1)
                        elif ' -t ' in self.conf['ssh']:
                            # case scp upload is allowed
                            if self.conf['scp_upload']:
                                if 'scpforce' in self.conf:
                                    cmdsplit = self.conf['ssh'].split(' ')
                                    scppath = os.path.realpath(cmdsplit[-1])
                                    forcedpath = os.path.realpath(self.conf
                                                                  ['scpforce'])
                                    if scppath != forcedpath:
                                        self.log.error('SCP: forced SCP '
                                                       'directory: %s'
                                                       % scppath)
                                        cmdsplit.pop(-1)
                                        cmdsplit.append(forcedpath)
                                        self.conf['ssh'] = string.join(
                                            cmdsplit)
                                self.log.error('SCP: PUT "%s"'
                                               % self.conf['ssh'])
                            # case scp upload is forbidden
                            else:
                                self.log.error('SCP: upload forbidden: "%s"'
                                               % self.conf['ssh'])
                                sys.exit(1)
                        retcode = utils.exec_cmd(self.conf['ssh'])
                        self.log.error('SCP disconnect')
                        sys.exit(retcode)
                    else:
                        self.ssh_warn('SCP connection',
                                      self.conf['ssh'],
                                      'scp')

                # check if command is in allowed overssh commands
                elif self.conf['ssh']:
                    # replace aliases
                    self.conf['ssh'] = utils.get_aliases(self.conf['ssh'],
                                                         self.conf['aliases'])
                    # if command is not "secure", exit
                    ret_check_secure, self.conf = sec.check_secure(
                        self.conf['ssh'],
                        self.conf,
                        strict=1,
                        ssh=1)
                    if ret_check_secure:
                        self.ssh_warn('char/command over SSH',
                                      self.conf['ssh'])
                    # else
                    self.log.error('Over SSH: "%s"' % self.conf['ssh'])
                    # if command is "help"
                    if self.conf['ssh'] == "help":
                        cli.do_help(None)
                        retcode = 0
                    else:
                        retcode = utils.exec_cmd(self.conf['ssh'])
                    self.log.error('Exited')
                    sys.exit(retcode)

                # else warn and log
                else:
                    self.ssh_warn('command over SSH', self.conf['ssh'])

            else:
                # case of shell escapes
                self.ssh_warn('shell escape', self.conf['ssh'])

    def ssh_warn(self, message, command='', key=''):
        """ log and warn if forbidden action over SSH """
        if key == 'scp':
            self.log.critical('*** forbidden %s' % message)
            self.log.error('*** SCP command: %s' % command)
        else:
            self.log.critical('*** forbidden %s: "%s"' % (message, command))
        self.stderr.write('This incident has been reported.\n')
        self.log.error('Exited')
        sys.exit(1)

    def set_noexec(self):
        """ This method checks the existence of the sudo_noexec library.
        """
        # list of standard sudo_noexec.so file location
        possible_lib = ['/lib/sudo_noexec.so',
                        '/usr/lib/sudo_noexec.so',
                        '/usr/lib/sudo/sudo_noexec.so',
                        '/usr/libexec/sudo_noexec.so',
                        '/usr/libexec/sudo/sudo_noexec.so',
                        '/usr/local/lib/sudo_noexec.so',
                        '/usr/local/lib/sudo/sudo_noexec.so',
                        '/usr/local/libexec/sudo_noexec.so',
                        '/usr/local/libexec/sudo/sudo_noexec.so',
                        '/usr/pkg/libexec/sudo_noexec.so',
                        '/lib64/sudo_noexec.so',
                        '/usr/lib64/sudo/sudo_noexec.so']

        # check if alternative path is set in configuration file
        if 'path_noexec' in self.conf_raw:
            self.conf['path_noexec'] = self.myeval(
                self.conf_raw['path_noexec'])
            # if path_noexec is empty, disable LD_PRELOAD
            # /!\ this feature should be used at the administrator's own risks!
            if self.conf['path_noexec'] == '':
                return
            if not os.path.exists(self.conf['path_noexec']):
                self.log.critical(
                    "Fatal: 'path_noexec': %s No such file of directory"
                    % (self.conf['path_noexec']))
                sys.exit(2)
        else:
            # go through the list of standard lib locations
            for path_lib in possible_lib:
                if os.path.exists(path_lib):
                    self.conf['path_noexec'] = path_lib
                    break

        # in case the library was found, set the LD_PRELOAD aliases
        if 'path_noexec' in self.conf:
            # exclude allowed_shell_escape commands from loop
            exclude_se = list(set(self.conf['allowed']) -
                              set(self.conf['allowed_shell_escape']) -
                              set(variables.builtins_list))

            for cmd in exclude_se:
                # take already set aliases into consideration
                if cmd in self.conf['aliases']:
                    cmd = self.conf['aliases'][cmd]

                # add an alias to all the commands, prepending with LD_PRELOAD=
                # except for built-in commands
                if cmd not in variables.builtins_list:
                    self.conf['aliases'][cmd] = 'LD_PRELOAD=%s %s' % (
                                                self.conf['path_noexec'],
                                                cmd)
        else:
            # if sudo_noexec.so file is not found,  write error in log file,
            # but don't exit tp  prevent strict dependency on sudo noexec lib
            self.log.error("Error: noexec library not found")

        self.conf['allowed'] += self.conf['allowed_shell_escape']

    def get_config_mtime(self, configfile):
        """ get configuration file modification time, and store in the
            configuration dict. This should then be used to reload the
            configuration dynamically upon file changes
        """
        return os.path.getmtime(configfile)

    def returnconf(self):
        """ returns the configuration dict """
        return self.conf
