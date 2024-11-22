""" This module is used to run all the tests in the test directory. """

from test import (
    test_builtins,
    test_command_execution,
    test_completion,
    test_config,
    test_env_vars,
    test_exit,
    test_file_extension,
    test_path,
    test_ps2,
    test_regex,
    test_scripts,
    test_security,
    test_signals,
    test_ssh,
    test_unit,
)


if __name__ == "__main__":
    test_builtins.unittest.main()
    test_command_execution.unittest.main()
    test_completion.unittest.main()
    test_config.unittest.main()
    test_env_vars.unittest.main()
    test_exit.unittest.main()
    test_file_extension.unittest.main()
    test_path.unittest.main()
    test_ps2.unittest.main()
    test_regex.unittest.main()
    test_scripts.unittest.main()
    test_security.unittest.main()
    test_signals.unittest.main()
    test_ssh.unittest.main()
    test_unit.unittest.main()
