![PyPI - Version](https://img.shields.io/pypi/v/limited-shell?link=https%3A%2F%2Fpypi.org%2Fproject%2Flimited-shell%2F)
![PyPI - Downloads](https://img.shields.io/pypi/dm/limited-shell)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/ghantoos/lshell/pytest.yml?branch=master&label=pytest&link=https%3A%2F%2Fgithub.com%2Fghantoos%2Flshell%2Factions%2Fworkflows%2Fpytest.yml)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/ghantoos/lshell/pylint.yml?branch=master&label=pylint&link=https%3A%2F%2Fgithub.com%2Fghantoos%2Flshell%2Factions%2Fworkflows%2Fpylint.yml)

# lshell

`lshell` is a Python-based restricted shell that limits users to a defined set of commands, enforces path and SSH transfer controls (`scp`, `sftp`, `rsync`, ...), logs user activity, supports session/time restrictions, and more.

PyPI project page: https://pypi.org/project/limited-shell/

## Installation

Install from PyPI:

```bash
pip install limited-shell
```

Build/install from source:

```bash
python3 -m pip install build --user
python3 -m build
pip install . --break-system-packages
```

Uninstall:

```bash
pip uninstall limited-shell
```

## Quick start

Run `lshell` with an explicit config:

```bash
lshell --config /path/to/lshell.conf
```

Default config location:

- Linux: `/etc/lshell.conf`
- *BSD: `/usr/{pkg,local}/etc/lshell.conf`

Set `lshell` as login shell:

```bash
chsh -s /usr/bin/lshell user_name
```

## Policy diagnostics

Explain the effective policy and decision for a command:

```bash
lshell policy-show \
  --config /path/to/lshell.conf \
  --user deploy \
  --group ops \
  --group release \
  --command "sudo systemctl restart nginx"
```

Inside an interactive session:

- `policy-show [<command...>]`
- `policy-path` (`lpath` alias)
- `policy-sudo` (`lsudo` alias)

Hide these built-ins if needed:

```ini
policy_commands : 0
```

## Configuration

Primary template: [`etc/lshell.conf`](etc/lshell.conf)

Key settings to review:

- `allowed` / `forbidden`
- `path`
- `sudo_commands`
- `overssh`, `scp`, `sftp`, `scp_upload`, `scp_download`
- `allowed_shell_escape`
- `allowed_file_extensions`
- `messages`
- `warning_counter`, `strict`
- `umask`

CLI overrides are supported, for example:

```bash
lshell --config /path/to/lshell.conf --log /var/log/lshell --umask 0077
```

### Best practices

- Prefer an explicit `allowed` allow-list instead of `'all'`.
- Keep `allowed_shell_escape` short and audit every entry. Never add tools that execute arbitrary commands (for example `find`, `vim`, `xargs`).
- Use `allowed_file_extensions` when users are expected to work with a known set of file types.
- Keep `warning_counter` enabled (avoid `-1` unless you intentionally want warning-only behavior).
- Use `policy-show` during reviews to validate effective policy before assigning it to users.

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

For full option details, use:

- `man lshell`
- `man ./man/lshell.1`

## Testing

Run test services directly:

```bash
docker compose up ubuntu_tests debian_tests fedora_tests
```

Run full validation:

```bash
just test-all
```

Run only SSH end-to-end checks:

```bash
just test-ssh-e2e
```

### Justfile usage

List commands:

```bash
just --list
```

Run distro-specific tests:

```bash
just test-debian
just test-ubuntu
just test-fedora
```

Run sample configs interactively:

```bash
just sample-list
just sample-ubuntu 01_baseline_allowlist.conf
```

## Contributing

Open an issue or pull request: https://github.com/ghantoos/lshell/issues
