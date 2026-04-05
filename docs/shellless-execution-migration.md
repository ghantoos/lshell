# Shellless Execution Migration

This change removes runtime `shell -c` command execution from `lshell.utils.exec_cmd`
and replaces it with direct `subprocess.Popen(shell=False)` invocation.

## Compatibility Matrix

| Feature | Policy/Parser Handling | Runtime Behavior (Shellless) | Notes |
| --- | --- | --- | --- |
| Quoting (`'...'`, `"..."`, escapes) | Parsed by `shlex` and engine splitters | Supported | Quoting is interpreted by lshell parsing, not by an external shell. |
| Variable expansion (`$VAR`, `${...}` subset) | Authorized through existing expansion inspector checks | Supported for lshell-supported forms via `expand_vars_quoted(..., support_advanced_braced=True)` | Unsupported `${...}` forms remain fail-closed via existing parser/authorizer safeguards. |
| Globbing (`*`, `?`, `[]`, brace patterns) | Path ACL checks still expand wildcards/brace forms for authorization | No implicit shell glob expansion at execution time | Commands receive literal operands unless tool itself expands internally. |
| Pipelines (`|`) | Parsed at top level by canonical engine | Supported | Implemented by manually wiring `stdout` -> `stdin` between `Popen` stages. |
| `&&`, `||`, `;`, `&` | Canonical engine handles sequencing/branching/background logic | Supported | No delegation to shell operator parsing. |
| Command substitution (`$(...)`, `` `...` ``) | Still inspected recursively for allowlist/path policy | Unsupported at runtime (fail closed) | Executor returns unknown-syntax denial with explicit unsupported-shell message. |
| Process substitution (`<(...)`, `>(...)`) | Still inspected recursively for allowlist/path policy | Unsupported at runtime (fail closed) | Same fail-closed runtime path as above. |
| Redirections (`>`, `<`, `>>`, `2>&1`, here-doc/here-string forms) | Existing checks continue to classify malformed forms | Unsupported at runtime (fail closed) | Runtime rejects unquoted redirection markers explicitly. |

## Security Outcome

- No interpreter invocation through `PATH` for command execution (`shell -c` removed).
- No implicit shell metacharacter execution path remains in `exec_cmd`.
- Existing environment scrubbing (`BASH_ENV`, `ENV`, `BASH_FUNC_*`) remains in place.

## Known Compatibility Tradeoffs

1. Shell-only runtime syntax (command/process substitution, redirection forms) is now denied explicitly rather than delegated.
2. Execution-time shell glob expansion is not performed; path policy wildcard validation remains unchanged.
3. Workflows that depended on shell redirection side effects must use allowed helper tools instead of inline shell redirection syntax.
