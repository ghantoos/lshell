""" This module contains the built-in commands of lshell """

import glob
import sys
import os
import shlex
import readline
import signal

# import lshell specifics
from lshell import variables
from lshell import utils
from lshell import sec as sec_policy


# Store background jobs
BACKGROUND_JOBS = []

POLICY_COMMANDS = [
    "policy-show",
    "policy-path",
    "policy-sudo",
    "lpath",
    "lsudo",
]

builtins_list = [
    "cd",
    "ls",
    "clear",
    "exit",
    "export",
    "history",
    "policy-show",
    "policy-path",
    "policy-sudo",
    "lpath",
    "lsudo",
    "help",
    "fg",
    "bg",
    "jobs",
    "source",
]


def _cancel_job_timeout(job):
    """Cancel a watchdog timer attached to a background job, if any."""
    timer = getattr(job, "lshell_timeout_timer", None)
    if timer is not None:
        timer.cancel()


def cmd_lpath(conf):
    """Show path policy in a concise, readable format."""
    current_dir = os.path.realpath(os.getcwd())
    path_acl = conf.get("path", ["", ""])
    allow = path_acl[0] if len(path_acl) > 0 else ""
    deny = path_acl[1] if len(path_acl) > 1 else ""
    allowed_roots = sec_policy._split_path_acl_entries(allow)
    denied_roots = sec_policy._split_path_acl_entries(deny)
    current_allowed = sec_policy._is_path_allowed(
        current_dir, allowed_roots, denied_roots
    )
    current_status = "allowed" if current_allowed else "denied"

    sys.stdout.write("Path Policy\n")
    sys.stdout.write("-----------\n")
    sys.stdout.write(f"Current directory      : {current_dir} ({current_status})\n")
    sys.stdout.write("\nAllowed paths\n")
    sys.stdout.write("-------------\n")
    lpath_allowed = sorted(path for path in conf["path"][0].split("|") if path)
    if lpath_allowed:
        for path in lpath_allowed:
            sys.stdout.write(f"{path}\n")
    else:
        sys.stdout.write("none\n")

    lpath_denied = sorted(path for path in conf["path"][1].split("|") if path)
    if lpath_denied:
        sys.stdout.write("\nDenied paths\n")
        sys.stdout.write("------------\n")
        for path in lpath_denied:
            sys.stdout.write(f"{path}\n")
    return 0


def cmd_lsudo(conf):
    """Show sudo policy in a concise, readable format."""
    sudo_commands = sorted(conf.get("sudo_commands", []))
    enabled = bool(sudo_commands)

    sys.stdout.write("Sudo Policy\n")
    sys.stdout.write("-----------\n")
    sys.stdout.write(f"Sudo access            : {'enabled' if enabled else 'disabled'}\n")
    if enabled:
        sys.stdout.write(f"Allowed via sudo       : {', '.join(sudo_commands)}\n")
        return 0

    sys.stdout.write("Allowed via sudo       : none\n")
    return 1


def cmd_history(conf, log):
    """print the commands history"""
    try:
        try:
            readline.write_history_file(conf["history_file"])
        except IOError:
            log.error(f"WARN: couldn't write history to file {conf['history_file']}\n")
            return 1
        with open(conf["history_file"], "r", encoding="utf-8") as history_file:
            i = 1
            for item in history_file.readlines():
                sys.stdout.write(f"{i}:  {item}")
                i += 1
    except (
        OSError,
        IOError,
        FileNotFoundError,
    ) as exception:  # Catch specific exceptions
        log.critical(f"** Unable to read the history file: {exception}")
        return 1
    return 0


def cmd_export(args):
    """export environment variables"""
    try:
        tokens = shlex.split(args, posix=True)
    except ValueError:
        return 0, None

    if len(tokens) >= 2 and "=" in tokens[1]:
        var, value = tokens[1].split("=", 1)
        # disallow dangerous variable
        if var in variables.FORBIDDEN_ENVIRON:
            return 1, var
        os.environ.update({var: value})
    return 0, None


def cmd_source(envfile):
    """Source a file in the current shell context"""
    envfile = envfile.strip().strip("'").strip('"')
    envfile = os.path.expanduser(os.path.expandvars(envfile))
    try:
        with open(envfile, encoding="utf-8") as env_vars:
            for env_var in env_vars.readlines():
                line = env_var.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    cmd_export(line)
    except (OSError, IOError):
        sys.stderr.write(f"lshell: unable to read environment file: {envfile}\n")
        return 1
    return 0


def cmd_cd(directory, conf):
    """implementation of the "cd" command"""
    # expand user's ~
    directory = os.path.expanduser(directory)

    # remove quotes if present
    directory = directory.strip("'").strip('"')

    if len(directory) >= 1:
        # add wildcard completion support to cd
        if directory.find("*"):
            # get all files and directories matching wildcard
            wildall = glob.glob(directory)
            wilddir = []
            # filter to only directories
            for item in wildall:
                if os.path.isdir(item):
                    wilddir.append(item)
            # sort results
            wilddir.sort()
            # if any results are returned, pick first one
            if len(wilddir) >= 1:
                directory = wilddir[0]
        # go previous directory
        if directory == "-":
            directory = conf["oldpwd"]

        # store current directory in oldpwd variable
        conf["oldpwd"] = os.getcwd()

        # change directory
        try:
            os.chdir(os.path.realpath(directory))
            conf["promptprint"] = utils.updateprompt(os.getcwd(), conf)
        except OSError as excp:
            sys.stdout.write(f"lshell: {directory}: {excp.strerror}\n")
            return excp.errno, conf
    else:
        os.chdir(conf["home_path"])
        conf["promptprint"] = utils.updateprompt(os.getcwd(), conf)

    return 0, conf


def check_background_jobs():
    """Check the status of background jobs and print a completion message if done."""
    active_jobs = []
    for idx, job in enumerate(BACKGROUND_JOBS, start=1):
        if job.poll() is None:
            active_jobs.append(job)
            continue

        _cancel_job_timeout(job)
        if getattr(job, "lshell_timeout_triggered", False):
            print(f"[{idx}]+  Timed Out               {_job_command(job)}")
            continue

        status = "Done" if job.returncode == 0 else "Failed"
        args = _job_command(job)
        # only print if the job has not been interrupted by the user
        if job.returncode != -2:
            print(f"[{idx}]+  {status}                    {args}")

    BACKGROUND_JOBS[:] = active_jobs


def get_job_status(job):
    """Return the status of a background job."""
    if getattr(job, "lshell_timeout_triggered", False):
        return "Timed Out"
    if job.poll() is None:
        status = "Stopped"
    elif job.poll() == 0:
        status = "Completed"  # Process completed successfully
    else:
        status = "Killed"  # Process was killed or terminated with a non-zero code
    return status


def _job_command(job):
    """Return the original command line for a tracked job."""
    return getattr(job, "lshell_cmd", " ".join(job.args))


def jobs():
    """Return a list of background jobs."""
    joblist = []
    active_jobs = []
    for job in BACKGROUND_JOBS:
        if job.poll() is not None:
            _cancel_job_timeout(job)
            continue

        active_jobs.append(job)
        idx = len(active_jobs)
        status = get_job_status(job)
        cmd = _job_command(job)
        joblist.append([idx, status, cmd])

    BACKGROUND_JOBS[:] = active_jobs
    return joblist


def cmd_jobs():
    """List all backgrounded jobs."""
    joblist = jobs()
    job_count = len(joblist)

    try:
        for i, job in enumerate(joblist, start=1):
            idx, status, cmd = job
            # Add '+' symbol for the most recent job
            job_symbol = "+"
            if job_count > 1:
                if i == job_count - 1:
                    # Add '-' for the second-to-last job
                    job_symbol = "-"
                elif i < job_count:
                    # No symbol for other jobs
                    job_symbol = " "
            print(f"[{idx}]{job_symbol}  {status}        {cmd}")
    except IndexError:
        return 1
    return 0


def cmd_bg_fg(job_type, job_id):
    """Resume a backgrounded job."""
    if job_type == "bg":
        print("lshell: bg not supported")
        return 1

    if job_id:
        # Check if job ID is valid
        try:
            job_id = int(job_id)
        except ValueError:
            print("lshell: invalid job ID")
            return 1
    else:
        # Use the last job if no specific job_id is provided
        if BACKGROUND_JOBS:
            job_id = len(BACKGROUND_JOBS)
        else:
            print(f"lshell: {job_type}: current: no such job")
            return 1

    if 0 < job_id <= len(BACKGROUND_JOBS):
        job = BACKGROUND_JOBS[job_id - 1]
        if job.poll() is None:
            if job_type == "fg":
                class CtrlZForeground(Exception):
                    """Raised when the foreground job is suspended with Ctrl+Z."""

                    pass

                def handle_sigtstp(signum, frame):
                    """Suspend the foreground job and keep/update its jobs list entry."""
                    if job.poll() is None:
                        os.killpg(os.getpgid(job.pid), signal.SIGSTOP)
                        if job in BACKGROUND_JOBS:
                            current_job_id = BACKGROUND_JOBS.index(job) + 1
                        else:
                            BACKGROUND_JOBS.append(job)
                            current_job_id = len(BACKGROUND_JOBS)
                        sys.stdout.write(
                            f"\n[{current_job_id}]+  Stopped        {_job_command(job)}\n"
                        )
                        sys.stdout.flush()
                    raise CtrlZForeground()

                previous_sigtstp_handler = signal.getsignal(signal.SIGTSTP)
                try:
                    signal.signal(signal.SIGTSTP, handle_sigtstp)
                    print(_job_command(job))
                    # Bring it to the foreground and wait
                    os.killpg(os.getpgid(job.pid), signal.SIGCONT)
                    job.wait()
                    # Remove the job from the list if it has completed
                    if job.poll() is not None:
                        BACKGROUND_JOBS.pop(job_id - 1)
                    return 0
                except CtrlZForeground:
                    return 0
                except KeyboardInterrupt:
                    os.killpg(os.getpgid(job.pid), signal.SIGINT)
                    BACKGROUND_JOBS.pop(job_id - 1)
                    return 130
                finally:
                    signal.signal(signal.SIGTSTP, previous_sigtstp_handler)
            # bg not supported at the moment
            # elif job_type == "bg":
            #     print(f"lshell: bg not supported")
            #     return 1
        else:
            print(f"lshell: {job_type}: {job_id}: no such job")
            return 1
    else:
        print(f"lshell: {job_type}: {job_id}: no such job")
        return 1
