![PyPI - Version](https://img.shields.io/pypi/v/limited-shell?link=https%3A%2F%2Fpypi.org%2Fproject%2Flimited-shell%2F)
![PyPI - Downloads](https://img.shields.io/pypi/dm/limited-shell)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/ghantoos/lshell/pytest.yml?branch=master&label=pytest&link=https%3A%2F%2Fgithub.com%2Fghantoos%2Flshell%2Factions%2Fworkflows%2Fpytest.yml)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/ghantoos/lshell/pylint.yml?branch=master&label=pylint&link=https%3A%2F%2Fgithub.com%2Fghantoos%2Flshell%2Factions%2Fworkflows%2Fpylint.yml)

# lshell

`lshell` is a Python-based limited shell. It is designed to restrict a user to a defined command set, enforce path and character restrictions, control SSH command behavior (`scp`, `sftp`, `rsync`, ...), and log activity.

## Installation

### Install from PyPI

```bash
pip install limited-shell
```

### Build and install from source

```bash
python3 -m pip install build --user
python3 -m build
pip install . --break-system-packages
```

### Uninstall

```bash
pip uninstall limited-shell
```

## Usage

### Run lshell

```bash
lshell --config /path/to/lshell.conf
```

Default config location:

- Linux: `/etc/lshell.conf`
- *BSD: `/usr/{pkg,local}/etc/lshell.conf`

You can also override configuration values from CLI:

```bash
lshell --config /path/to/lshell.conf --log /var/log/lshell --umask 0077
```

### Use lshell in scripts

Use the lshell shebang and keep the `.lsh` extension:

```bash
#!/usr/bin/lshell
echo "test"
```

## System setup

### Add user to `lshell` group (for log access)

```bash
usermod -aG lshell username
```

### Set lshell as login shell

Linux:

```bash
chsh -s /usr/bin/lshell user_name
```

*BSD:

```bash
chsh -s /usr/{pkg,local}/bin/lshell user_name
```

Make sure lshell is present in `/etc/shells`.

## Configuration

The main template is [`etc/lshell.conf`](etc/lshell.conf). Full reference is available in the man page.

### Section model and precedence

Supported section types:

- `[global]` for global lshell settings
- `[default]` for all users
- `[username]` for a specific user
- `[grp:groupname]` for a UNIX group

Precedence order:

1. User section
2. Group section
3. Default section

### `allowed`: exact vs generic commands

`allowed` accepts command names and exact command lines.

```ini
allowed: ['ls', 'echo asd', 'telnet localhost']
```

- `ls` allows `ls` with any arguments.
- `echo asd` allows only that exact command line.
- `telnet localhost` allows only `localhost` as host.

For local executables, add explicit relative paths (for example `./deploy.sh`).

### `warning_counter` and `strict`

`warning_counter` is decremented on forbidden command/path/character attempts.
When `strict = 1`, unknown syntax/commands also decrement `warning_counter`.

### Security-related settings

- `path_noexec`: if available, lshell uses `sudo_noexec.so` to reduce command escape vectors.
- `allowed_shell_escape`: explicit list of commands allowed to run child programs. Do not set it to `'all'`.
- `allowed_file_extensions`: optional allow-list for file extensions passed in command lines.

### `umask`

Set a persistent session umask in config:

```ini
umask : 0002
```

- `0002` -> files `664`, directories `775`
- `0022` -> files `644`, directories `755`
- `0077` -> files `600`, directories `700`

`umask` must be octal (`0000` to `0777`).  
If you set umask in `login_script`, it does not persist because `login_script` runs in a child shell.

Quick check inside an lshell session:

```bash
umask
touch test_file
mkdir test_dir
ls -ld test_file test_dir
```

### Example configuration

For users `foo` and `bar` in UNIX group `users`:

```ini
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
env_path        : '/sbin:/usr/foo'
scp             : 1
sftp            : 1
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
```

## Testing with Docker Compose

Run tests on multiple distributions in parallel:

```bash
docker compose up ubuntu_tests debian_tests fedora_tests
```

This runs `pytest`, `pylint`, and `flake8` in the configured test services.

## Documentation

- `man lshell` (installed)
- `man ./man/lshell.1` (from repository)

## Contributing

Open an issue or pull request: https://github.com/ghantoos/lshell/issues
