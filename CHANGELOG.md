# LSHELL - Limited Shell - CHANGELOG

Contact: [ghantoos@ghantoos.org](mailto:ghantoos@ghantoos.org)  
[https://github.com/ghantoos/lshell](https://github.com/ghantoos/lshell)


### v0.10.5 26/10/2024
- Fixed parsing and testing of the over SSH commands. Corrected return codes over SSH.

### v0.10.4 26/10/2024
- Feature: Allow commands with specific parameters, e.g., `telnet localhost`. Adding `telnet localhost` to the `allowed` configuration will not permit the `telnet` command by itself but will only allow the exact match `telnet localhost`.

### v0.10.2 24/10/2024
- Make env_path have precedence over the OS path ($env_path:$PATH)
- Test auto-release via Pypi

### v0.10.1 24/10/2024
- Add the ability to write and execute a lshell script (`#!/usr/bin/lshell`)
- Added Pypi package
- Code cleanup and testing

### v0.10 17/10/2024
- Fixed security issues CVE-2016-6902, CVE-2016-6903
  - [CVE-2016-6902](https://nvd.nist.gov/vuln/detail/CVE-2016-6902)
  - [CVE-2016-6903](https://nvd.nist.gov/vuln/detail/CVE-2016-6903)
- Fixed parser to better support operators like `||` and `&&`
- Added support for `ctrl-z`: lshell no longer runs in the background when `ctrl-z` is used
- Added `env_vars_files` feature: enables adding environment variables in a file and loading it at login
- Improved Python3 compatibility & general code refresh
- Removed the `help_help()` function

### v0.9.18 24/02/2016
- Corrected exit codes of built-in commands
- Added default support for `sudo_noexec.so` in `LD_PRELOAD`. This feature comes with a new variable `allowed_shell_escape` to allow admins to escape the new default behavior. Thank you Luca Berra for this contribution!
- Added Python3 compatibility. Thank you Tristan Cacqueray for your help!
- Added restricted environment variables that cannot be updated by user. Thank you Tristan Cacqueray for this contribution!
- Added `export` command in built-ins
- Added WinSCP support. Thank you @faberge-eggs for this contribution!
- Added tox testing. Thank you Tristan Cacqueray for your contribution!
- Correct logrotate configuration. Thank you Rune Schjellerup Philosof for your patch suggestion.
- Code cleanup (More information in the git commit log)

### v0.9.17 14/08/2015
- Added `include_dir` directive to include split configuration files from a directory.
- Added possibility of using 'all' for sudo commands
- Replaced `os.system` by `subprocess` (python)
- Added support for `sudo -u`
- Corrected shell variable expansion
- Corrected bugs in aliases support
- Fixed timer (idle session)
- Added exit code support
- Fixed wrong group reference for logging
- Replaced Python `os.system` with `subprocess`

### v0.9.16 14/08/2013
- Added support to login script. Thank you Laurent Debacker for the patch.
- Fixed auto-complete failing with "-"
- Fixed bug where forbidden commands still execute if `strict=1`
- Fixed auto-completion complete of forbidden paths 
- Fixed wrong parsing `&`, `|` or `;` characters
- Added `urandom` function definition for python 2.3 compat
- Corrected env variable expansion
- Add support for `cd` command in aliases
- Split `lshellmodule` in multiple files under the `lshell` directory
- Fixed `check_secure` function to ignore quoted text 
- Fixed multiple spaces escaping forbidden filtering
- Fixed log file permissions `644 -> 600`
- Added possibility to override config file option via command-line
- Enabled job control when executing command
- Code cleanup

### v0.9.15.2 08/05/2012
- Corrected mismatch in `aliaskey` variable.

### v0.9.15.1 15/03/2012
- Corrected security bug allowing user to get out of the restricted shell. Thank you bui from NBS System for reporting this grave issue!

### v0.9.15 13/03/2012
- Set the hostname to the "short hostname" in the prompt.
- Corrected traceback when "sudo" command was entered alone. Thank you Kiran Reddy for reporting this.
- Added support for python2.3 as `subprocess` is not included by default.
- Corrected the `strict` behavior when entering a forbidden path.
- Added short path prompt support using the `prompt_short` variable.
- Corrected stacktrace when group did not exist.
- Add support for empty prompt.
- Fixed bugs when using `$()` and ``.
- Corrected strict behavior to apply to forbidden path.
- Added support for wildcard `*` when using `cd`.
- Added support for `cd -` to return to previous directory.
- Updated security issue with non-printable characters permitting user to get out of the limited shell.
- Now lshell automatically reloads its configuration if the configuration file is modified.
- Added possibility to have no "intro" when user logs in (by setting the intro configuration field to "").
- Corrected multiple commands over ssh, and aliases interpretation.
- Added possibility to use wildcards in path definitions.
- Finally corrected the alias replacement loop.

### v0.9.14 27/10/2010
- Corrected `get_aliases` function, as it was looping when aliases were "recursive" (e.g. `ls:ls --color=auto`)
- Added `lsudo` built-in command to list allowed sudo commands.
- Corrected completion function when 2 strings collided (e.g. `ls` and `lsudo`)
- Corrected the README's installation part (adding `--prefix`).
- Added possibility to log via syslog.
- Corrected warning counter (was counting minus 1).
- Added the possibility to disable the counter, and just warn the user (without kicking him).
- Added possibility to configure prompt. Thank you bapt for the patch.
- Added possibility to set environment variables to users. Thank you bapt for the patch.
- Added the `history` built-in function.

### v0.9.13 02/09/2010
- Switched from deprecated `popen2` to `subprocess` to be python2.6 compatible. Thank you Greg Orlowski for the patch.
- Added missing built-in commands when `allowed` list was set to `all`. For example, the `cd` command was then missing.
- Added the `export` built-in function to export shell variables. Thank you Chris for reporting this issue.

### v0.9.12 04/05/2010
- A minor bug was inserted in version 0.9.11 with the sudo command. It has been corrected in this version.

### v0.9.11 27/04/2010
- Corrects traceback when executing a command that had a python homonym (e.g. `print foo` or `set`). (Closes: SF#2969631)
- Corrected completion error when using `~/`. Thanks to Piotr Minkina for reporting this.
- Corrected the `get_aliases` function.
- Corrected interpretation of `~user`. Thank you Adrien Urban for reporting this.
- The `home_path` variable is being deprecated from this version and on. Please use your system's tools to set a user's home directory. It will be completely removed in the next version of lshell.
- Corrected shell variable and wildcards expansions when checking a command. Thank you Adrien Urban for reporting this.
- Added possibility to allow/forbid scp upload/download using `scp_upload` and `scp_download` variables.
- Corrected bug when using the `command=` in openSSH's `authorized_keys`. lshell now takes into account the `SSH_ORIGINAL_COMMAND` environment variable. Thank you Jason Heiss for reporting this.
- Corrected traceback when aliases is not defined in configuration, and command is sent over SSH. Thank you Jason Heiss for reporting this.

### v0.9.10 08/03/2010
- Corrected minor bug in the aliases function that appeared in the previous version. Thank you Piotr Minkina for reporting this.

### v0.9.9 07/03/2010
- Added the possibility to configure introduction prompt.
- Replaced "joker" by "warnings" (more elegant)
- Possibility of limiting the history file size.
- Added `lpath` built-in command to list allowed and denied path. Thanks to Adrien Urban.
- Corrected bug when using `~` was not parsed as "home directory" when used in a command other than `cd`. Thank you Adrien Urban for finding this.
- Corrected minor typo when warning for a forbidden path.
- If `$(foo)` is present in the line, check if `foo` is allowed before executing the line. Thank you Adrien Urban for pointing this out!
- Added the possibility to list commands allowed to be executed using sudo. The new configuration field is `sudo_commands`.
- Added the `clear(1)` command as a built-in command.
- Added `$(` and `${` in the forbidden list by default in the configuration file.
- Now check the content of curly braces with variables `${}`. Thank you Adrien Urban for reporting this.
- Added possibility to set history file name using `history_file` in the configuration file.
- Corrected the bug when using `|`, `&` or `;` over ssh. Over ssh forbidden characters refer now to the list provided in the `forbidden` field. Thank you Jools Wills for reporting this!
- It now possible to use `&&` and `||` even if `&` and/or `|` are in the forbidden list. In order to forbid them too, you must add them explicitly in the forbidden list. Thank you Adrien Urban for this suggestion.
- Fixed aliases bug that replaced part of commands rendering them unusable. e.g. alias `vi:vim` replaced the `view` command by `vimew`.
- Added a logrotate file for lshell log files.
- Corrected parsing of commands over ssh to be checked by the same function used by the lshell CLI.

  Thank you Adrien Urban for your security audit and excellent ideas!

### v0.9.8 30/11/2009
- Major bug fix. lshell did not launch on python 2.4 and 2.5 ([sourceforge](https://sourceforge.net/projects/lshell/forums/forum/778301/topic/3474668))
- Added aliases for commands over SSH.

### v0.9.7 25/11/2009
- Cleaned up the Python code
- Corrected crash when directory permission denied ([sourceforge](https://sourceforge.net/tracker/?func=detail&aid=2875374&group_id=215792&atid=1035093))
- Added possibility to set the `home_path` option using the `%u` flag (e.g. `/var/chroot/%u` where `%u` will be replaced by the user's username)
- Now replaces `~` by user's home directory.

### v0.9.6 9/09/2009
- Major security fix. User had access to all files located in forbidden directories ([sourceforge](https://sourceforge.net/tracker/?func=detail&aid=2838542&group_id=215792&atid=1035093))
- Corrects RPM generation bug ([sourceforge](https://sourceforge.net/tracker/index.php?func=detail&aid=2838283&group_id=215792&atid=1035093))
- lshell exits gracefully when user home directory doesn't exist

### v0.9.5 28/07/2009
- Minor release
- Changed lshell's group from `lshellg` to `lshell` (this should not have an impact on older installations)
- Minor typo correction in the `lshell.py` code

### v0.9.4 09/06/2009
- Log file name is now configurable using `logfilename` variable inside the configuration file
- Corrected aliases in `lshell.conf` to work with *BSD

### v0.9.3 13/04/2009
- Corrected major bug (alias related)

### v0.9.2 05/04/2009
- Added Force SCP directory feature
- Added command alias feature

### v0.9.1 24/03/2009
- `loglevel` can now be defined on global, group or user level 
- Corrected sftp support (broken since in 0.9.0)

### v0.9.0 20/03/2009
- As lshell has reached the point where it can be considered as a nearly stable software. I decided to make a version jump to 0.9.0
- Corrected bug in case `PATH` does not exist and `allowed` set to `all`
- Added support for UNIX groups in configuration file
- Cleaned up code
- Corrected major security bug
- Corrected path completion, to complete only allowed path simplified the `check_secure` and `check_path` functions
- Added escape code handling (tested with ftp, gdb, vi)
- Added flexible +/- possibilities in configuration file
- Now supports completion after `|`, `;` and `&`
- Command tests are also done after `|`, `;` and `&`
- Doesn't list hidden directories by default
- There are now 4 logging levels (4: logs absolutely everything user types)
- Added `strict` behavior. If set to 1, any unknown command is considered as forbidden, as warning counter is decreased.

### v0.2.6 02/03/2009
- Added `all` to allow all commands to a user
- Added backticks in `lshell.conf`
- Changes made to `setup.py` in version 0.2.5 were undone + added classifiers

### v0.2.5 15/02/2009
- Corrected import readline [bug]
- Added log directory instead of a logfile
- Created log levels (0 to 3)
- `setup.py` is now BSD compatible (using `--install-data` flag)

### v0.2.4 27/01/2009
- NEW: `overssh` in config file. Allows to set commands allowed to execute over ssh (e.g. rsync)
- Fixed timer
- Added python logging method
- Cleaned code
- Cleaner "over ssh commands" support (e.g. scp, sftp, rsync, etc.)

### v0.2.3 03/12/2008
- Corrected completion
- Added `[global]` section in configuration file

### v0.2.2 29/10/2008
- Corrected SCP functionality
- Added SFTP support
- `passwd` is not mandatory in configuration file (deprecated)
- lshell is now added to `/etc/shells` using `add-shell`

### v0.2.1 20/10/2008
- Corrected rpm & deb builds
- Added a manpage

### v0.2 18/10/2008
- Initial debian packaging

### v0.2 17/10/2008
- Added config and log option on command line (`-c|--config` and `-l|--log`)
- Initial source packaging using distutils
- Initial rpm packaging using distutils

### v0.2 07/10/2008
- Added file completion
- Added a history file per user
- Added a logging for warnings and log in/out
- Added prompt update when user changes directory (bash like)
- Corrected the `check_path` function
- Changed user setting from global variable to dict
- Added a default profile used when a parameter is not set for a user

### 06/05/2008
- Added a shell script useful to install and manage lshell users

### 08/04/2008
- Added environment path (`env_path`) update support
- Added home path (`home_path`) variable

### 29/03/2008
- Corrected class declaration bug and configuration file location
- Updated the README file with another usage of lshell

### 05/02/2008
- Added a path variable to restrict the user's geographic actions
- MAJOR: added SCP support (also configurable through the config file)

### 31/01/2008
- MAJOR: Added the `help` method
- Did some code cleanup

### 28/01/2008
- Initial release of lshell
