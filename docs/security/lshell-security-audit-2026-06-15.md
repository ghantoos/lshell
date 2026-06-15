# `lshell` Security Audit

Date: `2026-06-15`

## Executive Summary

No evidence of a hidden backdoor, botnet logic, or covert outbound command-and-control behavior was found. The main risk is different: the restricted shell boundary can be weakened or bypassed through ordinary, supported code paths.

Three security issues stand out:

1. A user can manipulate environment variables so that an allowed command triggers an additional disallowed command inside `bash`.
2. `source` is enabled by default even when `export` is not, which leaves an alternate path for modifying the shell environment.
3. `LSHELL_ARGS` is accepted from the environment during startup, which can let external state influence security-sensitive startup options.

In practical terms, these issues mean a restricted user may be able to bypass part of the shell policy or run commands that were never meant to be allowed.

## What `lshell` Does

`lshell` is a restricted shell. Instead of dropping the user directly into a normal login shell such as `bash` or `sh`, it places the user inside an application that tries to limit:

- which commands may run
- which filesystem paths may be accessed
- which shell features may be used
- which remote command patterns are accepted over `SSH`, `SCP`, and `SFTP`

At a high level, command flow looks like this:

1. Startup arguments are processed in `lshell/cli.py`.
2. Configuration is loaded and normalized in `lshell/checkconfig.py`.
3. Interactive command handling runs through `lshell/shellcmd.py`.
4. Command parsing, policy checks, and execution orchestration run through `lshell/utils.py`.
5. Allowed commands are eventually executed through `subprocess.Popen(...)`.

Code references:

- `lshell/cli.py:18-87`
- `lshell/checkconfig.py:42-67`
- `lshell/shellcmd.py:26-300`
- `lshell/utils.py:526-877`
- `lshell/utils.py:880-1023`

## How a Normal Command Reaches Execution

When a user enters a command such as `echo hi`, the path is:

1. `ShellCmd` receives the input.
2. `utils.cmd_parse_execute(...)` is called.
3. The same path in `lshell/utils.py` breaks the command into segments and operators.
4. Policy checks decide whether the command, its arguments, and any referenced paths are allowed.
5. If the command passes, `utils.exec_cmd(...)` runs it.
6. For ordinary commands, `exec_cmd(...)` normally executes the final string through a real shell, effectively `bash -c "echo hi"`.

That last step matters. Any weakness that changes how `bash -c` interprets its environment can undermine the checks that happened earlier.

Code references:

- `lshell/utils.py:526-577`
- `lshell/utils.py:618-808`
- `lshell/utils.py:976-999`

## Review Method

The review was carried out in three layers:

1. Repository-wide searching for high-risk execution, environment, and transport surfaces.
2. Direct review of the main startup, policy, and command-execution paths.
3. Targeted proof-of-concept checks to verify whether suspicious behavior was actually reachable.

## Backdoor and Botnet Assessment

The review looked for:

- covert network connections
- hidden command download or execution paths
- suspicious dynamic loading behavior
- hard-coded control endpoints
- unusual use of modules such as `socket`, `requests`, `urllib`, `httpx`, `ftplib`, `telnetlib`, or `paramiko`

No clear sign of that class of behavior was found in the main runtime modules. The network-related code that appears in the repository is consistent with expected project behavior:

- `SSH`, `SCP`, and `SFTP` support
- container and integration-test setup
- Debian and RPM packaging helpers

The main security concerns are therefore policy bypasses inside ordinary shell behavior, not hidden remote-control logic.

## Issue 1: Disallowed Command Execution Through Environment Variable Manipulation

### Plain-Language Summary

A user can set environment variables so that an allowed command causes an extra, disallowed command to run behind the scenes.

This does not happen because `lshell` explicitly authorizes the second command. It happens because `bash` interprets inherited environment state in a dangerous way.

### Why This Matters

The central promise of a restricted shell is simple: users should only be able to run commands that policy allows. If an allowed command can be turned into a carrier for another command, the allow-list is no longer a real boundary.

### Conditions Required

This issue becomes reachable when all of the following are true:

1. The user can introduce or change environment variables inside the shell session.
2. At least one of these paths is available:
   - `export`
   - `source`
   - configuration-driven environment file loading
3. Final command execution still goes through `bash -c` or an equivalent shell execution path.

In this implementation, the third condition is true by design, and the first two are realistic in many configurations.

### Step-by-Step Execution Path

#### Step 1: The shell allows some dangerous environment variables to be set

`cmd_export(...)` blocks only a limited set of forbidden variables listed in `variables.FORBIDDEN_ENVIRON`.

That list does not include several environment variables that can materially change shell behavior, including:

- `SHELLOPTS`
- `BASHOPTS`
- `PS4`
- `PROMPT_COMMAND`
- `CDPATH`
- `GLOBIGNORE`
- `IFS`
- `PYTHONPATH`

Code references:

- `lshell/builtincmd.py:129-142`
- `lshell/variables.py:118-144`

#### Step 2: The same environment is later inherited by command execution

Inside `exec_cmd(...)`, the runtime environment starts as a full copy of `os.environ`.

Only a very small cleanup happens before the command is executed:

- `BASH_ENV` is removed
- `ENV` is removed
- names starting with `BASH_FUNC_` are stripped

There is no broader scrub of shell-sensitive variables before `bash` is launched.

Code references:

- `lshell/utils.py:880-903`

#### Step 3: Normal commands are executed through `bash -c`

For non-`sudo` and non-`su` commands, the execution path uses:

```python
cmd_args = ["bash", "-c", cmd]
```

That means the final command string is interpreted by a real `bash` process.

Code references:

- `lshell/utils.py:976-982`

#### Step 4: `bash` interprets the manipulated environment

If a user enables shell tracing through `SHELLOPTS=xtrace`, then `bash` uses `PS4` as the prefix for trace lines. If `PS4` contains command substitution, the shell evaluates that content while running the apparently safe command.

At that point, the extra command is no longer passing through the original allow-list decision. `lshell` has already approved the outer command and handed execution to `bash`.

### Simple Demonstration

A minimal demonstration is:

```bash
export SHELLOPTS=xtrace
export PS4='$(echo LSHELL_POC >&2) '
echo hi
```

In practice, this causes `LSHELL_POC` to be emitted before `echo hi` completes. The point of the demonstration is not the output itself. The point is that content inside `PS4` gets executed by `bash`.

If the payload inside `PS4` is replaced with a real system command, that command runs outside the intended command policy boundary.

### Practical Impact

This issue can let a restricted user:

1. run a command that appears to be allowed
2. trigger a second command in the background execution path
3. execute a command that is not in the configured allow-list

In practical terms, the allow-list stops being the effective security boundary.

### Severity

This issue should be treated as `Critical` because it directly breaks the restricted-shell security model.

### Practical Fix

This issue should be fixed in layers. Blocking one or two additional variables is not enough on its own.

#### Layer 1: Rebuild and filter the execution environment instead of blindly making it tiny

The correct security principle is for `exec_cmd(...)` to build a new execution environment instead of copying all of `os.environ`. But that must not be done in a naive way.

In plain terms:

- current unsafe pattern: take everything, then remove a few entries
- safer pattern: build a new environment, take only values from trusted state, and discard the rest

This change belongs in `lshell/utils.py`, inside `exec_cmd(...)`.

Code references:

- `lshell/utils.py:880-903`

Several existing behaviors in this implementation show why a tiny fixed environment would break legitimate features:

1. Variables defined through `env_vars` and `env_vars_files` are meant to reach later commands. That path is implemented by writing into `os.environ` and by calling `cmd_source(...)` from `check_env(...)`.
2. `env_path` and `allowed_cmd_path` modify `PATH`, and later command resolution depends on that `PATH`.
3. The existing behavior allows an assignment-only statement such as `LSH_PERSIST=YES` to remain in the shell environment for later commands.
4. Existing tests explicitly expect variables loaded from environment files to be visible to later commands such as `echo $bar`.

Code references:

- `lshell/checkconfig.py:140-150`
- `lshell/checkconfig.py:711-749`
- `test/test_env_vars_files_unit.py:19-47`
- `test/test_env_vars.py:84-125`
- `test/test_security_hardening_functional.py:60-77`

The initial safe set therefore needs to include at least:

- `HOME`
- `USER`
- `LOGNAME`
- `TERM`
- `LANG`
- `LC_*`

And in addition, these values need to be preserved or rebuilt in a controlled way:

- `PATH`, but only from values constructed or validated by `lshell`
- variables coming from `env_vars`
- variables coming from `env_vars_files`
- variables that the shell intentionally keeps in session state

The practical conclusion is that the right fix is not a tiny fixed environment. The right fix is a filtered environment rebuilt from trusted shell state.

#### Layer 2: If any inheritance remains, expand the forbidden-variable set

If the project still needs to inherit part of the environment, then at minimum the forbidden set should be expanded to include:

- `SHELLOPTS`
- `BASHOPTS`
- `PS4`
- `PROMPT_COMMAND`
- `CDPATH`
- `GLOBIGNORE`
- `IFS`
- `PYTHONPATH`

Any `BASH_FUNC_*` names should also be blocked consistently.

This enforcement should happen in two places:

1. when variables enter through `export` or `source`
2. when the final execution environment is assembled before `subprocess.Popen(...)`

Code references:

- `lshell/builtincmd.py:129-142`
- `lshell/builtincmd.py:145-155`
- `lshell/variables.py:118-144`
- `lshell/utils.py:880-903`

This layer also has compatibility impact:

1. shell customizations that rely on variables such as `CDPATH` or `IFS` will stop working
2. an allowed Python program that depends on `PYTHONPATH` may no longer behave the same way
3. if an administrator currently injects any of these variables through `env_vars` or `env_vars_files`, those settings will need to be revisited

That compatibility cost is acceptable for a hardened restricted shell, but it should be explicit.

#### Layer 3: Remove the `bash -c` dependency if the design allows it

This is the strongest security improvement, but it is not the lowest-risk fix. As long as ordinary commands are executed through `bash -c`, `bash` remains a large interpretation surface.

If the architecture allows it, ordinary commands should move toward direct execution without an intermediate shell, with the command and arguments passed straight to `subprocess.Popen(...)`.

Code references:

- `lshell/utils.py:976-999`

In this implementation, that is a major behavioral change because existing tests depend on shell semantics. For example:

1. pipelines need to work
2. redirections need to work
3. `&&` and `||` need to behave like shell operators
4. command substitution in `$(...)` and variable expansion such as `${HOME}` need to work

Code references:

- `test/test_command_execution.py:229-257`
- `test/test_command_execution.py:279-317`

#### Tests That Should Be Added

At minimum, add regression tests that prove:

1. `export SHELLOPTS=...` is rejected
2. `export PS4=...` is rejected
3. `source` rejects the same variables
4. `exec_cmd("echo hi")` is no longer affected by inherited `SHELLOPTS` and `PS4`

Good candidate test files:

- `test/test_source_command_unit.py`
- `test/test_security_hardening_functional.py`
- `test/test_user_behavior_security_functional.py`

## Issue 2: `source` Leaves an Alternate Path Around Disabled `export`

### Plain-Language Summary

The project tries not to enable `export` by default, but `source` is still enabled by default and can load exported variables from files into the shell environment.

As a result, the absence of `export` does not actually mean environment changes are blocked.

### Why This Matters

Issue 1 depends on the user being able to inject environment state. Issue 2 shows that the same capability remains available even when `export` is not part of the default allowed command set.

### Step-by-Step Execution Path

#### Step 1: `export` is excluded from the default built-in allow-list

During configuration assembly, the code adds built-ins to the allowed set but excludes `export`.

Code references:

- `lshell/checkconfig.py:725-726`

#### Step 2: `source` remains part of the default built-in set

`source` is still listed in `builtins_list`, so it remains available by default unless configuration removes it explicitly.

Code references:

- `lshell/builtincmd.py:24-43`

#### Step 3: `source` reads files and forwards `export ...` lines to `cmd_export(...)`

`cmd_source(...)` opens the target file and forwards lines beginning with `export ` to `cmd_export(...)`.

Code references:

- `lshell/builtincmd.py:140-155`

#### Step 4: Environment changes happen even when `export` is not allowed

In practical terms, a user can still load:

```text
export TEST_FROM_SOURCE=ok
```

through `source`, and the variable enters `os.environ` even though direct use of `export` was meant to be blocked by policy.

### When This Becomes More Dangerous

The issue is worse when:

1. the user can write files inside allowed paths
2. the operator assumes disabling `export` is enough to prevent environment manipulation
3. `source` is available for convenience in interactive sessions

### Practical Impact

`source` is not always a complete breakout by itself, but it is a direct enabler for Issue 1. It keeps open the exact environment-modification path the configuration appears to be trying to close.

In plain terms:

- `export` is closed
- `source` reopens the same door from another angle

### Severity

This issue should be treated as `High` because it defeats a visible hardening decision and helps enable a larger policy bypass.

### Practical Fix

The safest fix is to stop enabling `source` by default for general users.

#### Option 1: Remove `source` from the default built-in allow-list

This is the clearest default behavior:

- `source` should not be enabled by default
- it should only become available when an administrator opts into it explicitly

Code references:

- `lshell/builtincmd.py:24-43`
- `lshell/checkconfig.py:725-726`

#### Option 2: If `source` remains, prefer a separate explicit permission over reopening `export`

If the project does not want to remove `source` entirely, one of these policies should be used:

1. `source` should only be allowed when an administrator explicitly enables it in `allowed` or through a dedicated configuration key
2. a separate configuration key such as `allow_source=1` should control it, with a default of disabled

In practice, a separate key is safer than tying `source` directly to `export`, because reopening `export` broadens the attack surface again.

#### Option 3: Restrict `source` to trusted files only

If `source` is operationally necessary, it should load only:

- files from approved paths
- files named in administrator-controlled configuration
- files the restricted user cannot freely modify

Otherwise any writable allowed path can become an environment-injection surface.

#### Tests That Should Be Added

At minimum, add regression tests that prove:

1. `source` is not available by default
2. if `source` is enabled, dangerous variables are still rejected
3. `source` cannot silently restore the same power that blocking `export` was meant to remove

Good candidate test files:

- `test/test_source_command_unit.py`
- `test/test_builtins.py`
- `test/test_env_vars_files_unit.py`
- `test/test_completion.py`

## Issue 3: `LSHELL_ARGS` Can Influence Security-Sensitive Startup Behavior

### Plain-Language Summary

At startup, the program reads `LSHELL_ARGS` from the environment and merges it into the effective argument list. That means external environment state can shape startup behavior before the restricted shell has fully established its security posture.

### Why This Matters

In a security-oriented program, startup policy should come from a trusted boundary. Reading arbitrary startup arguments from the environment weakens that boundary.

### Step-by-Step Execution Path

#### Step 1: Startup reads `LSHELL_ARGS`

`lshell/cli.py` checks whether `LSHELL_ARGS` exists. If it does, it parses the value with `ast.literal_eval(...)`.

If the result is a `list` or `tuple` of strings, the values are merged into the active argument list.

Code references:

- `lshell/cli.py:27-40`

#### Step 2: The merged arguments are passed into configuration loading

After that merge, the combined list is passed into `CheckConfig(args).returnconf()`.

Code references:

- `lshell/cli.py:42`

#### Step 3: `CheckConfig` reads security-sensitive startup options from those arguments

`getoptions(...)` parses startup options and stores them in the configuration dictionary.

Code references:

- `lshell/checkconfig.py:94-138`

#### Step 4: Some of those options directly affect security behavior

The available startup options include settings such as:

- `allowed=`
- `forbidden=`
- `strict=`
- `path_noexec=`
- `allowed_shell_escape=`
- `winscp=`

Code references:

- `lshell/variables.py:100-115`

### When This Becomes Exploitable

This issue matters only when `LSHELL_ARGS` can realistically reach the process from outside. That can happen through:

1. an `SSH` configuration that preserves user-controlled environment variables
2. wrapper scripts that pass inherited environment state into `lshell`
3. service managers or control panels that launch `lshell` with inherited environment variables
4. reused process environments where the variable was already set

If none of those conditions exist, exploitability may be limited. Even so, the startup trust model is weaker than it should be.

### Practical Impact

If `LSHELL_ARGS` is user-controlled at process start, the user may be able to:

1. change the allowed command set
2. weaken or remove restrictions
3. disable or erode protections such as `path_noexec`

In plain terms, the shell may start with a different policy than the administrator intended.

### Severity

This issue should be treated as `High`. Its exploitability depends on deployment details, but the effect is direct and serious when the environment is not tightly controlled.

### Practical Fix

The fix belongs at the trust boundary. Security-sensitive startup behavior should not accept arbitrary environment-provided arguments.

#### Option 1: Stop reading free-form `LSHELL_ARGS` at startup

The lowest-risk change is:

- do not treat `LSHELL_ARGS` as a general startup argument source
- use only `sys.argv` for effective startup options

Code references:

- `lshell/cli.py:27-40`

There is an important detail here. `CheckConfig.getoptions(...)` also writes `LSHELL_ARGS` back into the environment after parsing arguments, using `--config` and, if present, `--log`. That means `LSHELL_ARGS` is not only an outside input today. It is also part of the internal mechanism used to preserve the active config path and log path.

Code references:

- `lshell/checkconfig.py:126-131`

As a result, removing `LSHELL_ARGS` reading completely and all at once can have side effects:

1. any internal path that relies on inheriting `--config` or `--log` from the environment will no longer receive the same settings
2. any nested or internal `lshell` execution that relies only on `$SHELL` and inherited environment may fall back to the default config instead of the previously selected one
3. the existing `test_main_appends_valid_lshell_args_from_env` behavior will need to be rewritten along with the new policy

Code references:

- `test/test_cli_unit.py:49-64`

#### Option 2: If the mechanism must remain, allow only a very small safe subset

If the project still needs this mechanism for internal re-execution, only clearly harmless options should survive environment loading, for example:

- `--config`
- `--log`

Security-sensitive options such as `--allowed=all` or `--path_noexec=` should be ignored if they come from the environment.

#### Option 3: Use a dedicated internal-only restart channel

If internal restart behavior is required, use a narrower mechanism that is clearly separate from general user-controlled startup state:

1. define a dedicated internal restart variable
2. read it only in a known internal restart mode
3. never accept security-sensitive policy options from it

#### Tests That Should Be Added

At minimum, add regression tests that prove:

1. `LSHELL_ARGS=['--allowed=all']` does not change policy
2. unsafe options coming from `LSHELL_ARGS` are ignored
3. if a safe subset remains, only `--config` and `--log` are honored

Good candidate test files:

- `test/test_cli_unit.py`

## How the Three Issues Reinforce Each Other

These issues are not isolated.

1. Issue 2 preserves a path for injecting environment variables.
2. Issue 1 uses that injected environment state to execute commands outside the intended policy boundary.
3. Issue 3 can weaken startup protections before the session even begins.

The main risk is therefore the chain, not just the individual bugs in isolation.

## Operational Impact of Each Remediation

One question matters as much as the findings themselves: what happens to real program behavior if these fixes are applied?

The short answer is that the remediations do not all carry the same implementation risk. Some are well suited for a low-risk hotfix. Some require compatibility work and test updates. Some are architectural changes rather than quick patches.

### Remediation 1: Stop reading free-form `LSHELL_ARGS` at startup

This change is necessary from a security perspective, but it is not side-effect free if done as a simple on-off switch.

Why? Because two behaviors exist at the same time:

1. `cli.main()` reads `LSHELL_ARGS` from the environment and appends it to `sys.argv`.
2. `CheckConfig.getoptions(...)` writes `LSHELL_ARGS` back into the environment using `--config` and `--log`.

Code references:

- `lshell/cli.py:27-40`
- `lshell/checkconfig.py:126-131`

Practical effect of this change:

1. a direct invocation such as `lshell --config ...` remains mostly unchanged
2. any internal or nested path that relies on inheriting `--config` and `--log` from the environment will no longer behave the same way
3. the existing `test/test_cli_unit.py` expectations for valid environment-appended arguments will need to change

Code references:

- `test/test_cli_unit.py:49-64`

Practical conclusion:

- this change is a good hotfix candidate, as long as it is not implemented as a blunt full removal
- the safest version is to keep only `--config` and `--log`, or move internal restart behavior to a separate variable
- without a compatibility path, some nested invocations or old wrapper flows may unexpectedly fall back to the default config

### Remediation 2: Harden the execution environment and expand forbidden environment variables

This change is highly important, but its main risk is that an oversimplified implementation can break legitimate shell behavior.

Several existing behaviors depend on the present environment model:

1. `env_vars` writes variables directly into `os.environ`
2. `env_vars_files` reads files through `cmd_source(...)` and applies results to the same live environment
3. `env_path` and `allowed_cmd_path` modify `PATH`
4. assignment-only lines such as `LSH_PERSIST=YES` are meant to persist in session state
5. assignment prefixes such as `A=INLINE printenv A` are meant to affect only the current command

Code references:

- `lshell/checkconfig.py:140-150`
- `lshell/checkconfig.py:711-749`
- `lshell/utils.py:880-903`
- `test/test_env_vars.py:84-125`
- `test/test_env_vars.py:188-203`
- `test/test_security_hardening_functional.py:48-77`

If execution is reduced to a very small fixed environment, these side effects are likely:

1. `echo $bar` for variables loaded from `env_vars_files` may stop working
2. variables set by the administrator through `env_vars` may stop reaching some external commands
3. the effect of `env_path` and `allowed_cmd_path` on command resolution may disappear unless `PATH` is rebuilt from trusted values
4. locale and terminal behavior tied to `LANG`, `TERM`, or `LC_*` may degrade

Code references:

- `test/test_env_vars.py:108-125`
- `test/test_unit.py:254-270`

On the other side, simply expanding the forbidden list also has compatibility cost:

1. workflows that intentionally rely on `CDPATH`, `IFS`, or `PYTHONPATH` will no longer behave the same way
2. if the administrator currently injects any of those variables through `env_vars` or `env_vars_files`, that configuration will need review

Practical conclusion:

- this is also a good hotfix candidate, but not with a tiny static environment
- the lower-risk version is to rebuild `exec_env` from trusted shell state, rebuild `PATH` separately, and strip only dangerous names
- this is a medium-risk change because it improves security while also exposing hidden compatibility assumptions

### Remediation 3: Remove `source` from the default command set

This is a sensible security improvement. But in the present behavior of the project, `source` is not just a minor convenience command. Several parts of the project assume its presence either directly or indirectly.

Code references:

- `lshell/builtincmd.py:24-43`
- `lshell/checkconfig.py:140-150`
- `lshell/checkconfig.py:725-726`

Practical effect of this change:

1. help output and command completion should no longer list `source` by default
2. tests that expect `source` in the default command set will need to change
3. if the same `cmd_source(...)` function is used both for user-facing `source` and for internal `env_vars_files` loading, closing the interactive command must not break internal environment-file loading

Code references:

- `test/test_completion.py:33-55`
- `test/test_ps2.py:13-29`
- `test/test_scripts.py:13-31`
- `test/test_security.py:13-28`
- `test/test_env_vars_files_unit.py:19-47`

The right fix is therefore not just removing one name from `builtins_list`. The right fix is:

1. separate internal environment-file loading from the interactive user command path
2. make `source` available only by explicit administrator choice
3. apply the same dangerous-variable filtering when `source` is enabled

Practical conclusion:

- this is a medium-risk change
- it is worthwhile, but it affects help output, completion, tests, and internal environment-file loading
- if it is implemented bluntly, an administrator may think only an interactive command was closed while internal environment-file loading was silently broken too

### Remediation 4: Remove `bash -c` and move to direct shellless execution

This is the best long-term security state, but for this code it is an architectural change rather than a quick fix.

The reason is simple: the implementation depends heavily on shell semantics, and the tests make that dependency explicit:

1. pipelines such as `printf foo | wc -c` must work
2. redirections such as `>`, `>>`, and `2>&1` must work
3. operators such as `&&` and `||` must work
4. command substitution such as `$(...)` and expansions such as `${HOME}` must work

Code references:

- `lshell/utils.py:976-999`
- `test/test_command_execution.py:229-257`
- `test/test_command_execution.py:279-317`

If `bash -c` is removed without a replacement design, a large part of existing behavior will either stop working or need to be reimplemented inside `lshell`.

Practical conclusion:

- this is not a good hotfix candidate
- this is a high-risk architectural change
- it should be handled as a later design phase, not as the first security patch

## Practical Remediation Plan

If these issues are going to be fixed with the best balance of security and implementation risk, the work should be ordered by real change risk, not only by raw vulnerability severity.

### Phase 1: Low-risk hotfix for the startup trust boundary

Start by closing the trust boundary at startup. This change has direct security value and can be made with the least disruption if done carefully.

Work items:

1. stop accepting free-form `LSHELL_ARGS` from the environment
2. keep only `--config` and `--log` if they are genuinely needed
3. or replace the mechanism with a separate internal-only restart variable
4. rewrite `test/test_cli_unit.py` to reflect the new policy

Primary files:

- `lshell/cli.py`
- `lshell/checkconfig.py`
- `test/test_cli_unit.py`

### Phase 2: Harden final command execution with controlled compatibility risk

Then harden the final execution boundary in a way that does not unnecessarily break legitimate behavior.

Work items:

1. rebuild `exec_env` from trusted shell state
2. expand the forbidden variable set to include `SHELLOPTS`, `PS4`, `BASHOPTS`, `IFS`, `PYTHONPATH`, and similar names
3. rebuild `PATH` from trusted `env_path` and `allowed_cmd_path` state
4. add regression tests proving that required allowed variables still work

Primary files:

- `lshell/utils.py`
- `lshell/variables.py`
- `lshell/checkconfig.py`
- `test/test_source_command_unit.py`
- `test/test_env_vars.py`
- `test/test_security_hardening_functional.py`

### Phase 3: Close the user-facing helper path through `source`

After that, reduce the user's ability to modify the environment through the interactive shell, without breaking internal environment-file loading.

Work items:

1. remove `source` from the default built-in set
2. split internal `env_vars_files` loading from the user-facing `source` command
3. require explicit administrator permission before `source` is available
4. apply the same dangerous-variable filtering to `source`

Primary files:

- `lshell/builtincmd.py`
- `lshell/checkconfig.py`
- `test/test_builtins.py`
- `test/test_env_vars_files_unit.py`
- `test/test_completion.py`

### Phase 4: Architectural work to remove the `bash -c` dependency

This phase should start only if the project is ready to revisit its execution model.

Work items:

1. decide which shell behaviors must remain supported and which should be deliberately removed
2. move ordinary command execution to direct `subprocess.Popen(...)` calls without an intermediate shell
3. rewrite or remove tests that currently depend on full `bash` behavior

Primary files:

- `lshell/utils.py`
- `test/test_command_execution.py`
- `test/test_security_hardening_functional.py`

## What Kind of Unauthorized Access These Issues Create

The phrase "unauthorized access" can mean different things, so it should be stated clearly.

In this project, the main effect is:

1. a restricted user may run a command that policy was supposed to deny
2. the user may bypass part of the shell policy boundary
3. if that same account already has useful filesystem, group, or `sudo` privileges, the bypass can lead to more serious damage

These issues do not automatically guarantee full root access. They do, however, break the central security boundary that the restricted shell is supposed to enforce.

## Why These Findings Are Serious Even Though They Are Not Classic Backdoors

A classic backdoor usually means:

- intentionally hidden access logic
- or covert communication with an outside operator

That is not what appears here. The issues are design and hardening problems inside legitimate code paths.

From an operational security perspective, the outcome is still serious. A restricted shell that can be bypassed is not providing the boundary it claims to provide.

## Most Important Files for Following the Audit

If this audit needs to be followed directly in code, these are the main entry points:

### Startup

- `lshell/cli.py:18-87`

### Configuration loading

- `lshell/checkconfig.py:57-67`
- `lshell/checkconfig.py:94-150`
- `lshell/checkconfig.py:711-749`

### Built-in commands

- `lshell/builtincmd.py:24-43`
- `lshell/builtincmd.py:124-155`

### Forbidden environment-variable list

- `lshell/variables.py:118-144`

### Command parsing, policy checks, and orchestration

- `lshell/utils.py:526-877`

### Final command execution

- `lshell/utils.py:880-1023`

## Final Assessment

Stated plainly:

1. no hidden backdoor or botnet-style control logic was found
2. three real security weaknesses can still undermine the core purpose of the project
3. the most dangerous issue is the ability to influence `bash` through inherited environment state and trigger extra command execution
4. the second issue is that `source` leaves open the same environment-modification capability that disabling `export` appears to close
5. the third issue is that `LSHELL_ARGS` allows outside state to influence startup policy

If `lshell` is expected to serve as a real isolation boundary for semi-trusted or untrusted users, it should not be relied on in this form without hardening these paths and keeping them covered by regression tests.

## Recommended Next Order of Work

The most practical order of work is:

1. stop free-form `LSHELL_ARGS` handling while keeping only safe internal paths
2. harden `exec_env` by rebuilding it from trusted state and blocking dangerous variables
3. remove `source` from the default user-facing command set and separate it from internal `env_vars_files` loading
4. leave `bash -c` removal for a later architectural phase
