"""System bootstrap helpers for pip-based lshell installs."""

import argparse
import grp
import os
import pwd
import shutil
import subprocess
import sys


def _ensure_root():
    if os.name != "posix":
        raise RuntimeError("lshell setup-system is supported on POSIX systems only.")
    if os.geteuid() != 0:
        raise RuntimeError("lshell setup-system must be run as root.")


def _create_group(group_name):
    """Best-effort system group creation across common Linux/BSD tools."""
    candidates = [
        ["groupadd", "-r", group_name],
        ["groupadd", group_name],
        ["addgroup", "--system", group_name],
        ["addgroup", group_name],
        ["pw", "groupadd", group_name],
    ]
    for cmd in candidates:
        if shutil.which(cmd[0]) is None:
            continue
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except subprocess.CalledProcessError:
            continue
    raise RuntimeError(
        f"Unable to create group '{group_name}'. Create it manually and retry."
    )


def _ensure_group(group_name):
    try:
        return grp.getgrnam(group_name).gr_gid
    except KeyError:
        _create_group(group_name)
        return grp.getgrnam(group_name).gr_gid


def _resolve_uid(user_name):
    try:
        return pwd.getpwnam(user_name).pw_uid
    except KeyError as exception:
        raise RuntimeError(f"Owner user '{user_name}' does not exist.") from exception


def _resolve_lshell_path(requested):
    if requested and requested != "auto":
        return os.path.realpath(requested)

    discovered = shutil.which("lshell")
    if not discovered:
        raise RuntimeError("lshell binary not found in PATH.")
    return os.path.realpath(discovered)


def _ensure_shell_entry(shell_path):
    shells_file = "/etc/shells"
    if os.path.exists(shells_file):
        with open(shells_file, "r", encoding="utf-8") as stream:
            entries = [line.strip() for line in stream if line.strip()]
        if shell_path not in entries:
            with open(shells_file, "a", encoding="utf-8") as stream:
                stream.write(f"{shell_path}\n")
    else:
        with open(shells_file, "w", encoding="utf-8") as stream:
            stream.write(f"{shell_path}\n")


def _set_user_shell(user_name, shell_path):
    if shutil.which("usermod"):
        subprocess.run(["usermod", "-s", shell_path, user_name], check=True)
        return
    if shutil.which("chsh"):
        subprocess.run(["chsh", "-s", shell_path, user_name], check=True)
        return
    raise RuntimeError("Neither 'usermod' nor 'chsh' is available to set user shells.")


def _add_user_to_group(user_name, group_name):
    if shutil.which("usermod"):
        subprocess.run(["usermod", "-aG", group_name, user_name], check=True)
        return
    if shutil.which("gpasswd"):
        subprocess.run(["gpasswd", "-a", user_name, group_name], check=True)
        return
    raise RuntimeError("Neither 'usermod' nor 'gpasswd' is available to manage group membership.")


def _ensure_log_directory(path, owner_uid, group_gid, mode):
    os.makedirs(path, exist_ok=True)
    os.chown(path, owner_uid, group_gid)
    os.chmod(path, mode)


def main(argv=None):
    """Prepare system-level resources needed by lshell."""
    parser = argparse.ArgumentParser(
        prog="lshell setup-system",
        description="Create/validate group, log directory, and login-shell registration.",
    )
    parser.add_argument("--group", default="lshell", help="System group for lshell logs.")
    parser.add_argument(
        "--log-dir", default="/var/log/lshell", help="Directory used for lshell log files."
    )
    parser.add_argument(
        "--owner", default="root", help="Owner user for the log directory (default: root)."
    )
    parser.add_argument(
        "--mode",
        default="2770",
        help="Octal mode for log directory. Default 2770 keeps group-write + setgid.",
    )
    parser.add_argument(
        "--shell-path",
        default="auto",
        help="Path to lshell binary to register in /etc/shells (default: auto).",
    )
    parser.add_argument(
        "--skip-shell-registration",
        action="store_true",
        help="Do not modify /etc/shells.",
    )
    parser.add_argument(
        "--set-shell-user",
        action="append",
        default=[],
        help="Set the login shell of this user to lshell (repeatable).",
    )
    parser.add_argument(
        "--add-group-user",
        action="append",
        default=[],
        help="Add user to the lshell group so group-write log access works (repeatable).",
    )
    args = parser.parse_args(argv)

    try:
        _ensure_root()
        mode_value = int(args.mode, 8)
        if mode_value < 0 or mode_value > 0o7777:
            raise ValueError
    except ValueError:
        print(
            f"lshell setup-system: Invalid mode value '{args.mode}'. "
            "Use octal digits, e.g. 2770.",
            file=sys.stderr,
        )
        return 1
    except RuntimeError as exception:
        print(f"lshell setup-system: {exception}", file=sys.stderr)
        return 1

    try:
        gid = _ensure_group(args.group)
        uid = _resolve_uid(args.owner)
        _ensure_log_directory(args.log_dir, uid, gid, mode_value)

        shell_path = _resolve_lshell_path(args.shell_path)
        if not args.skip_shell_registration:
            _ensure_shell_entry(shell_path)
        for user_name in args.set_shell_user:
            _set_user_shell(user_name, shell_path)
        for user_name in args.add_group_user:
            _add_user_to_group(user_name, args.group)
    except RuntimeError as exception:
        print(f"lshell setup-system: {exception}", file=sys.stderr)
        return 1
    except (OSError, subprocess.CalledProcessError) as exception:
        print(f"lshell setup-system: {exception}", file=sys.stderr)
        return 1

    print(
        f"lshell setup complete: group={args.group} log_dir={args.log_dir} "
        f"mode={oct(mode_value)} shell={shell_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
