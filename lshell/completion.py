"""Completion functions for lshell"""

import os
import re
from lshell import sec


def completedefault(*ignored):
    """Method called to complete an input line when no command-specific
    complete_*() method is available.

    By default, it returns an empty list.

    """
    return []


def completenames(conf, text, line, *ignored):
    """This method is meant to override the original completenames method
    to overload it's output with the command available in the 'allowed'
    variable. This is useful when typing 'tab-tab' in the command prompt
    """
    commands = conf["allowed"]
    if line.startswith("./"):
        return [cmd[2:] for cmd in commands if cmd.startswith(f"./{text}")]
    else:
        return [cmd for cmd in commands if cmd.startswith(text)]


def completesudo(conf, text, line, begidx, endidx):
    """complete sudo command"""
    return [a for a in conf["sudo_commands"] if a.startswith(text)]


def completechdir(conf, text, line, begidx, endidx):
    """complete directories"""
    dirs_to_return = []
    tocomplete = line.split(" ")[1]
    # replace "~" with home path
    tocomplete = re.sub("^~", conf["home_path"], tocomplete)

    # Detect relative vs absolute paths
    if not tocomplete.startswith("/"):
        # Resolve relative paths based on current working directory
        base_path = os.getcwd()
        tocomplete = os.path.normpath(os.path.join(base_path, tocomplete))
    try:
        directory = os.path.realpath(tocomplete)
    except OSError:
        directory = os.getcwd()

    # if directory doesn't exist, take the parent directory
    if not os.path.isdir(directory):
        directory = directory.rsplit("/", 1)[0]
        if directory == "":
            directory = "/"

    directory = os.path.normpath(directory)

    # check path security
    ret_check_path, conf = sec.check_path(directory, conf, completion=1)

    # if path is secure, list subdirectories and files
    if ret_check_path == 0:
        for instance in os.listdir(directory):
            if os.path.isdir(os.path.join(directory, instance)):
                if instance.startswith(text):
                    dirs_to_return.append(f"{instance}/")

    # if path is not secure, add completion based on allowed path
    else:
        allowed_paths = conf["path"][0].split("|")
        for instance in allowed_paths:
            # Check if the directory matches or is a parent of the allowed path
            if instance.startswith(directory) and instance.startswith(tocomplete):
                # Extract the next unmatched segment of the allowed path
                remaining_path = instance[len(directory) :].lstrip("/")
                if "/" in remaining_path:
                    next_segment = remaining_path.split("/", 1)[0] + "/"
                else:
                    next_segment = remaining_path + "/"

                # Add unique suggestions
                if next_segment and next_segment not in dirs_to_return:
                    dirs_to_return.append(next_segment)

    return dirs_to_return


def completelistdir(conf, text, line, begidx, endidx):
    """complete with files and directories"""
    toreturn = []
    tocomplete = line.split()[-1]
    # replace "~" with home path
    tocomplete = re.sub("^~", conf["home_path"], tocomplete)
    try:
        directory = os.path.realpath(tocomplete)
    except OSError:
        directory = os.getcwd()

    if not os.path.isdir(directory):
        directory = directory.rsplit("/", 1)[0]
        if directory == "":
            directory = "/"
        if not os.path.isdir(directory):
            directory = os.getcwd()

    ret_check_path, conf = sec.check_path(directory, conf, completion=1)
    if ret_check_path == 0:
        for instance in os.listdir(directory):
            if os.path.isdir(os.path.join(directory, instance)):
                instance = instance + "/"
            else:
                instance = instance + " "
            if instance.startswith("."):
                if text.startswith("."):
                    toreturn.append(instance)
                else:
                    pass
            else:
                toreturn.append(instance)
        return [a for a in toreturn if a.startswith(text)]
    else:
        return None
