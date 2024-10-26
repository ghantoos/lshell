""" This module is used to check the security of the commands entered by the
user. It checks if the command is allowed, if the path is allowed, if the
command contains forbidden characters, etc.
"""

import sys
import re
import os
import subprocess

# import lshell specifics
from lshell import utils


def warn_count(messagetype, command, conf, strict=None, ssh=None):
    """Update the warning_counter, log and display a warning to the user"""

    log = conf["logpath"]
    if not ssh:
        if strict:
            conf["warning_counter"] -= 1
            if conf["warning_counter"] < 0:
                log.critical(f'*** forbidden {messagetype} -> "{command}"')
                log.critical("*** Kicked out")
                sys.exit(1)
            else:
                log.critical(f'*** forbidden {messagetype} -> "{command}"')
                sys.stderr.write(
                    f"*** You have {conf['warning_counter']} warning(s) left,"
                    " before getting kicked out.\n"
                )
                log.error(f"*** User warned, counter: {conf['warning_counter']}")
                sys.stderr.write("This incident has been reported.\n")
        else:
            if not conf["quiet"]:
                log.critical(f"*** forbidden {messagetype}: {command}")

    # if you are here, means that you did something wrong. Return 1.
    return 1, conf


def check_path(line, conf, completion=None, ssh=None, strict=None):
    """Check if a path is entered in the line. If so, it checks if user
    are allowed to see this path. If user is not allowed, it calls
    warn_count. In case of completion, it only returns 0 or 1.
    """
    allowed_path_re = str(conf["path"][0])
    denied_path_re = str(conf["path"][1][:-1])

    # split line depending on the operators
    sep = re.compile(r"\ |;|\||&")
    line = line.strip()
    line = sep.split(line)

    for item in line:
        # remove potential quotes or back-ticks
        item = re.sub(r'^["\'`]|["\'`]$', "", item)

        # remove potential $(), ${}, ``
        item = re.sub(r"^\$[\(\{]|[\)\}]$", "", item)

        # if item has been converted to something other than a string
        # or an int, reconvert it to a string
        if type(item) not in ["str", "int"]:
            item = str(item)
        # replace "~" with home path
        item = os.path.expanduser(item)

        # expand shell wildcards using "echo"
        # i know, this a bit nasty...
        if re.findall(r"\$|\*|\?", item):
            # remove quotes if available
            item = re.sub("\"|'", "", item)

            p = subprocess.Popen(
                f"`which echo` {item}",
                shell=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            cout = p.stdout

            try:
                item = cout.readlines()[0].decode("utf8").split(" ")[0]
                item = item.strip()
                item = os.path.expandvars(item)
            except IndexError:
                conf["logpath"].critical("*** Internal error: command not " "executed")
                return 1, conf

        tomatch = os.path.realpath(item)
        if os.path.isdir(tomatch) and tomatch[-1] != "/":
            tomatch += "/"
        match_allowed = re.findall(allowed_path_re, tomatch)
        if denied_path_re:
            match_denied = re.findall(denied_path_re, tomatch)
        else:
            match_denied = None

        # if path not allowed
        # case path executed: warn, and return 1
        # case completion: return 1
        if not match_allowed or match_denied:
            if not completion:
                ret, conf = warn_count("path", tomatch, conf, strict=strict, ssh=ssh)
            return 1, conf

    if not completion:
        if not re.findall(allowed_path_re, os.getcwd() + "/"):
            ret, conf = warn_count("path", tomatch, conf, strict=strict, ssh=ssh)
            os.chdir(conf["home_path"])
            conf["promptprint"] = utils.updateprompt(os.getcwd(), conf)
            return 1, conf
    return 0, conf


def check_secure(line, conf, strict=None, ssh=None):
    """This method is used to check the content on the typed command.
    Its purpose is to forbid the user to user to override the lshell
    command restrictions.
    The forbidden characters are placed in the 'forbidden' variable.
    Feel free to update the list. Emptying it would be quite useless..: )

    A warning counter has been added, to kick out of lshell a user if he
    is warned more than X time (X being the 'warning_counter' variable).
    """

    # store original string
    oline = line

    # strip all spaces/tabs
    line = line.strip()

    # init return code
    returncode = 0

    # This logic is kept crudely simple on purpose.
    # At most we might match the same stanza twice
    # (for e.g. "'a'", 'a') but the converse would
    # require detecting single quotation stanzas
    # nested within double quotes and vice versa
    relist = re.findall(r"[^=]\"(.+)\"", line)
    relist2 = re.findall(r"[^=]\'(.+)\'", line)
    relist = relist + relist2
    for item in relist:
        if os.path.exists(item):
            ret_check_path, conf = check_path(item, conf, strict=strict)
            returncode += ret_check_path

    # parse command line for control characters, and warn user
    if re.findall(r"[\x01-\x1F\x7F]", oline):
        ret, conf = warn_count("control char", oline, conf, strict=strict, ssh=ssh)
        return ret, conf

    for item in conf["forbidden"]:
        # allow '&&' and '||' even if singles are forbidden
        if item in ["&", "|"]:
            if re.findall(rf"[^\{item}]\{item}[^\{item}]", line):
                ret, conf = warn_count("syntax", oline, conf, strict=strict, ssh=ssh)
                return ret, conf
        else:
            if item in line:
                ret, conf = warn_count("syntax", oline, conf, strict=strict, ssh=ssh)
                return ret, conf

    # check if the line contains $(foo) executions, and check them
    executions = re.findall(r"\$\([^)]+[)]", line)
    for item in executions:
        # recurse on check_path
        ret_check_path, conf = check_path(item[2:-1].strip(), conf, strict=strict)
        returncode += ret_check_path

        # recurse on check_secure
        ret_check_secure, conf = check_secure(item[2:-1].strip(), conf, strict=strict)
        returncode += ret_check_secure

    # check for executions using back quotes '`'
    executions = re.findall(r"\`[^`]+[`]", line)
    for item in executions:
        ret_check_secure, conf = check_secure(item[1:-1].strip(), conf, strict=strict)
        returncode += ret_check_secure

    # check if the line contains ${foo=bar}, and check them
    curly = re.findall(r"\$\{[^}]+[}]", line)
    for item in curly:
        # split to get variable only, and remove last character "}"
        if re.findall(r"=|\+|\?|\-", item):
            variable = re.split(r"=|\+|\?|\-", item, 1)
        else:
            variable = item
        ret_check_path, conf = check_path(variable[1][:-1], conf, strict=strict)
        returncode += ret_check_path

    # if unknown commands where found, return 1 and don't execute the line
    if returncode > 0:
        return 1, conf
    # in case the $(foo) or `foo` command passed the above tests
    elif line.startswith("$(") or line.startswith("`"):
        return 0, conf

    # in case ';', '|' or '&' are not forbidden, check if in line
    lines = []

    # corrected by Alojzij Blatnik #48
    # test first character
    if line[0] in ["&", "|", ";"]:
        start = 1
    else:
        start = 0

    # split remaining command line
    for i in range(1, len(line)):
        # in case \& or \| or \; don't split it
        if line[i] in ["&", "|", ";"] and line[i - 1] != "\\":
            # if there is more && or || skip it
            if start != i:
                lines.append(line[start:i])
            start = i + 1

    # append remaining command line
    if start != len(line):
        # fmt: off
        lines.append(line[start:len(line)])
        # fmt: on

    for separate_line in lines:
        # remove trailing parenthesis
        separate_line = re.sub(r"\)$", "", separate_line)
        separate_line = " ".join(separate_line.split())
        splitcmd = separate_line.strip().split(" ")

        # Extract the command and its arguments
        command = splitcmd[0]
        command_args_list = splitcmd[1:]
        command_args_string = " ".join(command_args_list)
        full_command = f"{command} {command_args_string}".strip()

        # in case of a sudo command, check in sudo_commands list if allowed
        if command == "sudo" and command_args_list:
            # allow the -u (user) flag
            if command_args_list[0] == "-u" and command_args_list:
                sudocmd = command_args_list[2]
            else:
                sudocmd = command_args_list[0]
            if sudocmd not in conf["sudo_commands"] and command_args_list:
                ret, conf = warn_count(
                    "sudo command", oline, conf, strict=strict, ssh=ssh
                )
                return ret, conf

        # if over SSH, replaced allowed list with the one of overssh
        if ssh:
            conf["allowed"] = conf["overssh"]

        # # for all other commands check in allowed list
        # if command not in conf["allowed"] and command:
        #     ret, conf = warn_count("command", command, conf, strict=strict, ssh=ssh)
        #     return ret, conf

        # Check if the full command (with arguments) or just the command is allowed
        if (
            full_command not in conf["allowed"]
            and command not in conf["allowed"]
            and command
        ):
            ret, conf = warn_count("command", command, conf, strict=strict, ssh=ssh)
            return ret, conf

    return 0, conf
