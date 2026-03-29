""" Unit tests for lshell """

import io
import os
import stat
import sys
import tempfile
import unittest
from getpass import getuser
from time import strftime, gmtime
from unittest.mock import patch

# import lshell specifics
from lshell.config.runtime import CheckConfig
from lshell.utils import get_aliases, updateprompt, parse_ps1, getpromptbase
from lshell import builtincmd
from lshell import sec
from lshell.shellcmd import ShellCmd

TOPDIR = f"{os.path.dirname(os.path.realpath(__file__))}/../"
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"


class TestFunctions(unittest.TestCase):
    """Unit tests for lshell"""

    args = [f"--config={CONFIG}", "--quiet=1"]
    userconf = CheckConfig(args).returnconf()

    def test_checksecure_doublepipe(self):
        """U03 | double pipes should be allowed, even if pipe is forbidden"""
        args = self.args + ["--forbidden=['|']"]
        userconf = CheckConfig(args).returnconf()
        input_command = "ls || ls"
        return self.assertEqual(sec.check_secure(input_command, userconf)[0], 0)

    def test_checksecure_forbiddenpipe(self):
        """U04 | forbid pipe, should return 1"""
        args = self.args + ["--forbidden=['|']"]
        userconf = CheckConfig(args).returnconf()
        input_command = "ls | ls"
        return self.assertEqual(sec.check_secure(input_command, userconf)[0], 1)

    def test_checksecure_forbiddenchar(self):
        """U05 | forbid character, should return 1"""
        args = self.args + ["--forbidden=['l']"]
        userconf = CheckConfig(args).returnconf()
        input_command = "ls"
        return self.assertEqual(sec.check_secure(input_command, userconf)[0], 1)

    def test_checksecure_sudo_command(self):
        """U06 | quoted text should not be forbidden"""
        input_command = "sudo ls"
        return self.assertEqual(sec.check_secure(input_command, self.userconf)[0], 1)

    def test_checksecure_notallowed_command(self):
        """U07 | forbidden command, should return 1"""
        args = self.args + ["--allowed=['ls']"]
        userconf = CheckConfig(args).returnconf()
        input_command = "ll"
        return self.assertEqual(sec.check_secure(input_command, userconf)[0], 1)

    def test_checkpath_notallowed_path(self):
        """U08 | forbidden command, should return 1"""
        args = self.args + ["--path=['/home', '/var']"]
        userconf = CheckConfig(args).returnconf()
        input_command = "cd /tmp"
        return self.assertEqual(sec.check_path(input_command, userconf)[0], 1)

    def test_checkpath_notallowed_path_completion(self):
        """U09 | forbidden command, should return 1"""
        args = self.args + ["--path=['/home', '/var']"]
        userconf = CheckConfig(args).returnconf()
        input_command = "cd /tmp/"
        return self.assertEqual(
            sec.check_path(input_command, userconf, completion=1)[0], 1
        )

    def test_checkpath_dollarparenthesis(self):
        """U10 | when $() is allowed, return 0 if path allowed"""
        args = self.args + ["--forbidden=[';', '&', '|','`','>','<', '${']"]
        userconf = CheckConfig(args).returnconf()
        input_command = "echo $(echo aze)"
        return self.assertEqual(sec.check_path(input_command, userconf)[0], 0)

    def test_checkconfig_configoverwrite(self):
        """U12 | forbid ';', then check_secure should return 1"""
        args = [f"--config={CONFIG}", "--strict=123"]
        userconf = CheckConfig(args).returnconf()
        return self.assertEqual(userconf["strict"], 123)

    def test_merge_plus_minus_supported_for_all_list_merge_keys(self):
        """U12b | +/- merge semantics are applied for all merge-capable list keys."""
        args = self.args + [
            "--allowed=['basecmd'] + ['pluscmd'] - ['basecmd']",
            "--allowed_shell_escape=['ase_base'] + ['ase_plus'] - ['ase_base']",
            "--allowed_file_extensions=['.log'] + ['.txt'] - ['.log']",
            "--forbidden=[';'] + ['#'] - [';']",
            "--overssh=['scp', 'rsync'] + ['ls'] - ['scp']",
            "--path=['/'] - ['/var','/etc'] + ['/var/log']",
        ]
        userconf = CheckConfig(args).returnconf()

        self.assertIn("pluscmd", userconf["allowed"])
        self.assertNotIn("basecmd", userconf["allowed"])

        self.assertEqual(set(userconf["allowed_shell_escape"]), {"ase_plus"})
        self.assertEqual(set(userconf["allowed_file_extensions"]), {".txt"})

        self.assertIn("#", userconf["forbidden"])
        self.assertNotIn(";", userconf["forbidden"])

        self.assertIn("rsync", userconf["overssh"])
        self.assertIn("ls", userconf["overssh"])
        self.assertNotIn("scp", userconf["overssh"])

        self.assertTrue(userconf["path"][0].startswith("/|"))
        self.assertIn(f"{os.path.realpath('/var/log')}/|", userconf["path"][0])
        self.assertIn(f"{os.path.realpath('/var')}/|", userconf["path"][1])
        self.assertIn(f"{os.path.realpath('/etc')}/|", userconf["path"][1])

    def test_multiple_aliases_with_separator(self):
        """U13 | multiple aliases using &&, || and ; separators"""
        # enable &, | and ; characters
        aliases = {"foo": "foo -l", "bar": "open"}
        input_command = "foo; fooo  ;bar&&foo  &&   foo | bar||bar   ||     foo"
        return self.assertEqual(
            get_aliases(input_command, aliases),
            " foo -l; fooo  ; open&& foo -l  " "&& foo -l | open|| open   || foo -l",
        )

    def test_sudo_all_commands_expansion(self):
        """U14 | sudo_commands set to 'all' is equal to allowed variable"""
        args = self.args + ["--sudo_commands=all"]
        userconf = CheckConfig(args).returnconf()
        # exclude shell-internal builtins and sudo(8), but keep `ls`
        exclude = [cmd for cmd in builtincmd.builtins_list if cmd != "ls"] + ["sudo"]
        allowed = list(dict.fromkeys(x for x in userconf["allowed"] if x not in exclude))
        # sort lists to compare
        userconf["sudo_commands"].sort()
        allowed.sort()
        return self.assertEqual(allowed, userconf["sudo_commands"])

    def test_allowed_all_unquoted_expands(self):
        """U14b | allowed=all (unquoted) expands to executable allow-list."""
        args = self.args + ["--allowed=all"]
        userconf = CheckConfig(args).returnconf()
        self.assertIsInstance(userconf["allowed"], list)
        self.assertIn("ls", userconf["allowed"])

    def test_allowed_all_quoted_expands(self):
        """U14c | allowed='all' (quoted) expands to executable allow-list."""
        args = self.args + ["--allowed='all'"]
        userconf = CheckConfig(args).returnconf()
        self.assertIsInstance(userconf["allowed"], list)
        self.assertIn("ls", userconf["allowed"])

    def test_sudo_all_quoted_expansion(self):
        """U14d | sudo_commands='all' (quoted) expands against effective allowed list."""
        args = self.args + ["--sudo_commands='all'"]
        userconf = CheckConfig(args).returnconf()
        self.assertIn("echo", userconf["sudo_commands"])
        self.assertIn("ll", userconf["sudo_commands"])
        self.assertIn("ls", userconf["sudo_commands"])
        self.assertEqual(
            userconf["sudo_commands"].count("ls"),
            1,
            msg="sudo_commands all-expansion must not duplicate ls",
        )

    def test_allowed_ld_preload_builtin(self):
        """U16 | builtin commands should NOT be prepended with LD_PRELOAD"""
        args = self.args + ["--allowed=['echo','export']"]
        userconf = CheckConfig(args).returnconf()
        # verify that export is not automatically added to the aliases (i.e.
        # prepended with LD_PRELOAD)
        return self.assertNotIn("export", userconf["aliases"])

    def test_allowed_exec_cmd(self):
        """U17 | allowed_shell_escape should NOT be prepended with LD_PRELOAD
        The command should not be added to the aliases variable
        """
        args = self.args + ["--allowed_shell_escape=['echo']"]
        userconf = CheckConfig(args).returnconf()
        # sort lists to compare
        return self.assertNotIn("echo", userconf["aliases"])

    def test_forbidden_environment(self):
        """U18 | unsafe environment are forbidden"""
        input_command = "export LD_PRELOAD=/lib64/ld-2.21.so"
        args = input_command
        retcode = builtincmd.cmd_export(args)[0]
        return self.assertEqual(retcode, 1)

    def test_allowed_environment(self):
        """U19 | other environment are accepted"""
        input_command = "export MY_PROJECT_VERSION=43"
        args = input_command
        retcode = builtincmd.cmd_export(args)[0]
        return self.assertEqual(retcode, 0)

    def test_prompt_short_0(self):
        """U22 | short_prompt = 0 should show dir compared to home dir"""
        expected = f"{getuser()}:~/foo$ "
        args = self.args + ["--prompt_short=0"]
        userconf = CheckConfig(args).returnconf()
        currentpath = f"{userconf['home_path']}/foo"
        prompt = updateprompt(currentpath, userconf)
        # sort lists to compare
        return self.assertEqual(prompt, expected)

    def test_prompt_short_1(self):
        """U23 | short_prompt = 1 should show only current dir"""
        expected = f"{getuser()}:foo$ "
        args = self.args + ["--prompt_short=1"]
        userconf = CheckConfig(args).returnconf()
        currentpath = f"{userconf['home_path']}/foo"
        prompt = updateprompt(currentpath, userconf)
        # sort lists to compare
        return self.assertEqual(prompt, expected)

    def test_prompt_short_2(self):
        """U24 | short_prompt = 2 should show full dir path"""
        expected = f"{getuser()}:{os.getcwd()}/foo$ "
        args = self.args + ["--prompt_short=2"]
        userconf = CheckConfig(args).returnconf()
        currentpath = f"{userconf['home_path']}/foo"
        prompt = updateprompt(currentpath, userconf)
        # sort lists to compare
        return self.assertEqual(prompt, expected)

    def test_disable_ld_preload(self):
        """U25 | empty path_noexec should disable LD_PRELOAD"""
        args = self.args + ["--allowed=['echo','export']", "--path_noexec=''"]
        userconf = CheckConfig(args).returnconf()
        # verify that no alias was created containing LD_PRELOAD
        return self.assertNotIn("echo", userconf["aliases"])

    def test_checksecure_quoted_command(self):
        """U26 | quoted command should be parsed"""
        input_command = 'echo 1 && "bash"'
        return self.assertEqual(sec.check_secure(input_command, self.userconf)[0], 1)

    def test_checksecure_quoted_command_case_27(self):
        """U27 | quoted command should be parsed"""
        input_command = '"bash" && echo 1'
        return self.assertEqual(sec.check_secure(input_command, self.userconf)[0], 1)

    def test_checksecure_quoted_command_case_28(self):
        """U28 | quoted command should be parsed"""
        input_command = "echo'/1.sh'"
        return self.assertEqual(sec.check_secure(input_command, self.userconf)[0], 1)

    def test_env_path_updates_path_variable(self):
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
    def test_invalid_new_path(self, mock_exit):
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
    def test_new_path_starts_with_colon(self, mock_exit):
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

    def test_lps1_user_host_time(self):
        r"""U32 | LPS1 using \u@\h - \t> format"""
        os.environ["LPS1"] = r"\u@\h - \t> "
        expected = f"{getuser()}@{os.uname()[1].split('.')[0]} - {strftime('%H:%M:%S', gmtime())}> "
        prompt = parse_ps1(os.getenv("LPS1"))
        self.assertEqual(prompt, expected)
        del os.environ["LPS1"]

    def test_lps1_with_cwd(self):
        r"""U33 | LPS1 should replace cwd with \w format"""
        os.environ["LPS1"] = r"\u:\w$ "
        expected = f"{getuser()}:{os.getcwd().replace(os.path.expanduser('~'), '~')}$ "
        prompt = parse_ps1(os.getenv("LPS1"))
        self.assertEqual(prompt, expected)
        del os.environ["LPS1"]

    def test_prompt_default_user_host(self):
        """U34 | Default config-based prompt should replace %u and %h"""
        userconf = CheckConfig(self.args).returnconf()
        userconf["prompt"] = "%u@%h"
        expected = f"{getuser()}@{os.uname()[1].split('.')[0]}"
        prompt = getpromptbase(userconf)
        self.assertEqual(prompt, expected)

    def test_updateprompt_lps1_defined(self):
        """U35 | LPS1 environment variable should override config-based prompt"""
        os.environ["LPS1"] = r"\u@\H \W$ "
        expected = f"{getuser()}@{os.uname()[1]} {os.path.basename(os.getcwd())}$ "
        userconf = CheckConfig(self.args).returnconf()
        prompt = updateprompt(os.getcwd(), userconf)
        self.assertEqual(prompt, expected)
        del os.environ["LPS1"]

    def test_updateprompt_home_path(self):
        """U36 | Prompt path should use '~' for home directory"""
        userconf = CheckConfig(self.args).returnconf()
        currentpath = userconf["home_path"]
        expected = f"{getuser()}:~$ "
        prompt = updateprompt(currentpath, userconf)
        self.assertEqual(prompt, expected)

    def test_updateprompt_short_prompt_level_1(self):
        """U37 | short_prompt = 1 should show only last directory in path"""
        userconf = CheckConfig(self.args).returnconf()
        userconf["prompt_short"] = 1
        currentpath = f"{userconf['home_path']}/foo/bar"
        expected = f"{getuser()}:bar$ "
        prompt = updateprompt(currentpath, userconf)
        self.assertEqual(prompt, expected)

    def test_updateprompt_short_prompt_level_2(self):
        """U38 | short_prompt = 2 should show full directory path"""
        userconf = CheckConfig(self.args).returnconf()
        userconf["prompt_short"] = 2
        currentpath = f"{userconf['home_path']}/foo/bar"
        expected = f"{getuser()}:{currentpath}$ "
        prompt = updateprompt(currentpath, userconf)
        self.assertEqual(prompt, expected)

    def test_updateprompt_path_inside_home(self):
        """U39 | Path inside home directory should start with '~'"""
        userconf = CheckConfig(self.args).returnconf()
        currentpath = f"{userconf['home_path']}/projects"
        expected = f"{getuser()}:~{currentpath[len(userconf['home_path']):]}$ "
        prompt = updateprompt(currentpath, userconf)
        self.assertEqual(prompt, expected)

    def test_updateprompt_absolute_path_outside_home(self):
        """U40 | Absolute path outside home should display fully in prompt"""
        userconf = CheckConfig(self.args).returnconf()
        currentpath = "/etc"
        expected = f"{getuser()}:{currentpath}$ "
        prompt = updateprompt(currentpath, userconf)
        self.assertEqual(prompt, expected)

    @patch("lshell.config.runtime.os.umask")
    def test_umask_sets_process_mask(self, mock_umask):
        """U41 | --umask should be parsed as octal and applied to process mask"""
        args = self.args + ["--umask=0002"]
        userconf = CheckConfig(args).returnconf()
        self.assertEqual(userconf["umask"], "0002")
        mock_umask.assert_called_once_with(0o002)

    def test_invalid_umask_value_raises(self):
        """U42 | invalid umask value should exit with error"""
        args = self.args + ["--umask=0088"]
        with self.assertRaises(SystemExit) as exc:
            CheckConfig(args).returnconf()
        self.assertEqual(exc.exception.code, 1)

    def test_umask_masks_new_history_file_permissions(self):
        """U42b | configured umask should affect newly created lshell artifacts."""
        original_umask = os.umask(0)
        os.umask(original_umask)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                history_path = os.path.join(tmpdir, "lshell_history")
                args = self.args + [
                    "--umask=0077",
                    f"--history_file='{history_path}'",
                ]
                userconf = CheckConfig(args).returnconf()

                with open(userconf["history_file"], "w", encoding="utf-8") as handle:
                    handle.write("echo test\n")

                history_mode = stat.S_IMODE(os.stat(userconf["history_file"]).st_mode)
                self.assertEqual(history_mode, 0o600)
        finally:
            os.umask(original_umask)

    def test_default_ls_alias_enables_auto_color(self):
        """U43 | default config should alias ls to a platform color option."""
        userconf = CheckConfig(self.args).returnconf()
        expected = None
        if sys.platform.startswith("linux"):
            expected = "ls --color=auto"
        elif sys.platform == "darwin" or "bsd" in sys.platform:
            expected = "ls -G"
        self.assertEqual(userconf["aliases"].get("ls"), expected)

    def test_explicit_ls_alias_is_preserved(self):
        """U44 | explicit ls alias should not be overwritten."""
        args = self.args + ["--aliases={'ls':'ls -lh'}"]
        userconf = CheckConfig(args).returnconf()
        self.assertEqual(userconf["aliases"].get("ls"), "ls -lh")

    def test_auto_ls_alias_expands_during_local_execution(self):
        """U44b | local execution should dispatch through the generated ls alias."""
        saved_env = {}
        for key in ("SSH_CLIENT", "SSH_TTY", "SSH_ORIGINAL_COMMAND"):
            saved_env[key] = os.environ.get(key)
            os.environ.pop(key, None)
        try:
            userconf = CheckConfig(self.args).returnconf()
            expected = get_aliases("ls", userconf["aliases"])
            if not userconf.get("_auto_ls_alias") or expected is None:
                self.skipTest("platform does not synthesize an ls alias")

            with patch(
                "lshell.shellcmd.utils.cmd_parse_execute", return_value=0
            ) as mock_exec:
                shell = ShellCmd(
                    userconf,
                    args=[],
                    stdin=io.StringIO(),
                    stdout=io.StringIO(),
                    stderr=io.StringIO(),
                )
                shell.onecmd("ls")

            mock_exec.assert_called_once_with(expected, shell_context=shell)
        finally:
            for key, value in saved_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_policy_commands_enabled_by_default(self):
        """U45 | policy commands should be available by default."""
        userconf = CheckConfig(self.args).returnconf()
        self.assertIn("lshow", userconf["allowed"])

    def test_policy_commands_can_be_hidden(self):
        """U46 | policy commands can be hidden via --policy_commands=0."""
        args = self.args + ["--policy_commands=0"]
        userconf = CheckConfig(args).returnconf()
        self.assertNotIn("lshow", userconf["allowed"])

    def test_history_file_accepts_string_and_expands_home(self):
        """U48 | --history_file should parse as string and resolve under home path."""
        history_name = ".lshell_%u_history"
        args = self.args + [f"--history_file='{history_name}'"]
        userconf = CheckConfig(args).returnconf()
        expected_history = os.path.join(
            userconf["home_path"], history_name.replace("%u", userconf["username"])
        )
        self.assertEqual(userconf["history_file"], expected_history)

    def test_history_file_absolute_path_kept_absolute(self):
        """U49 | absolute --history_file path should not be prefixed by home path."""
        history_path = "/tmp/lshell_%u_history"
        args = self.args + [f"--history_file='{history_path}'"]
        userconf = CheckConfig(args).returnconf()
        self.assertEqual(
            userconf["history_file"], history_path.replace("%u", userconf["username"])
        )

    @patch("lshell.config.runtime.CheckConfig.noexec_library_usable", return_value=False)
    def test_incompatible_noexec_library_is_disabled(self, _mock_usable):
        """U50 | incompatible --path_noexec should be removed from runtime config."""
        with tempfile.NamedTemporaryFile() as fake_lib:
            args = self.args + [f"--path_noexec='{fake_lib.name}'"]
            userconf = CheckConfig(args).returnconf()
        self.assertNotIn("path_noexec", userconf)
