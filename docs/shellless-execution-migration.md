# Shellless Execution Migration

This change removes implicit runtime `shell -c` execution and introduces an explicit
runtime executor mode switch:

- `runtime_executor=shellless` (default, hardened/fail-closed)
- `runtime_executor=bash_compat` (explicit compatibility opt-in)

## Compatibility Matrix

| Feature | Policy/Parser Handling | `shellless` Runtime | `bash_compat` Runtime | Notes |
| --- | --- | --- | --- | --- |
| Quoting (`'...'`, `"..."`, escapes) | Parsed by `shlex` and engine splitters | Supported | Supported | Quoting is parsed by lshell in shellless; delegated to bash in compat mode. |
| Variable expansion (`$VAR`, `${...}` subset) | Authorized through expansion inspector checks | Supported for lshell-supported forms via `expand_vars_quoted` | Supported by bash | Unsupported/unsafe forms remain fail-closed in policy path. |
| Globbing (`*`, `?`, `[]`, brace patterns) | Path ACL checks expand wildcard/brace forms for authorization | No implicit shell glob expansion at execution time | Bash globbing semantics | Path ACL checks still run before execution. |
| Pipelines (`|`) | Parsed by canonical engine | Supported via explicit `Popen` pipe wiring | Supported via bash parser/executor | Runtime containment still applies per execution mode constraints. |
| `&&`, `||`, `;`, `&` | Canonical engine sequencing/branching logic | Supported | Supported |  |
| Command substitution (`$(...)`, `` `...` ``) | Nested commands still recursively authorized (allowlist/path) | Unsupported at runtime (fail-closed) | Allowed (historic behavior) | |
| Process substitution (`<(...)`, `>(...)`) | Nested commands still recursively authorized (allowlist/path) | Unsupported at runtime (fail-closed) | Allowed (historic behavior) | |
| Redirections (`>`, `<`, `>>`, `2>&1`, here-doc/here-string forms) | Existing checks continue to classify malformed forms | Unsupported at runtime (fail-closed) | Supported by bash syntax, still subject to policy checks | Forbidden-character config can still block metacharacters. |

### Runtime Executor Matrix

| `runtime_executor` | Effective behavior |
| --- | --- |
| `shellless` | Hardened mode: command/process substitution denied at runtime. |
| `bash_compat` | Compatibility mode: command/process substitution allowed (historic behavior). |

## Security Outcome

- Default mode (`shellless`) keeps fail-closed behavior with no external shell parser.
- `bash_compat` uses only trusted absolute bash candidates (`/bin/bash`, `/usr/bin/bash`, etc.); no PATH-based interpreter lookup is used.
- Nested allowlist/path checks for commands inside substitutions remain enforced before execution.
- Environment hardening remains in place for both modes: `BASH_ENV`, `ENV`, and `BASH_FUNC_*` are stripped from child envs.
- `sudo_noexec` probe remains shellless and uses a trusted absolute `true` binary.

## Known Compatibility Tradeoffs

1. `bash_compat` is a compatibility mode and broadens runtime shell semantics versus `shellless`.
2. In `shellless`, shell-only forms (substitution/redirection) are denied explicitly.
3. In `bash_compat`, runtime containment limits such as pipeline-stage counting apply to the outer bash process, not each shell-internal stage.
