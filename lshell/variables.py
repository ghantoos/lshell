"""This file contains all the variables used in lshell"""

import sys
import os

__version__ = "0.11.1rc3"

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
  --security_audit_json=<0|1> : Emit structured JSON/ECS security audit events
  -h, --help        : Show this help message
  --version         : Show version

Usage: lshell policy-show [OPTIONS] --command <CMD>
  --config <file>   : Config file location (default {configfile})
  --user <name>     : Target username
  --group <name>    : Target group (repeat for multiple groups)
  --json            : Print JSON diagnostics output

Usage: lshell setup-system [OPTIONS]
  --group <name>            : Group for log directory (default lshell)
  --log-dir <path>          : Log directory path (default /var/log/lshell)
  --owner <user>            : Log directory owner (default root)
  --mode <octal>            : Log directory mode (default 2770)
  --set-shell-user <name>   : Assign lshell as login shell (repeatable)
  --add-group-user <name>   : Add user to log-writer group (repeatable)

Usage: lshell harden-init [OPTIONS]
  --list-templates          : List available hardened templates
  --profile <name>          : Template name (sftp-only, rsync-backup, deploy-minimal, readonly-support)
  --group <name>            : Add scoped [grp:<name>] section (repeatable)
  --user <name>             : Add scoped [user:<name>] section (repeatable)
  --output <path>           : Write rendered config file to path (default /etc/lshell.d/<profile>.conf)
  --stdout                  : Print rendered config to stdout
  --dry-run                 : Render and run sanity checks without writing
  --explain                 : Print profile hardening rationale
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
    "allowed_file_extensions=",
    "forbidden=",
    "sudo_commands=",
    "warning_counter=",
    "aliases=",
    "messages=",
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
    "umask=",
    "allowed_shell_escape=",
    "winscp=",
    "disable_exit=",
    "policy_commands=",
    "include_dir=",
    "security_audit_json=",
    "max_sessions_per_user=",
    "max_background_jobs=",
]

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

# Single source of truth for trusted SFTP protocol executables.
TRUSTED_SFTP_PROTOCOL_BINARIES = (
    "sftp-server",
    "/usr/libexec/sftp-server",
    "/usr/lib/ssh/sftp-server",
    "/usr/lib/openssh/sftp-server",
    "/usr/libexec/openssh/sftp-server",
)
