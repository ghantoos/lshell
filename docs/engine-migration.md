# Canonical Engine Architecture

## Overview

Lshell now uses a single canonical command engine for both runtime execution
and policy diagnostics. There is no legacy engine toggle or fallback path.

## Pipeline

The shared flow is:

1. `parse(line)` -> `lshell.engine.ast.ParsedAST`
2. `normalize(parsed_ast)` -> `lshell.engine.ast.CanonicalAST`
3. `authorize(canonical_ast, policy)` -> structured allow/deny decision
4. `execute(decisions, runtime)` -> retcode + audit outcome

Runtime entrypoint:

- `lshell.utils.cmd_parse_execute` -> `lshell.engine.executor.execute_for_shell`

Policy diagnostics entrypoint:

- `lshell.config.diagnostics.policy_command_decision` -> canonical authorizer path

## Engine Modules

- `lshell/engine/ast.py`: canonical AST structures.
- `lshell/engine/parser.py`: top-level command/operator sequence parser.
- `lshell/engine/normalizer.py`: canonical command normalization and assignment splitting.
- `lshell/engine/authorizer.py`: centralized command/path/security authorization.
- `lshell/engine/reasons.py`: structured reason codes and user/audit mappings.
- `lshell/engine/executor.py`: runtime execution with strict-mode and audit semantics.

## Reason Codes

Primary reason codes are defined in `lshell.engine.reasons`, including:

- `allowed`
- `unknown_syntax`
- `forbidden_control_char`
- `forbidden_character`
- `forbidden_path`
- `forbidden_command`
- `forbidden_sudo_command`
- `forbidden_file_extension`
- `forbidden_env_assignment`
- `forbidden_trusted_protocol`
- `command_not_found`

Mappings:

- `to_policy_message(reason)` for policy-show text.
- `to_audit_reason(reason)` for runtime audit logging.
- `warning_payload(reason)` for strict/warning-counter compatibility hooks.

## Validation

- Unit tests: parser/normalizer/authorizer behavior.
- Security regressions: parser smuggling, substitution checks, and path ACL edge cases.
