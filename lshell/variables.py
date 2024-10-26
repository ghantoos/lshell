""" This file contains all the variables used in lshell """

import sys
import os

__version__ = "0.10.3"

# Required config variable list per user
required_config = ["allowed", "forbidden", "warning_counter"]

# set configuration file path depending on sys.exec_prefix
# on *Linux sys.exec_prefix = '/usr' and default path must be in '/etc'
# on *BSD sys.exec_prefix = '/usr/{pkg,local}/' and default path
# is '/usr/{pkg,local}/etc'
lshell_path = os.path.abspath(__file__).split("/lib/")[0]
if sys.exec_prefix != "/usr":
    # for *BSD
    CONF_PREFIX = sys.exec_prefix
elif lshell_path == "/home/ghantoos/.local":
    # for *Linux user install
    CONF_PREFIX = lshell_path
else:
    # for *Linux system-wide install
    CONF_PREFIX = ""
configfile = CONF_PREFIX + "/etc/lshell.conf"

# history file
HISTORY_FILE = ".lhistory"

# help text
USAGE = f"""Usage: lshell [OPTIONS]
  --config <file>   : Config file location (default {configfile})
  --<param> <value> : where <param> is *any* config file parameter
  -h, --help        : Show this help message
  --version         : Show version
"""

# Intro Text
INTRO = """You are in a limited shell.
Type '?' or 'help' to get the list of allowed commands"""

# configuration parameters
configparams = [
    "config=",
    "help",
    "version",
    "quiet=",
    "log=",
    "logpath=",
    "loglevel=",
    "logfilename=",
    "syslogname=",
    "allowed=",
    "forbidden=",
    "sudo_commands=",
    "warning_counter=",
    "aliases=",
    "intro=",
    "prompt=",
    "prompt_short=",
    "timer=",
    "path=",
    "home_path=",
    "env_path=",
    "allowed_cmd_path=",
    "env_vars=",
    "env_vars_files=",
    "scp=",
    "scp_upload=",
    "scp_download=",
    "sftp=",
    "overssh=",
    "strict=",
    "scpforce=",
    "history_size=",
    "history_file=",
    "path_noexec=",
    "allowed_shell_escape=",
    "winscp=",
    "disable_exit=",
    "include_dir=",
]

builtins_list = ["cd", "clear", "exit", "export", "history", "lpath", "lsudo", "help"]

FORBIDDEN_ENVIRON = (
    "LD_AOUT_LIBRARY_PATH",
    "LD_AOUT_PRELOAD",
    "LD_LIBRARY_PATH",
    "LD_PRELOAD",
    "LD_ORIGIN_PATH",
    "LD_DEBUG_OUTPUT",
    "LD_PROFILE",
    "GCONV_PATH",
    "HOSTALIASES",
    "LOCALDOMAIN",
    "LOCPATH",
    "MALLOC_TRACE",
    "NLSPATH",
    "RESOLV_HOST_CONF",
    "RES_OPTIONS",
    "TMPDIR",
    "TZDIR",
    "LD_USE_LOAD_BIAS",
    "LD_DEBUG",
    "LD_DYNAMIC_WEAK",
    "LD_SHOW_AUXV",
    "GETCONF_DIR",
    "LD_AUDIT",
    "NIS_PATH",
    "PATH",
)
