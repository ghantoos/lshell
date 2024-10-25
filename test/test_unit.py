""" Unit tests for lshell """

import os
import unittest
from getpass import getuser
from unittest.mock import patch

# import lshell specifics
from lshell.shellcmd import ShellCmd
from lshell.checkconfig import CheckConfig
from lshell.utils import get_aliases, updateprompt
from lshell.variables import builtins_list
from lshell import builtincmd
from lshell import sec

TOPDIR = f"{os.path.dirname(os.path.realpath(__file__))}/../"


class TestFunctions(unittest.TestCase):
    """Unit tests for lshell"""

    args = [f"--config={TOPDIR}/etc/lshell.conf", "--quiet=1"]
    userconf = CheckConfig(args).returnconf()

    def test_03_checksecure_doublepipe(self):
        """U03 | double pipes should be allowed, even if pipe is forbidden"""
        args = self.args + ["--forbidden=['|']"]
        userconf = CheckConfig(args).returnconf()
        input_command = "ls || ls"
        return self.assertEqual(sec.check_secure(input_command, userconf)[0], 0)

    def test_04_checksecure_forbiddenpipe(self):
        """U04 | forbid pipe, should return 1"""
        args = self.args + ["--forbidden=['|']"]
        userconf = CheckConfig(args).returnconf()
        input_command = "ls | ls"
        return self.assertEqual(sec.check_secure(input_command, userconf)[0], 1)

    def test_05_checksecure_forbiddenchar(self):
        """U05 | forbid character, should return 1"""
        args = self.args + ["--forbidden=['l']"]
        userconf = CheckConfig(args).returnconf()
        input_command = "ls"
        return self.assertEqual(sec.check_secure(input_command, userconf)[0], 1)

    def test_06_checksecure_sudo_command(self):
        """U06 | quoted text should not be forbidden"""
        input_command = "sudo ls"
        return self.assertEqual(sec.check_secure(input_command, self.userconf)[0], 1)

    def test_07_checksecure_notallowed_command(self):
        """U07 | forbidden command, should return 1"""
        args = self.args + ["--allowed=['ls']"]
        userconf = CheckConfig(args).returnconf()
        input_command = "ll"
        return self.assertEqual(sec.check_secure(input_command, userconf)[0], 1)

    def test_08_checkpath_notallowed_path(self):
        """U08 | forbidden command, should return 1"""
        args = self.args + ["--path=['/home', '/var']"]
        userconf = CheckConfig(args).returnconf()
        input_command = "cd /tmp"
        return self.assertEqual(sec.check_path(input_command, userconf)[0], 1)

    def test_09_checkpath_notallowed_path_completion(self):
        """U09 | forbidden command, should return 1"""
        args = self.args + ["--path=['/home', '/var']"]
        userconf = CheckConfig(args).returnconf()
        input_command = "cd /tmp/"
        return self.assertEqual(
            sec.check_path(input_command, userconf, completion=1)[0], 1
        )

    def test_10_checkpath_dollarparenthesis(self):
        """U10 | when $() is allowed, return 0 if path allowed"""
        args = self.args + ["--forbidden=[';', '&', '|','`','>','<', '${']"]
        userconf = CheckConfig(args).returnconf()
        input_command = "echo $(echo aze)"
        return self.assertEqual(sec.check_path(input_command, userconf)[0], 0)

    def test_11_checkconfig_configoverwrite(self):
        """U12 | forbid ';', then check_secure should return 1"""
        args = [f"--config={TOPDIR}/etc/lshell.conf", "--strict=123"]
        userconf = CheckConfig(args).returnconf()
        return self.assertEqual(userconf["strict"], 123)

    def test_12_overssh(self):
        """U12 | command over ssh"""
        args = self.args + ["--overssh=['exit']", "-c exit"]
        userconf = CheckConfig(args).returnconf()
        shell = ShellCmd(userconf, args)
        os.environ["SSH_CLIENT"] = "8.8.8.8 36000 22"
        if "SSH_TTY" in os.environ:
            os.environ.pop("SSH_TTY")
        with self.assertRaises(SystemExit) as cm:
            shell.check_scp_sftp()
        return self.assertEqual(cm.exception.code, 0)

    def test_13_multiple_aliases_with_separator(self):
        """U13 | multiple aliases using &&, || and ; separators"""
        # enable &, | and ; characters
        aliases = {"foo": "foo -l", "bar": "open"}
        input_command = "foo; fooo  ;bar&&foo  &&   foo | bar||bar   ||     foo"
        return self.assertEqual(
            get_aliases(input_command, aliases),
            " foo -l; fooo  ; open&& foo -l  " "&& foo -l | open|| open   || foo -l",
        )

    def test_14_sudo_all_commands_expansion(self):
        """U14 | sudo_commands set to 'all' is equal to allowed variable"""
        args = self.args + ["--sudo_commands=all"]
        userconf = CheckConfig(args).returnconf()
        # exclude internal and sudo(8) commands
        exclude = builtins_list + ["sudo"]
        allowed = [x for x in userconf["allowed"] if x not in exclude]
        # sort lists to compare
        userconf["sudo_commands"].sort()
        allowed.sort()
        return self.assertEqual(allowed, userconf["sudo_commands"])

    def test_15_allowed_ld_preload_cmd(self):
        """U15 | all allowed commands should be prepended with LD_PRELOAD"""
        args = self.args + ["--allowed=['echo','export']"]
        userconf = CheckConfig(args).returnconf()
        # sort lists to compare
        return self.assertEqual(
            userconf["aliases"]["echo"], f"LD_PRELOAD={userconf['path_noexec']} echo"
        )

    def test_16_allowed_ld_preload_builtin(self):
        """U16 | builtin commands should NOT be prepended with LD_PRELOAD"""
        args = self.args + ["--allowed=['echo','export']"]
        userconf = CheckConfig(args).returnconf()
        # verify that export is not automatically added to the aliases (i.e.
        # prepended with LD_PRELOAD)
        return self.assertNotIn("export", userconf["aliases"])

    def test_17_allowed_exec_cmd(self):
        """U17 | allowed_shell_escape should NOT be prepended with LD_PRELOAD
        The command should not be added to the aliases variable
        """
        args = self.args + ["--allowed_shell_escape=['echo']"]
        userconf = CheckConfig(args).returnconf()
        # sort lists to compare
        return self.assertNotIn("echo", userconf["aliases"])

    def test_18_forbidden_environment(self):
        """U18 | unsafe environment are forbidden"""
        input_command = "export LD_PRELOAD=/lib64/ld-2.21.so"
        args = input_command
        retcode = builtincmd.export(args)[0]
        return self.assertEqual(retcode, 1)

    def test_19_allowed_environment(self):
        """U19 | other environment are accepted"""
        input_command = "export MY_PROJECT_VERSION=43"
        args = input_command
        retcode = builtincmd.export(args)[0]
        return self.assertEqual(retcode, 0)

    def test_20_winscp_allowed_commands(self):
        """U20 | when winscp is enabled, new allowed commands are automatically
        added (see man).
        """
        args = self.args + ["--allowed=[]", "--winscp=1"]
        userconf = CheckConfig(args).returnconf()
        # sort lists to compare, except 'export'
        exclude = list(set(builtins_list) - set(["export"]))
        expected = exclude + ["scp", "env", "pwd", "groups", "unset", "unalias"]
        expected.sort()
        allowed = userconf["allowed"]
        allowed.sort()
        return self.assertEqual(allowed, expected)

    def test_21_winscp_allowed_semicolon(self):
        """U21 | when winscp is enabled, use of semicolon is allowed"""
        args = self.args + ["--forbidden=[';']", "--winscp=1"]
        userconf = CheckConfig(args).returnconf()
        # sort lists to compare
        return self.assertNotIn(";", userconf["forbidden"])

    def test_22_prompt_short_0(self):
        """U22 | short_prompt = 0 should show dir compared to home dir"""
        expected = f"{getuser()}:~/foo$ "
        args = self.args + ["--prompt_short=0"]
        userconf = CheckConfig(args).returnconf()
        currentpath = f"{userconf['home_path']}/foo"
        prompt = updateprompt(currentpath, userconf)
        # sort lists to compare
        return self.assertEqual(prompt, expected)

    def test_23_prompt_short_1(self):
        """U23 | short_prompt = 1 should show only current dir"""
        expected = f"{getuser()}: foo$ "
        args = self.args + ["--prompt_short=1"]
        userconf = CheckConfig(args).returnconf()
        currentpath = f"{userconf['home_path']}/foo"
        prompt = updateprompt(currentpath, userconf)
        # sort lists to compare
        return self.assertEqual(prompt, expected)

    def test_24_prompt_short_2(self):
        """U24 | short_prompt = 2 should show full dir path"""
        expected = f"{getuser()}: {os.getcwd()}$ "
        args = self.args + ["--prompt_short=2"]
        userconf = CheckConfig(args).returnconf()
        currentpath = f"{userconf['home_path']}/foo"
        prompt = updateprompt(currentpath, userconf)
        # sort lists to compare
        return self.assertEqual(prompt, expected)

    def test_25_disable_ld_preload(self):
        """U25 | empty path_noexec should disable LD_PRELOAD"""
        args = self.args + ["--allowed=['echo','export']", "--path_noexec=''"]
        userconf = CheckConfig(args).returnconf()
        # verify that no alias was created containing LD_PRELOAD
        return self.assertNotIn("echo", userconf["aliases"])

    def test_26_checksecure_quoted_command(self):
        """U26 | quoted command should be parsed"""
        input_command = 'echo 1 && "bash"'
        return self.assertEqual(sec.check_secure(input_command, self.userconf)[0], 1)

    def test_27_checksecure_quoted_command(self):
        """U27 | quoted command should be parsed"""
        input_command = '"bash" && echo 1'
        return self.assertEqual(sec.check_secure(input_command, self.userconf)[0], 1)

    def test_28_checksecure_quoted_command(self):
        """U28 | quoted command should be parsed"""
        input_command = "echo'/1.sh'"
        return self.assertEqual(sec.check_secure(input_command, self.userconf)[0], 1)

    def test_29_env_path_updates_path_variable(self):
        """Test that --env_path updates the PATH environment variable."""
        # store the original $PATH
        original_path = os.environ["PATH"]

        # Simulate passing the --env_path argument
        random_path = "/usr/random:/this_is_a_test"
        args = self.args + [
            f"--env_path='{random_path}'",
        ]
        CheckConfig(args).returnconf()

        # Verify that the $PATH has been updated correctly
        expected_path = f"{random_path}:{original_path}"

        # Assuming CheckConfig sets the environment variable
        self.assertEqual(os.environ["PATH"], expected_path)

        # Reset the PATH environment variable
        os.environ["PATH"] = original_path

    @patch("sys.exit")  # Mock sys.exit to prevent exiting the test on failure
    def test_invalid_new_path(self, mock_exit):
        """Test that an invalid new PATH triggers an error and sys.exit."""
        original_path = os.environ["PATH"]
        random_path = "/usr/random:/invalid$path"
        args = self.args + [
            f"--env_path='{random_path}'",
        ]

        # Simulate passing the --env_path argument
        CheckConfig(args).returnconf()

        # Check that sys.exit was called due to invalid path
        mock_exit.assert_called_once_with(1)

        # The PATH should not have been changed
        self.assertEqual(os.environ["PATH"], original_path)

    @patch("sys.exit")
    def test_new_path_starts_with_colon(self, mock_exit):
        """Test that a new PATH starting with a colon triggers an error."""
        original_path = os.environ["PATH"]
        random_path = ":/usr/random:/this_is_a_test"
        args = self.args + [
            f"--env_path='{random_path}'",
        ]

        # Simulate passing the --env_path argument
        CheckConfig(args).returnconf()

        # Check that sys.exit was called due to invalid path
        mock_exit.assert_called_once()

        # The PATH should not have been changed
        self.assertEqual(os.environ["PATH"], original_path)
