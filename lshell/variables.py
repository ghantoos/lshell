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

__version__ = "0.9.18"

# Required config variable list per user
required_config = ['allowed', 'forbidden', 'warning_counter']

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

# help text
usage = """Usage: lshell [OPTIONS]
  --config <file>   : Config file location (default %s)
  --<param> <value> : where <param> is *any* config file parameter
  -h, --help        : Show this help message
  --version         : Show version
""" % configfile

# Intro Text
intro = """You are in a limited shell.
Type '?' or 'help' to get the list of allowed commands"""
# configuration parameters
configparams = ['config=',
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
                'history_file=',
                'path_noexec=',
                'allowed_shell_escape=',
                'winscp=',
                'disable_exit=',
                'include_dir=']

builtins_list = ['cd',
                 'clear',
                 'exit',
                 'export',
                 'history',
                 'lpath',
                 'lsudo']

FORBIDDEN_ENVIRON = (
    'LD_AOUT_LIBRARY_PATH', 'LD_AOUT_PRELOAD', 'LD_LIBRARY_PATH', 'LD_PRELOAD',
    'LD_ORIGIN_PATH', 'LD_DEBUG_OUTPUT', 'LD_PROFILE', 'GCONV_PATH',
    'HOSTALIASES', 'LOCALDOMAIN', 'LOCPATH', 'MALLOC_TRACE', 'NLSPATH',
    'RESOLV_HOST_CONF', 'RES_OPTIONS', 'TMPDIR', 'TZDIR', 'LD_USE_LOAD_BIAS',
    'LD_DEBUG', 'LD_DYNAMIC_WEAK', 'LD_SHOW_AUXV', 'GETCONF_DIR', 'LD_AUDIT',
    'NIS_PATH', 'PATH'
)
