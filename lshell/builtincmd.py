""" This module contains the built-in commands of lshell """

import glob
import sys
import os
import readline
import signal

# import lshell specifics
from lshell import variables
from lshell import utils


# Store background jobs
background_jobs = []


def lpath(conf):
    """lists allowed and forbidden path"""
    if conf["path"][0]:
        sys.stdout.write("Allowed:\n")
        lpath_allowed = conf["path"][0].split("|")
        lpath_allowed.sort()
        for path in lpath_allowed:
            if path:
                sys.stdout.write(f" {path[:-2]}\n")
    if conf["path"][1]:
        sys.stdout.write("Denied:\n")
        lpath_denied = conf["path"][1].split("|")
        lpath_denied.sort()
        for path in lpath_denied:
            if path:
                sys.stdout.write(f" {path[:-2]}\n")
    return 0


def lsudo(conf):
    """lists allowed sudo commands"""
    if "sudo_commands" in conf and len(conf["sudo_commands"]) > 0:
        sys.stdout.write("Allowed sudo commands:\n")
        for command in conf["sudo_commands"]:
            sys.stdout.write(f" - {command}\n")
        return 0

    sys.stdout.write("No sudo commands allowed\n")
    return 1


def history(conf, log):
    """print the commands history"""
    try:
        try:
            readline.write_history_file(conf["history_file"])
        except IOError:
            log.error(f"WARN: couldn't write history to file {conf['history_file']}\n")
            return 1
        with open(conf["history_file"], "r", encoding="utf-8") as f:
            i = 1
            for item in f.readlines():
                sys.stdout.write(f"{i}:  {item}")
                i += 1
    except (OSError, IOError, FileNotFoundError) as e:  # Catch specific exceptions
        log.critical(f"** Unable to read the history file: {e}")
        return 1
    return 0


def export(args):
    """export environment variables"""
    # if command contains at least 1 space
    if args.count(" "):
        env = args.split(" ", 1)[1]
        # if it contains the equal sign, consider only the first one
        if env.count("="):
            var, value = env.split(" ")[0].split("=")[0:2]
            # disallow dangerous variable
            if var in variables.FORBIDDEN_ENVIRON:
                return 1, var
            # Strip the quotes from the value if it begins and ends with quotes (single or double)
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            os.environ.update({var: value})
    return 0, None


def source(envfile):
    """Source a file in the current shell context"""
    envfile = os.path.expandvars(envfile)
    try:
        with open(envfile, encoding="utf-8") as env_vars:
            for env_var in env_vars.readlines():
                if env_var.split(" ", 1)[0] == "export":
                    export(env_var.strip())
    except (OSError, IOError):
        sys.stderr.write(f"ERROR: Unable to read environment file: {envfile}\n")
        return 1
    return 0


def cd(directory, conf):
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
    global background_jobs
    updated_jobs = []
    for idx, job in enumerate(background_jobs, start=1):
        if job.poll() is None:
            # Process is still running
            updated_jobs.append((idx, job.args, job.pid))
        else:
            # Process has finished
            status = "Done" if job.returncode == 0 else "Failed"
            args = " ".join(job.args)
            # only print if the job has not been interrupted by the user
            if job.returncode != -2:
                print(f"[{idx}]+  {status}                    {args}")

            # Remove the job from the list of background jobs
            background_jobs.pop(idx - 1)


def get_job_status(job):
    """Return the status of a background job."""
    if job.poll() is None:
        status = "Stopped"
    elif job.poll() == 0:
        status = "Completed"  # Process completed successfully
    else:
        status = "Killed"  # Process was killed or terminated with a non-zero code
    return status


def jobs():
    """Return a list of background jobs."""
    global background_jobs
    joblist = []
    for idx, job in enumerate(background_jobs, start=1):
        status = get_job_status(job)
        if status in ["Stopped", "Killed"]:
            if job.poll() is not None:
                background_jobs.pop(idx - 1)
                continue
        cmd = " ".join(job.args)
        joblist.append([idx, status, cmd])
    return joblist


def print_jobs():
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


def bg_fg(job_type, job_id):
    """Resume a backgrounded job."""

    global background_jobs
    if job_type == "bg":
        print(f"lshell: bg not supported")
        return 1

    if job_id:
        # Check if job ID is valid
        try:
            job_id = int(job_id)
        except ValueError:
            print("Invalid job ID.")
            return 1
    else:
        # Use the last job if no specific job_id is provided
        if background_jobs:
            job_id = len(background_jobs)
        else:
            print(f"lshell: {job_type}: current: no such job")
            return 1

    if 0 < job_id <= len(background_jobs):
        job = background_jobs[job_id - 1]
        if job.poll() is None:
            if job_type == "fg":
                try:
                    print(" ".join(job.args))
                    # Bring it to the foreground and wait
                    os.killpg(os.getpgid(job.pid), signal.SIGCONT)
                    job.wait()
                    # Remove the job from the list if it has completed
                    if job.poll() is not None:
                        background_jobs.pop(job_id - 1)
                    return 0
                except KeyboardInterrupt:
                    os.killpg(os.getpgid(job.pid), signal.SIGINT)
                    background_jobs.pop(job_id - 1)
                    return 130
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
