""" Unit tests for lshell """

import os
import unittest
from getpass import getuser
from time import strftime, gmtime
from unittest.mock import patch

# import lshell specifics
from lshell.checkconfig import CheckConfig
from lshell.utils import get_aliases, updateprompt, parse_ps1, getpromptbase
from lshell.variables import builtins_list
from lshell import builtincmd
from lshell import sec

TOPDIR = f"{os.path.dirname(os.path.realpath(__file__))}/../"
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"


class TestFunctions(unittest.TestCase):
    """Unit tests for lshell"""

    args = [f"--config={CONFIG}", "--quiet=1"]
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
        args = [f"--config={CONFIG}", "--strict=123"]
        userconf = CheckConfig(args).returnconf()
        return self.assertEqual(userconf["strict"], 123)

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
        expected = f"{getuser()}:foo$ "
        args = self.args + ["--prompt_short=1"]
        userconf = CheckConfig(args).returnconf()
        currentpath = f"{userconf['home_path']}/foo"
        prompt = updateprompt(currentpath, userconf)
        # sort lists to compare
        return self.assertEqual(prompt, expected)

    def test_24_prompt_short_2(self):
        """U24 | short_prompt = 2 should show full dir path"""
        expected = f"{getuser()}:{os.getcwd()}/foo$ "
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
        """U29 | Test that --env_path updates the PATH environment variable."""
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
    def test_30_invalid_new_path(self, mock_exit):
        """U30 | Test that an invalid new PATH triggers an error and sys.exit."""
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
    def test_31_new_path_starts_with_colon(self, mock_exit):
        """U31 | Test that a new PATH starting with a colon triggers an error."""
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

    def test_32_lps1_user_host_time(self):
        r"""U32 | LPS1 using \u@\h - \t> format"""
        os.environ["LPS1"] = r"\u@\h - \t> "
        expected = f"{getuser()}@{os.uname()[1].split('.')[0]} - {strftime('%H:%M:%S', gmtime())}> "
        prompt = parse_ps1(os.getenv("LPS1"))
        self.assertEqual(prompt, expected)
        del os.environ["LPS1"]

    def test_33_lps1_with_cwd(self):
        r"""U33 | LPS1 should replace cwd with \w format"""
        os.environ["LPS1"] = r"\u:\w$ "
        expected = f"{getuser()}:{os.getcwd().replace(os.path.expanduser('~'), '~')}$ "
        prompt = parse_ps1(os.getenv("LPS1"))
        self.assertEqual(prompt, expected)
        del os.environ["LPS1"]

    def test_34_prompt_default_user_host(self):
        """U34 | Default config-based prompt should replace %u and %h"""
        userconf = CheckConfig(self.args).returnconf()
        userconf["prompt"] = "%u@%h"
        expected = f"{getuser()}@{os.uname()[1].split('.')[0]}"
        prompt = getpromptbase(userconf)
        self.assertEqual(prompt, expected)

    def test_35_updateprompt_lps1_defined(self):
        """U35 | LPS1 environment variable should override config-based prompt"""
        os.environ["LPS1"] = r"\u@\H \W$ "
        expected = f"{getuser()}@{os.uname()[1]} {os.path.basename(os.getcwd())}$ "
        userconf = CheckConfig(self.args).returnconf()
        prompt = updateprompt(os.getcwd(), userconf)
        self.assertEqual(prompt, expected)
        del os.environ["LPS1"]

    def test_36_updateprompt_home_path(self):
        """U36 | Prompt path should use '~' for home directory"""
        userconf = CheckConfig(self.args).returnconf()
        currentpath = userconf["home_path"]
        expected = f"{getuser()}:~$ "
        prompt = updateprompt(currentpath, userconf)
        self.assertEqual(prompt, expected)

    def test_37_updateprompt_short_prompt_level_1(self):
        """U37 | short_prompt = 1 should show only last directory in path"""
        userconf = CheckConfig(self.args).returnconf()
        userconf["prompt_short"] = 1
        currentpath = f"{userconf['home_path']}/foo/bar"
        expected = f"{getuser()}:bar$ "
        prompt = updateprompt(currentpath, userconf)
        self.assertEqual(prompt, expected)

    def test_38_updateprompt_short_prompt_level_2(self):
        """U38 | short_prompt = 2 should show full directory path"""
        userconf = CheckConfig(self.args).returnconf()
        userconf["prompt_short"] = 2
        currentpath = f"{userconf['home_path']}/foo/bar"
        expected = f"{getuser()}:{currentpath}$ "
        prompt = updateprompt(currentpath, userconf)
        self.assertEqual(prompt, expected)

    def test_39_updateprompt_path_inside_home(self):
        """U39 | Path inside home directory should start with '~'"""
        userconf = CheckConfig(self.args).returnconf()
        currentpath = f"{userconf['home_path']}/projects"
        expected = f"{getuser()}:~{currentpath[len(userconf['home_path']):]}$ "
        prompt = updateprompt(currentpath, userconf)
        self.assertEqual(prompt, expected)

    def test_40_updateprompt_absolute_path_outside_home(self):
        """U40 | Absolute path outside home should display fully in prompt"""
        userconf = CheckConfig(self.args).returnconf()
        currentpath = "/etc"
        expected = f"{getuser()}:{currentpath}$ "
        prompt = updateprompt(currentpath, userconf)
        self.assertEqual(prompt, expected)
