"""CLI entry points for lshell."""

import ast
import os
import signal
import sys
import uuid

from lshell import policy as policy_mode
from lshell import systemsetup as system_setup
from lshell.checkconfig import CheckConfig
from lshell.shellcmd import LshellTimeOut, ShellCmd


def main():
    """Main CLI entry point."""
    if len(sys.argv) > 1 and sys.argv[1] == "policy-show":
        sys.exit(policy_mode.main(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "setup-system":
        sys.exit(system_setup.main(sys.argv[2:]))

    # Set SHELL and process LSHELL_ARGS env variables.
    os.environ["SHELL"] = os.path.realpath(sys.argv[0])
    if "LSHELL_ARGS" in os.environ:
        try:
            parsed_args = ast.literal_eval(os.environ["LSHELL_ARGS"])
        except (ValueError, SyntaxError):
            parsed_args = []
        if not isinstance(parsed_args, (list, tuple)) or not all(
            isinstance(item, str) for item in parsed_args
        ):
            parsed_args = []
        args = sys.argv[1:] + list(parsed_args)
    else:
        args = sys.argv[1:]

    userconf = CheckConfig(args).returnconf()
    userconf["session_id"] = os.environ.get("LSHELL_SESSION_ID", uuid.uuid4().hex)
    os.environ["LSHELL_SESSION_ID"] = userconf["session_id"]

    def disable_ctrl_z(_signum, _frame):
        return None

    signal.signal(signal.SIGTSTP, disable_ctrl_z)

    cli = ShellCmd(userconf, args)
    try:
        while True:
            try:
                cli.cmdloop()
                break
            except KeyboardInterrupt:
                # Keep interactive sessions alive when Ctrl+C races outside
                # command-specific handlers.
                sys.stdout.write("\n")
                continue
            except EOFError:
                sys.stdout.write("\nExited on user request\n")
                sys.exit(0)
    except LshellTimeOut:
        userconf["logpath"].error("Timer expired")
        sys.stdout.write("\nTime is up.\n")
