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
from lshell import audit
from lshell import expansion_inspector

EXTENSION_RESTRICTION_EXEMPT_COMMANDS = {"cd", "clear", "fg", "bg", "ls"}
MAX_WILDCARD_MATCHES = 4096
MAX_BRACE_EXPANSIONS = 256
MAX_EXPANSION_RECURSION = expansion_inspector.MAX_EXPANSION_RECURSION

# Backward-compatible exports used by tests and internal callers.
_ShellExpansion = expansion_inspector._ShellExpansion
_scan_shell_expansions = expansion_inspector._scan_shell_expansions
inspect_shell_expansions = expansion_inspector.inspect_shell_expansions

_EXTGLOB_OPENERS = ("@(", "!(", "+(", "*(", "?(")
_AWK_COMMANDS = {"awk", "gawk", "mawk", "nawk"}
_SED_COMMANDS = {"sed", "gsed"}

# Commands whose positional operands commonly refer to filesystem entries.
# We use this to protect bareword symlink targets without treating generic
# literals (for example `echo hello`) as path operands.
_BAREWORD_FILESYSTEM_COMMANDS = {
    *_AWK_COMMANDS,
    "cat",
    "chgrp",
    "chmod",
    "chown",
    "cmp",
    "comm",
    "cp",
    "diff",
    "du",
    "file",
    "grep",
    "egrep",
    "fgrep",
    "rgrep",
    "head",
    "install",
    "less",
    "ln",
    "ls",
    "mkdir",
    "more",
    "mv",
    "nl",
    "patch",
    "readlink",
    "realpath",
    "rm",
    "rmdir",
    *_SED_COMMANDS,
    "sort",
    "stat",
    "tac",
    "tail",
    "tee",
    "touch",
    "wc",
}


def _is_assignment_word(word):
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*=.*$", word))


def _quoted_literals_without_assignment(line):
    """Extract quoted literals, excluding immediate assignment values (X="...")."""
    literals = []
    index = 0
    length = len(line)

    while index < length:
        quote = line[index]
        if quote not in {"'", '"'}:
            index += 1
            continue

        previous = line[index - 1] if index > 0 else ""
        index += 1
        chunk = []
        escaped = False

        while index < length:
            char = line[index]
            if quote == '"' and escaped:
                chunk.append(char)
                escaped = False
                index += 1
                continue
            if quote == '"' and char == "\\":
                escaped = True
                index += 1
                continue
            if char == quote:
                break
            chunk.append(char)
            index += 1

        if index < length and line[index] == quote:
            chunk_text = "".join(chunk)
            if previous != "=":
                literals.append(chunk_text)
            if quote == "'":
                literals.extend(_quoted_literals_without_assignment(chunk_text))
        index += 1

    return literals


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
    audit.set_decision_reason(
        conf, f"forbidden {messagetype}: {str(command).strip()}"
    )

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
    audit.set_decision_reason(conf, f"unknown syntax: {command}")
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


def _safe_realpath(path):
    """Resolve canonical path and ignore malformed/unresolvable inputs."""
    try:
        return os.path.realpath(path)
    except (OSError, TypeError, ValueError):
        return None


def _safe_expand_path(path):
    """Expand user/env path fragments and reject malformed values."""
    try:
        expanded = os.path.expanduser(path)
        return os.path.expandvars(expanded)
    except (TypeError, ValueError):
        return None


def _safe_lexists(path):
    """Return os.path.lexists(path) while rejecting malformed inputs."""
    try:
        return os.path.lexists(path)
    except (OSError, TypeError, ValueError):
        return False


def _contains_unescaped_extglob(pattern):
    """Return True when extglob operators are present in an unescaped form."""
    escaped = False
    for index, char in enumerate(pattern[:-1]):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if pattern[index : index + 2] in _EXTGLOB_OPENERS:
            return True
    return False


def _find_matching_brace(text, start):
    """Return index of matching '}' for text[start] == '{', else None."""
    escaped = False
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return index
            if depth < 0:
                return None
    return None


def _split_brace_options(body):
    """Split one brace body ('a,b,{c,d}') into top-level options."""
    options = []
    current = []
    escaped = False
    depth = 0

    for char in body:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            current.append(char)
            escaped = True
            continue
        if char == "{":
            current.append(char)
            depth += 1
            continue
        if char == "}":
            if depth == 0:
                return None
            current.append(char)
            depth -= 1
            continue
        if char == "," and depth == 0:
            options.append("".join(current))
            current = []
            continue
        current.append(char)

    if escaped or depth != 0:
        return None

    options.append("".join(current))
    if len(options) <= 1:
        return []
    return options


def _find_expandable_brace_group(pattern):
    """Return first expandable brace group as (start, end, options, malformed)."""
    escaped = False
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == "\\":
            escaped = True
            index += 1
            continue
        if char != "{":
            index += 1
            continue

        end = _find_matching_brace(pattern, index)
        if end is None:
            return None, None, None, True

        options = _split_brace_options(pattern[index + 1 : end])
        if options is None:
            return None, None, None, True
        if options:
            return index, end, options, False

        index = end + 1

    return None, None, None, False


def _expand_brace_patterns(pattern, limit=MAX_BRACE_EXPANSIONS):
    """Perform shell-style brace expansion for one pattern, with fan-out limits."""
    expanded = []
    malformed = False

    def _walk(current):
        nonlocal malformed
        if malformed:
            return
        if len(expanded) >= limit:
            malformed = True
            return

        start, end, options, group_malformed = _find_expandable_brace_group(current)
        if group_malformed:
            malformed = True
            return

        if start is None:
            expanded.append(current)
            return

        prefix = current[:start]
        suffix = current[end + 1 :]
        for option in options:
            _walk(prefix + option + suffix)
            if malformed:
                return

    _walk(pattern)
    if malformed:
        return None
    return expanded


def expand_shell_wildcards(item):
    """Expand shell wildcards and return all candidate filesystem paths."""

    # Expand shell variables like $HOME first.
    expanded_item = _safe_expand_path(item)
    if expanded_item is None:
        return []

    expanded_patterns = _expand_brace_patterns(expanded_item)
    if expanded_patterns is None:
        return []

    # Expand wildcard patterns against the filesystem and validate all matches.
    # Fail closed if expansion fans out too much to avoid memory abuse.
    try:
        expanded_items = []
        seen_candidates = set()
        for pattern in expanded_patterns:
            if _contains_unescaped_extglob(pattern):
                return []

            matched = False
            for match in glob.iglob(pattern, recursive=True):
                matched = True
                resolved = _safe_realpath(match)
                if resolved and resolved not in seen_candidates:
                    seen_candidates.add(resolved)
                    expanded_items.append(resolved)
                if len(expanded_items) > MAX_WILDCARD_MATCHES:
                    return []

            if not matched:
                resolved = _safe_realpath(pattern)
                if resolved and resolved not in seen_candidates:
                    seen_candidates.add(resolved)
                    expanded_items.append(resolved)
                if len(expanded_items) > MAX_WILDCARD_MATCHES:
                    return []
    except (OSError, RuntimeError, ValueError, re.error):
        return []

    return expanded_items


def _split_path_acl_entries(path_acl):
    """Convert legacy path ACL string format to canonical path entries."""
    if not path_acl:
        return []

    entries = []
    for token in str(path_acl).split("|"):
        candidate = token.strip()
        if not candidate:
            continue
        resolved = _safe_realpath(candidate)
        if resolved:
            entries.append(resolved)
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


def _looks_like_numeric_literal(token):
    """Return True for plain numeric arguments such as `10` or `-1`."""
    return bool(re.fullmatch(r"[-+]?\d+(?:\.\d+)?", token))


def _references_existing_path(token):
    """Return True when token resolves to an existing filesystem entry."""
    expanded = _safe_expand_path(token)
    if expanded is None:
        return False
    if not os.path.isabs(expanded):
        expanded = os.path.join(os.getcwd(), expanded)
    return _safe_lexists(expanded)


def _command_name(command):
    """Return a basename-style command identifier for operand heuristics."""
    if not command:
        return ""
    return os.path.basename(command)


def _should_check_bareword_path_operand(command, token):
    """Return True when a bareword operand should be treated as a path."""
    if not token or token == "-" or token.startswith("-"):
        return False
    if _looks_like_numeric_literal(token):
        return False
    if _command_name(command) not in _BAREWORD_FILESYSTEM_COMMANDS:
        return False
    return _references_existing_path(token)


def _grep_implicit_pattern_index(args):
    """Return the grep implicit PATTERN arg index, or None when explicit patterns are used."""
    has_explicit_pattern = False
    index = 0

    while index < len(args):
        token = args[index]

        if token == "--":
            if not has_explicit_pattern and index + 1 < len(args):
                return index + 1
            return None

        if token in {"-e", "--regexp", "-f", "--file"}:
            has_explicit_pattern = True
            index += 2
            continue

        if token.startswith("--regexp=") or token.startswith("--file="):
            has_explicit_pattern = True
            index += 1
            continue

        # Handle compact short forms like -ePATTERN / -fFILE.
        if len(token) > 2 and token.startswith("-") and token[1] in {"e", "f"}:
            has_explicit_pattern = True
            index += 1
            continue

        if token.startswith("-") and token != "-":
            index += 1
            continue

        if not has_explicit_pattern:
            return index
        return None

    return None


def _awk_non_path_indices(args):
    """Return awk argument indices that are program/options, not file operands."""
    skip_indices = set()
    has_program = False
    index = 0

    while index < len(args):
        token = args[index]

        if token == "--":
            if not has_program and index + 1 < len(args):
                skip_indices.add(index + 1)
                has_program = True
                index += 2
                continue
            index += 1
            continue

        if token in {"-v", "-F"}:
            if index + 1 < len(args):
                skip_indices.add(index + 1)
            index += 2
            continue

        if token == "-f":
            # The following argument is an awk program file and must be checked.
            has_program = True
            index += 2
            continue

        if token.startswith(("-v", "-F", "-f", "--")) and token != "-":
            if token.startswith("-f"):
                has_program = True
            index += 1
            continue

        if token.startswith("-") and token != "-":
            index += 1
            continue

        if not has_program:
            skip_indices.add(index)
            has_program = True

        index += 1

    return skip_indices


def _awk_path_like_non_path_indices(args):
    """Return awk argument indices that should not be path-checked even if path-like."""
    skip_indices = set()
    index = 0

    while index < len(args):
        token = args[index]

        if token == "--":
            index += 1
            continue

        if token in {"-v", "-F"}:
            if index + 1 < len(args):
                skip_indices.add(index + 1)
            index += 2
            continue

        if token in {"-f"}:
            index += 2
            continue

        if token.startswith(("-v", "-F", "--")) and token != "-":
            index += 1
            continue

        if token.startswith("-") and token != "-":
            index += 1
            continue

        index += 1

    return skip_indices


def _sed_non_path_indices(args):
    """Return sed argument indices that are scripts/options, not file operands."""
    skip_indices = set()
    has_script = False
    index = 0

    while index < len(args):
        token = args[index]

        if token == "--":
            if not has_script and index + 1 < len(args):
                skip_indices.add(index + 1)
                has_script = True
                index += 2
                continue
            index += 1
            continue

        if token in {"-e", "--expression"}:
            if index + 1 < len(args):
                skip_indices.add(index + 1)
            has_script = True
            index += 2
            continue

        if token in {"-f", "--file"}:
            # The following argument is a sed script file and must be checked.
            has_script = True
            index += 2
            continue

        if token.startswith(("-e", "--expression=")) and token != "-":
            has_script = True
            index += 1
            continue

        if token.startswith(("-f", "--file=")) and token != "-":
            has_script = True
            index += 1
            continue

        if token.startswith("-") and token != "-":
            index += 1
            continue

        if not has_script:
            skip_indices.add(index)
            has_script = True

        index += 1

    return skip_indices


def _non_path_operand_indices(command, args):
    """Return argument indices that are not bareword filesystem operands."""
    command_name = _command_name(command)
    if command_name in {"grep", "egrep", "fgrep", "rgrep"}:
        implicit_pattern_index = _grep_implicit_pattern_index(args)
        return {implicit_pattern_index} if implicit_pattern_index is not None else set()
    if command_name in _AWK_COMMANDS:
        return _awk_non_path_indices(args)
    if command_name in _SED_COMMANDS:
        return _sed_non_path_indices(args)
    return set()


def _path_like_non_path_operand_indices(command, args):
    """Return argument indices that should not be path-checked even if path-like."""
    command_name = _command_name(command)
    if command_name in {"grep", "egrep", "fgrep", "rgrep"}:
        implicit_pattern_index = _grep_implicit_pattern_index(args)
        return {implicit_pattern_index} if implicit_pattern_index is not None else set()
    if command_name in _AWK_COMMANDS:
        return _awk_path_like_non_path_indices(args)
    if command_name in _SED_COMMANDS:
        return _sed_non_path_indices(args)
    return set()


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
            bareword_skip_indices = _non_path_operand_indices(command, args)
            path_like_skip_indices = _path_like_non_path_operand_indices(command, args)

            path_tokens.extend(
                token
                for idx, token in enumerate(args)
                if (
                    (
                        idx not in path_like_skip_indices
                        and _looks_like_path_token(token)
                    )
                    or (
                        idx not in bareword_skip_indices
                        and _should_check_bareword_path_operand(command, token)
                    )
                )
            )
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
        if not candidates:
            if not completion:
                ret, conf = warn_count("path", item, conf, strict=strict, ssh=ssh)
            return 1, conf

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


def check_secure(line, conf, strict=None, ssh=None, _depth=0):
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

    if _depth > MAX_EXPANSION_RECURSION:
        return warn_unknown_syntax(oline, conf, strict=strict, ssh=ssh)

    for item in _quoted_literals_without_assignment(line):
        if os.path.exists(item):
            ret_check_path, conf = check_path(item, conf, strict=strict, ssh=ssh)
            returncode += ret_check_path

    # parse command line for control characters, and warn user
    if re.findall(r"[\x01-\x1F\x7F]", oline):
        ret, conf = warn_count("control char", oline, conf, strict=strict, ssh=ssh)
        return ret, conf

    ret_forbidden, conf = check_forbidden_chars(line, conf, strict=strict, ssh=ssh)
    if ret_forbidden:
        return ret_forbidden, conf

    expansion_inspection = inspect_shell_expansions(line)
    if expansion_inspection.malformed:
        return warn_unknown_syntax(oline, conf, strict=strict, ssh=ssh)

    for variable in expansion_inspection.parameter_path_probes:
        ret_check_path, conf = check_path(variable, conf, strict=strict, ssh=ssh)
        returncode += ret_check_path

    for expansion in expansion_inspection.executable_expansions:
        inner = expansion.body.strip()
        if not inner:
            continue
        if expansion.kind in {"command_substitution", "process_substitution"}:
            ret_check_path, conf = check_path(inner, conf, strict=strict, ssh=ssh)
            returncode += ret_check_path

        ret_check_secure, conf = check_secure(
            inner,
            conf,
            strict=strict,
            ssh=ssh,
            _depth=_depth + 1,
        )
        returncode += ret_check_secure

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
            expanded_value = _safe_expand_path(value)
            resolved_value = (
                _safe_realpath(expanded_value) if expanded_value is not None else None
            )
            is_existing_dir = bool(resolved_value and os.path.isdir(resolved_value))
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
