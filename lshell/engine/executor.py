"""Runtime execution path for v2 parse/authorize pipeline."""

import os
import re
import sys
from typing import NamedTuple

from lshell import audit
from lshell import builtincmd
from lshell import containment
from lshell import messages
from lshell import sec
from lshell import utils
from lshell import variables
from lshell.engine import authorizer
from lshell.engine import normalizer
from lshell.engine import parser as engine_parser
from lshell.engine import reasons


class EngineDecisions(NamedTuple):
    """Input for execute(decisions, runtime)."""

    ast: object
    policy: dict


class ExecutionResult(NamedTuple):
    """Execution result produced by the v2 executor."""

    retcode: int
    audit_reason: str


def build_decisions(command_line, policy):
    """parse(line) -> normalize(AST) decisions bundle."""
    parsed = engine_parser.parse(command_line)
    canonical = normalizer.normalize(parsed)
    return EngineDecisions(ast=canonical, policy=policy)


def _unknown_syntax_retcode(shell_context, command):
    ret, shell_context.conf = sec.warn_unknown_syntax(
        command,
        shell_context.conf,
        strict=shell_context.conf["strict"],
    )
    audit.log_command_event(
        shell_context.conf,
        command,
        allowed=False,
        reason=audit.pop_decision_reason(
            shell_context.conf,
            reasons.to_audit_reason(reasons.make_reason(reasons.UNKNOWN_SYNTAX, command=command)),
        ),
        level="warning",
    )
    if ret == 1 and shell_context.conf["strict"]:
        return 126
    return 1


def _deny_with_reason(shell_context, command_line, decision):
    reason = decision.reason
    payload = reasons.warning_payload(reason)

    if payload and payload.get("kind") == "unknown_syntax":
        return _unknown_syntax_retcode(shell_context, payload.get("command", command_line))

    if payload and payload.get("kind") == "warn_count":
        _ret, shell_context.conf = sec.warn_count(
            payload.get("messagetype", "command"),
            payload.get("command", command_line),
            shell_context.conf,
            strict=shell_context.conf["strict"],
        )
        audit.log_command_event(
            shell_context.conf,
            command_line,
            allowed=False,
            reason=audit.pop_decision_reason(
                shell_context.conf,
                reasons.to_audit_reason(reason),
            ),
        )
        return 126

    if reason.code == reasons.FORBIDDEN_ENV_ASSIGNMENT:
        variable = reason.details.get("variable", "")
        audit.set_decision_reason(
            shell_context.conf,
            reasons.to_audit_reason(reason),
        )
        audit.log_command_event(
            shell_context.conf,
            command_line,
            allowed=False,
            reason=audit.pop_decision_reason(
                shell_context.conf,
                reasons.to_audit_reason(reason),
            ),
        )
        shell_context.log.critical(f"lshell: forbidden environment variable: {variable}")
        sys.stderr.write(f"lshell: forbidden environment variable: {variable}\n")
        return 126

    if reason.code == reasons.FORBIDDEN_TRUSTED_PROTOCOL:
        audit.log_command_event(
            shell_context.conf,
            command_line,
            allowed=False,
            reason=reasons.to_audit_reason(reason),
        )
        shell_context.log.critical(
            f'lshell: forbidden trusted SSH protocol command: "{command_line}"'
        )
        sys.stderr.write("lshell: forbidden trusted SSH protocol command\n")
        return 126

    audit.log_command_event(
        shell_context.conf,
        command_line,
        allowed=False,
        reason=reasons.to_audit_reason(reason),
    )
    return 126


def _trusted_protocol_precheck(sequence, shell_context):
    operators = {"&&", "||", "|", ";", "&"}
    trusted = set(variables.TRUSTED_SFTP_PROTOCOL_BINARIES)

    for item in sequence:
        if item in operators:
            continue

        executable, _argument, _split, assignments = utils._parse_command(item)
        if executable is None:
            return authorizer.AuthorizationDecision(
                False,
                reasons.make_reason(reasons.UNKNOWN_SYNTAX, command=item, line=item),
                None,
            )
        if assignments:
            return authorizer.AuthorizationDecision(
                False,
                reasons.make_reason(
                    reasons.FORBIDDEN_TRUSTED_PROTOCOL,
                    command=item,
                    detail="env assignment",
                ),
                None,
            )
        if executable not in trusted:
            return authorizer.AuthorizationDecision(
                False,
                reasons.make_reason(
                    reasons.FORBIDDEN_TRUSTED_PROTOCOL,
                    command=executable,
                ),
                None,
            )

    return None


def execute(decisions, runtime):
    """execute(decisions, runtime) -> retcode + audit."""
    shell_context = runtime["shell_context"]
    trusted_protocol = bool(runtime.get("trusted_protocol"))
    command_line = decisions.ast.line

    if decisions.ast.parse_error:
        retcode = _unknown_syntax_retcode(shell_context, command_line)
        return ExecutionResult(retcode=retcode, audit_reason="unknown syntax")

    forbidden_check_line = utils.expand_vars_quoted(
        command_line,
        support_advanced_braced=False,
    )
    ret_forbidden_chars, shell_context.conf = sec.check_forbidden_chars(
        forbidden_check_line,
        shell_context.conf,
        strict=shell_context.conf["strict"],
    )
    if ret_forbidden_chars == 1:
        audit.log_command_event(
            shell_context.conf,
            command_line,
            allowed=False,
            reason=audit.pop_decision_reason(
                shell_context.conf, "forbidden character in command"
            ),
        )
        retcode = 126
        return ExecutionResult(
            retcode=retcode,
            audit_reason="forbidden character in command",
        )

    command_sequence = list(decisions.ast.sequence)
    retcode = 0

    if trusted_protocol:
        trusted_check = _trusted_protocol_precheck(command_sequence, shell_context)
        if trusted_check is not None:
            retcode = _deny_with_reason(shell_context, command_line, trusted_check)
            return ExecutionResult(
                retcode=retcode,
                audit_reason=reasons.to_audit_reason(trusted_check.reason),
            )

    i = 0
    while i < len(command_sequence):
        current_item = command_sequence[i]

        if current_item in ["&&", "||", "|", "&", ";"]:
            i += 1
            continue

        prev_operator = command_sequence[i - 1] if i > 0 else None

        if prev_operator == "&&" and retcode != 0:
            j = i
            while (
                j + 2 < len(command_sequence)
                and command_sequence[j + 1] == "|"
                and command_sequence[j + 2] not in ["&&", "||", "|", "&", ";"]
            ):
                j += 2
            i = j + (
                2
                if j + 1 < len(command_sequence) and command_sequence[j + 1] == "&"
                else 1
            )
            continue
        if prev_operator == "||" and retcode == 0:
            j = i
            while (
                j + 2 < len(command_sequence)
                and command_sequence[j + 1] == "|"
                and command_sequence[j + 2] not in ["&&", "||", "|", "&", ";"]
            ):
                j += 2
            i = j + (
                2
                if j + 1 < len(command_sequence) and command_sequence[j + 1] == "&"
                else 1
            )
            continue

        pipeline_parts = [current_item]
        j = i
        while (
            j + 2 < len(command_sequence)
            and command_sequence[j + 1] == "|"
            and command_sequence[j + 2] not in ["&&", "||", "|", "&", ";"]
        ):
            pipeline_parts.append(command_sequence[j + 2])
            j += 2

        pipeline_parts = [utils.replace_exit_code(part, retcode) for part in pipeline_parts]
        pipeline_parts = [
            utils.expand_vars_quoted(part, support_advanced_braced=False)
            for part in pipeline_parts
        ]
        full_command = " | ".join(pipeline_parts)
        background = bool(j + 1 < len(command_sequence) and command_sequence[j + 1] == "&")

        if background:
            limits = containment.get_runtime_limits(shell_context.conf)
            if limits.max_background_jobs > 0:
                active_jobs = len(builtincmd.jobs())
                if active_jobs >= limits.max_background_jobs:
                    reason = containment.reason_with_details(
                        "runtime_limit.max_background_jobs_exceeded",
                        active=active_jobs,
                        limit=limits.max_background_jobs,
                    )
                    shell_context.log.critical(
                        "lshell: runtime containment denied background command: "
                        f"active_jobs={active_jobs}, limit={limits.max_background_jobs}, "
                        f'command="{full_command}"'
                    )
                    sys.stderr.write(
                        "lshell: background job denied: "
                        f"max_background_jobs={limits.max_background_jobs} reached\n"
                    )
                    audit.log_command_event(
                        shell_context.conf,
                        full_command,
                        allowed=False,
                        reason=reason,
                    )
                    return ExecutionResult(retcode=126, audit_reason=reason)

        parsed_parts = [utils._parse_command(part) for part in pipeline_parts]
        if any(part[0] is None for part in parsed_parts):
            retcode = _unknown_syntax_retcode(shell_context, full_command)
            return ExecutionResult(retcode=retcode, audit_reason="unknown syntax")

        for _executable_name, _argument, _split, assignments in parsed_parts:
            for var_name, _var_value in assignments:
                if var_name in variables.FORBIDDEN_ENVIRON:
                    deny_decision = authorizer.AuthorizationDecision(
                        False,
                        reasons.make_reason(
                            reasons.FORBIDDEN_ENV_ASSIGNMENT,
                            variable=var_name,
                            line=full_command,
                        ),
                        None,
                    )
                    retcode = _deny_with_reason(shell_context, full_command, deny_decision)
                    return ExecutionResult(
                        retcode=retcode,
                        audit_reason=reasons.to_audit_reason(deny_decision.reason),
                    )

        executable, argument, _, assignments = parsed_parts[0]
        if not executable and assignments:
            for var_name, var_value in assignments:
                os.environ[var_name] = var_value
            audit.log_command_event(
                shell_context.conf,
                full_command,
                allowed=True,
                reason="assignment-only command accepted",
            )
            retcode = 0
            i = j + (2 if background else 1)
            continue

        if not trusted_protocol:
            decision = authorizer.authorize_line(
                full_command,
                shell_context.conf,
                mode="runtime",
                check_current_dir=True,
            )
            if not decision.allowed:
                retcode = _deny_with_reason(shell_context, full_command, decision)
                if (
                    decision.reason.code == reasons.FORBIDDEN_PATH
                    and shell_context.conf.get("winscp")
                    and re.search("WinSCP: this is end-of-file", command_line)
                ):
                    utils.exec_cmd(f'echo "WinSCP: this is end-of-file: {retcode}"')
                return ExecutionResult(
                    retcode=retcode,
                    audit_reason=reasons.to_audit_reason(decision.reason),
                )

        if len(pipeline_parts) == 1 and executable in builtincmd.builtins_list and not background:
            audit.log_command_event(
                shell_context.conf,
                full_command,
                allowed=True,
                reason="allowed builtin command",
            )
            retcode, shell_context.conf = utils.handle_builtin_command(
                full_command,
                executable,
                argument,
                shell_context,
            )
        elif trusted_protocol or all(
            executable_name
            and utils._is_allowed_command(executable_name, part, shell_context.conf)
            for (executable_name, _, _, _), part in zip(parsed_parts, pipeline_parts)
        ):
            if not trusted_protocol:
                missing_executable = next(
                    (
                        executable_name
                        for executable_name, _, _, _ in parsed_parts
                        if executable_name
                        and executable_name not in builtincmd.builtins_list
                        and not utils._command_exists(executable_name)
                    ),
                    None,
                )
                if missing_executable:
                    command_not_found_message = messages.get_message(
                        shell_context.conf,
                        "command_not_found",
                        command=missing_executable,
                    )
                    audit.log_command_event(
                        shell_context.conf,
                        full_command,
                        allowed=False,
                        reason=f"command not found: {missing_executable}",
                    )
                    shell_context.log.critical(command_not_found_message)
                    return ExecutionResult(retcode=127, audit_reason="command not found")

            extra_env = None
            allowed_shell_escape = set(shell_context.conf.get("allowed_shell_escape", []))
            uses_shell_escape = any(
                executable_name in allowed_shell_escape
                for (executable_name, _, _, _) in parsed_parts
                if executable_name
            )
            if "path_noexec" in shell_context.conf and not uses_shell_escape:
                extra_env = {"LD_PRELOAD": shell_context.conf["path_noexec"]}

            audit.log_command_event(
                shell_context.conf,
                full_command,
                allowed=True,
                reason="allowed by command and path policy",
            )
            retcode = utils.exec_cmd(
                full_command,
                background=background,
                extra_env=extra_env,
                conf=shell_context.conf,
                log=shell_context.log,
            )
        else:
            retcode = _unknown_syntax_retcode(shell_context, full_command)
            return ExecutionResult(retcode=retcode, audit_reason="unknown syntax")

        i = j + (2 if background else 1)

    return ExecutionResult(retcode=retcode, audit_reason="command execution complete")


def execute_for_shell(command_line, shell_context, trusted_protocol=False):
    """Convenience runtime entrypoint for utils.cmd_parse_execute v2 path."""
    decisions = build_decisions(command_line, shell_context.conf)
    result = execute(
        decisions,
        {
            "shell_context": shell_context,
            "trusted_protocol": trusted_protocol,
        },
    )
    return result.retcode


__all__ = ["EngineDecisions", "ExecutionResult", "build_decisions", "execute", "execute_for_shell"]
