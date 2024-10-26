![PyPI - Version](https://img.shields.io/pypi/v/limited-shell?link=https%3A%2F%2Fpypi.org%2Fproject%2Flimited-shell%2F)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/ghantoos/lshell/pytest.yml?branch=master&label=pytest&link=https%3A%2F%2Fgithub.com%2Fghantoos%2Flshell%2Factions%2Fworkflows%2Fpytest.yml)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/ghantoos/lshell/pylint.yml?branch=master&label=pylint&link=https%3A%2F%2Fgithub.com%2Fghantoos%2Flshell%2Factions%2Fworkflows%2Fpylint.yml)

# lshell

lshell is a limited shell coded in Python, that lets you restrict a user's environment to limited sets of commands, choose to enable/disable any command over SSH (e.g. SCP, SFTP, rsync, etc.), log user's commands, implement timing restriction, and more.


## Installation

### Install via pip

To install `limited-shell` directly via `pip`, use the following command:

```bash
pip install limited-shell
```

This will install limited-shell from PyPI along with all its dependencies.

To uninstall, you can run:

```bash
pip uninstall limited-shell
```

### Build from source and install locally

If you'd like to build and install limited-shell from the source code (useful if you're making modifications or testing new features), you can follow these steps:

```
python3 -m pip install build --user
python3 -m build
pip install . --break-system-packages
```

### Uninstall lshell

To uninstall, you can run:

```bash
pip uninstall limited-shell
```

## Usage
### Via binary
To launch lshell, just execute lshell specifying the location of your configuration file:

```bash
lshell --config /path/to/configuration/file
```

### Using `lshell` in Scripts

You can use `lshell` directly within a script by specifying the lshell path in the shebang. Ensure your script has a `.lsh` extension to indicate it is for lshell, and make sure to include the shebang `#!/usr/bin/lshell` at the top of your script.

For example:

```bash
#!/usr/bin/lshell
echo "test"
```


## Configuration
### User shell configuration
In order to log a user, you will have to add them to the lshell group:

```bash
usermod -aG lshell username
```

In order to configure a user account to use lshell by default, you must: 

```bash
chsh -s /usr/bin/lshell user_name
```

You might need to ensure that lshell is listed in /etc/shells.

### lshell.conf

#### Allowed list
lshell.conf presents a template configuration file. See `etc/lshell.conf` or the man file for more information.

You can allow commands specifying commands with exact arguments in the `allowed` list. This means you can define specific commands along with their arguments that are permitted. Commands without arguments can also be specified, allowing any arguments to be passed.

For example:
```
allowed: ['ls', 'echo asd', 'telnet localhost']
```

This will:
- Allow the `ls` command with any arguments.
- Allow `echo asd` but will reject `echo` with any other arguments (e.g., `echo qwe` will be rejected).
- Allow `telnet localhost`, but not `telnet` with other hosts (e.g., `telnet 192.168.0.1` will be rejected).

Commands that do not include arguments (e.g., `ls`) can be used with any arguments, while commands specified with arguments (e.g., `echo asd`) must be used exactly as specified.

#### User profiles

A [default] profile is available for all users using lshell. Nevertheless,  you can create a [username] section or a [grp:groupname] section to customize users' preferences.

Order of priority when loading preferences is the following:

1. User configuration
2. Group configuration
3. Default configuration

The primary goal of lshell, is to be able to create shell accounts with ssh access and restrict their environment to a couple a needed commands and path.

#### Example

For example User 'foo' and user 'bar' both belong to the 'users' UNIX group:

- User 'foo': 
       - must be able to access /usr and /var but not /usr/local
       - use all commands in their PATH except 'su'
       - has a warning counter set to 5
       - has their home path set to '/home/users'

- User 'bar':
       - must be able to access /etc and /usr but not /usr/local
       - is allowed default commands plus 'ping' minus 'ls'
       - strictness is set to 1 (meaning he is not allowed to type an unknown command)

In this case, my configuration file will look something like this:

    # CONFIGURATION START
    [global]
    logpath         : /var/log/lshell/
    loglevel        : 2

    [default]
    allowed         : ['ls','pwd']
    forbidden       : [';', '&', '|'] 
    warning_counter : 2
    timer           : 0
    path            : ['/etc', '/usr']
    env_path        : ':/sbin:/usr/foo'
    scp             : 1 # or 0
    sftp            : 1 # or 0
    overssh         : ['rsync','ls']
    aliases         : {'ls':'ls --color=auto','ll':'ls -l'}

    [grp:users]
    warning_counter : 5
    overssh         : - ['ls']

    [foo]
    allowed         : 'all' - ['su']
    path            : ['/var', '/usr'] - ['/usr/local']
    home_path       : '/home/users'

    [bar]
    allowed         : + ['ping'] - ['ls'] 
    path            : - ['/usr/local']
    strict          : 1
    scpforce        : '/home/bar/uploads/'
    # CONFIGURATION END

## More information

More information can be found in the manpage: `man -l man/lshell.1` or `man lshell`.


## Contributions

To contribute, open an issue or send a pull request.

Please use github for all requests: https://github.com/ghantoos/lshell/issues
