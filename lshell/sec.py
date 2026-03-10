""" This module is used to check the security of the commands entered by the
user. It checks if the command is allowed, if the path is allowed, if the
command contains forbidden characters, etc.
"""

import sys
import re
import os
import shlex
import glob

# import lshell specifics
from lshell import messages
from lshell import utils

EXTENSION_RESTRICTION_EXEMPT_COMMANDS = {"cd", "clear", "fg", "bg", "ls"}


def _is_assignment_word(word):
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*=.*$", word))


def should_enforce_file_extensions(command):
    """Return True when extension restrictions should apply to this command."""
    return command not in EXTENSION_RESTRICTION_EXEMPT_COMMANDS


def _split_command_for_auth(command_line):
    """Return (command, args, full_command) for auth checks, skipping VAR=VALUE prefixes."""
    try:
        tokens = shlex.split(command_line, posix=True)
    except ValueError:
        return "", [], ""

    index = 0
    while index < len(tokens) and _is_assignment_word(tokens[index]):
        index += 1

    if index >= len(tokens):
        return "", [], ""

    command = tokens[index]
    args = tokens[index + 1 :]
    full_command = " ".join([command] + args).strip()
    return command, args, full_command


def warn_count(messagetype, command, conf, strict=None, ssh=None):
    """Update the warning_counter, log and display a warning to the user"""

    log = conf["logpath"]
    if messagetype == "unknown syntax":
        primary_message = messages.get_message(
            conf, "unknown_syntax", command=command
        )
    else:
        primary_message = messages.get_forbidden_message(conf, messagetype, command)

    if ssh:
        return 1, conf

    conf["warning_counter"] -= 1
    if conf["warning_counter"] < 0:
        log.critical(primary_message)
        log.critical(messages.get_message(conf, "session_terminated"))
        sys.exit(1)

    log.critical(primary_message)
    remaining = conf["warning_counter"]
    violation_label = "violation" if remaining == 1 else "violations"
    sys.stderr.write(
        messages.get_message(
            conf,
            "warning_remaining",
            remaining=remaining,
            violation_label=violation_label,
        )
        + "\n"
    )
    log.error(f"lshell: user warned, counter: {remaining}")

    # Return 1 to indicate a warning was triggered.
    return 1, conf


def warn_unknown_syntax(command, conf, strict=None, ssh=None):
    """Warn on unknown syntax, honoring strict-mode warning counting."""
    if strict:
        return warn_count("unknown syntax", command, conf, strict=strict, ssh=ssh)

    log = conf["logpath"]
    log.warning(f'INFO: unknown syntax -> "{command}"')
    # Keep legacy UX: unknown syntax is always printed to stderr.
    sys.stderr.write(messages.get_message(conf, "unknown_syntax", command=command) + "\n")
    return 1, conf


def tokenize_command(command):
    """Tokenize the command line into separate commands based on the operators"""

    try:
        lexer = shlex.shlex(command, posix=True)
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        # Handle the exception and return an appropriate message or handle as needed
        return []
    return tokens


def expand_shell_wildcards(item):
    """Expand shell wildcards and return all candidate filesystem paths."""

    # Expand shell variables like $HOME first.
    expanded_item = os.path.expanduser(item)
    expanded_item = os.path.expandvars(expanded_item)

    # Expand wildcard patterns against the filesystem and validate all matches.
    expanded_items = glob.glob(expanded_item, recursive=True)
    if expanded_items:
        return [os.path.realpath(match) for match in expanded_items]

    # If no glob match exists, still validate the canonical target path.
    return [os.path.realpath(expanded_item)]


def _split_path_acl_entries(path_acl):
    """Convert legacy path ACL string format to canonical path entries."""
    if not path_acl:
        return []

    entries = []
    for token in str(path_acl).split("|"):
        candidate = token.strip()
        if not candidate:
            continue
        entries.append(os.path.realpath(candidate))
    return entries


def _is_path_within_base(path, base):
    """Return True when path is equal to or nested under base."""
    try:
        return os.path.commonpath([path, base]) == base
    except ValueError:
        # Different mount/drive semantics: treat as not matching.
        return False


def _is_path_allowed(candidate, allowed_roots, denied_roots):
    """Return True when candidate path passes allow/deny ACL precedence.

    Specificity rule:
    - most specific matching prefix wins;
    - ties favor deny.
    This preserves historical expectation that:
      ['/'] - ['/var'] + ['/var/log']
    allows /var/log while still denying /var.
    """

    def _specificity(path):
        normalized = os.path.normpath(path)
        if normalized == os.sep:
            return 0
        return len([segment for segment in normalized.split(os.sep) if segment])

    matching_allows = [root for root in allowed_roots if _is_path_within_base(candidate, root)]
    matching_denies = [root for root in denied_roots if _is_path_within_base(candidate, root)]

    # Legacy behavior: empty allow-list means unrestricted unless denied.
    if not allowed_roots:
        return not bool(matching_denies)

    if not matching_allows:
        return False

    best_allow = max(_specificity(root) for root in matching_allows)
    best_deny = max(_specificity(root) for root in matching_denies) if matching_denies else -1

    return best_allow > best_deny


def _format_path_for_message(path):
    """Format path in user-facing messages with historical trailing-slash behavior."""
    if os.path.isdir(path) and not path.endswith("/"):
        return f"{path}/"
    return path


def _looks_like_path_token(token):
    """Heuristic: return True if a token appears to reference a filesystem path."""
    if not token:
        return False
    if token.startswith(("/", ".", "~")):
        return True
    if "/" in token or "\\" in token:
        return True
    if any(char in token for char in ["*", "?", "[", "]"]):
        return True
    return False


def _path_tokens_from_line(line):
    """Extract path-like tokens from command segments, excluding bare command names."""
    segments = utils.split_commands(line)
    if not segments:
        return []

    path_tokens = []
    for segment in segments:
        try:
            tokens = shlex.split(segment, posix=True)
        except ValueError:
            tokens = tokenize_command(segment)
        if not tokens:
            continue

        index = 0
        while index < len(tokens) and _is_assignment_word(tokens[index]):
            index += 1
        if index >= len(tokens):
            continue

        command = tokens[index]
        args = tokens[index + 1 :]

        if command == "cd" and args:
            # `cd var` style operands are path targets even without slashes.
            path_tokens.append(args[0])
            continue

        if args:
            path_tokens.extend(token for token in args if _looks_like_path_token(token))
            continue

        # Single token mode (used by completion/policy path checks):
        # only treat it as a path when it looks path-like.
        if _looks_like_path_token(command):
            path_tokens.append(command)

    return path_tokens


def check_path(line, conf, completion=None, ssh=None, strict=None):
    """Check if a path is entered in the line. If so, it checks if user
    are allowed to see this path. If user is not allowed, it calls
    warn_count. In case of completion, it only returns 0 or 1.
    """
    allowed_roots = _split_path_acl_entries(conf["path"][0])
    denied_roots = _split_path_acl_entries(conf["path"][1])

    path_tokens = _path_tokens_from_line(line)

    for item in path_tokens:
        candidates = expand_shell_wildcards(item)
        for candidate in candidates:
            if not _is_path_allowed(candidate, allowed_roots, denied_roots):
                if not completion:
                    message_path = _format_path_for_message(candidate)
                    ret, conf = warn_count(
                        "path", message_path, conf, strict=strict, ssh=ssh
                    )
                return 1, conf

    if not completion:
        current_dir = os.path.realpath(os.getcwd())
        if not _is_path_allowed(current_dir, allowed_roots, denied_roots):
            ret, conf = warn_count(
                "path",
                _format_path_for_message(current_dir),
                conf,
                strict=strict,
                ssh=ssh,
            )
            os.chdir(conf["home_path"])
            conf["promptprint"] = utils.updateprompt(os.getcwd(), conf)
            return 1, conf
    return 0, conf


def check_forbidden_chars(line, conf, strict=None, ssh=None):
    """Check if the line contains any forbidden
    characters. If so, it calls warn_count.
    """
    for item in conf["forbidden"]:
        # keep compatibility with historical behavior from check_secure:
        # allow "&&" and "||" even when single "&" or "|" are forbidden.
        if item in ["&", "|"]:
            escaped_item = re.escape(item)
            if re.search(rf"(?<!{escaped_item}){escaped_item}(?!{escaped_item})", line):
                ret, conf = warn_count("character", item, conf, strict=strict, ssh=ssh)
                return ret, conf
        elif item in line:
            ret, conf = warn_count("character", item, conf, strict=strict, ssh=ssh)
            return ret, conf
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
                ret, conf = warn_count("character", item, conf, strict=strict, ssh=ssh)
                return ret, conf
        else:
            if item in line:
                ret, conf = warn_count("character", item, conf, strict=strict, ssh=ssh)
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

    lines = utils.split_commands(line)

    for separate_line in lines:
        # remove trailing parenthesis
        separate_line = re.sub(r"\)$", "", separate_line)
        separate_line = " ".join(separate_line.split())
        command, command_args_list, full_command = _split_command_for_auth(
            separate_line
        )

        # in case of a sudo command, check in sudo_commands list if allowed
        if command == "sudo" and command_args_list:
            # allow the -u (user) flag
            if command_args_list[0] == "-u" and command_args_list:
                if len(command_args_list) < 3:
                    ret, conf = warn_count(
                        "sudo command", oline, conf, strict=strict, ssh=ssh
                    )
                    return ret, conf
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
            if strict:
                ret, conf = warn_count("command", command, conf, strict=strict, ssh=ssh)
            else:
                ret, conf = warn_unknown_syntax(full_command, conf, strict=strict, ssh=ssh)
            return ret, conf

        # Check if the command contains any forbidden extensions
        if conf.get("allowed_file_extensions") and should_enforce_file_extensions(
            command
        ):
            allowed_extensions = conf["allowed_file_extensions"]
            check_extensions, disallowed_extensions = check_allowed_file_extensions(
                full_command, allowed_extensions
            )
            if check_extensions is False:
                ret, conf = warn_count(
                    f"file extension {disallowed_extensions}",
                    full_command,
                    conf,
                    strict=strict,
                    ssh=ssh,
                )
                return ret, conf

    return 0, conf


def check_allowed_file_extensions(command_line, allowed_extensions):
    """Checks if file arguments in the command line use allowed extensions."""
    # Split the command using shlex to handle quotes and escape characters
    try:
        tokens = shlex.split(command_line)
    except ValueError as exception:
        # Log error or provide user feedback on the invalid input
        print(f"lshell: error parsing command line: {exception}")
        return True, []

    if not tokens:
        return True, None

    candidates = []
    for token in tokens[1:]:
        if _is_assignment_word(token):
            continue

        # Parse option values such as `--include=*.log` as potential file globs.
        if token.startswith("-"):
            if "=" not in token:
                continue
            _, value = token.split("=", 1)
            values_to_check = [value] if value else []
        else:
            values_to_check = [token]

        for value in values_to_check:
            candidate = value.rstrip("/")
            basename = os.path.basename(candidate)

            if not basename or basename in [".", ".."]:
                continue

            extension = os.path.splitext(basename)[1]
            # Existing directories are valid SCP/SFTP targets and do not
            # represent file-extension risk on their own.
            is_existing_dir = os.path.isdir(os.path.realpath(os.path.expanduser(value)))
            has_path_markers = any(
                char in value for char in ["/", "\\", "*", "?", "[", "]"]
            ) or value.startswith(("~", "."))
            is_simple_bareword = bool(re.match(r"^[A-Za-z0-9_-]+$", basename))

            candidates.append(
                {
                    "extension": extension if extension else "<none>",
                    "explicit_path_like": bool(extension) or has_path_markers,
                    "simple_bareword": is_simple_bareword and not has_path_markers,
                    "is_existing_dir": is_existing_dir,
                }
            )

    has_explicit_path_like = any(item["explicit_path_like"] for item in candidates)
    disallowed_extensions = []
    for item in candidates:
        # If explicit path-like operands are present, treat lone bare words as
        # likely literals/patterns rather than filenames.
        if has_explicit_path_like and item["simple_bareword"]:
            continue
        if item["is_existing_dir"]:
            continue
        extension = item["extension"]
        if extension not in allowed_extensions and extension not in disallowed_extensions:
            disallowed_extensions.append(extension)

    if disallowed_extensions:
        return False, disallowed_extensions
    return True, None
