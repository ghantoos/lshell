"""Functional tests for lshell"""

import os
import unittest
import subprocess
from getpass import getuser
import tempfile
import shutil
import pexpect

# import lshell specifics
from lshell import utils

TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class TestFunctions(unittest.TestCase):
    """Functional tests for lshell"""

    user = getuser()

    def setUp(self):
        """spawn lshell with pexpect and return the child"""
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell --config {TOPDIR}/etc/lshell.conf --strict 1"
        )
        self.child.expect(f"{self.user}:~\\$")

    def tearDown(self):
        self.child.close()

    def test_01_welcome_message(self):
        """F01 | lshell welcome message"""
        expected = (
            "You are in a limited shell.\r\nType '?' or 'help' to get"
            " the list of allowed commands\r\n"
        )
        result = self.child.before.decode("utf8")
        self.assertEqual(expected, result)

    def test_02_builtin_ls_command(self):
        """F02 | built-in ls command"""
        p = subprocess.Popen(
            "ls ~", shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE
        )
        cout = p.stdout
        expected = cout.read(-1)
        self.child.sendline("ls")
        self.child.expect(f"{self.user}:~\\$")
        output = self.child.before.decode("utf8").split("ls\r", 1)[1]
        self.assertEqual(len(expected.strip().split()), len(output.strip().split()))

    def test_03_external_echo_command_num(self):
        """F03 | external echo number"""
        expected = "32"
        self.child.sendline("echo 32")
        self.child.expect(f"{self.user}:~\\$")
        result = self.child.before.decode("utf8").split()[2]
        self.assertEqual(expected, result)

    def test_04_external_echo_command_string(self):
        """F04 | external echo random string"""
        expected = "bla blabla  32 blibli! plop."
        self.child.sendline(f'echo "{expected}"')
        self.child.expect(f"{self.user}:~\\$")
        result = self.child.before.decode("utf8").split("\n", 1)[1].strip()
        self.assertEqual(expected, result)

    def test_05_external_echo_forbidden_syntax(self):
        """F05 | echo forbidden syntax $(bleh)"""
        expected = (
            '*** forbidden syntax -> "echo $(uptime)"\r\n*** You '
            "have 1 warning(s) left, before getting kicked out.\r\nThis "
            "incident has been reported.\r\n"
        )
        self.child.sendline("echo $(uptime)")
        self.child.expect(f"{self.user}:~\\$")
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_06_builtin_cd_change_dir(self):
        """F06 | built-in cd - change directory"""
        expected = ""
        home = os.path.expanduser("~")
        dirpath = None
        for path in os.listdir(home):
            dirpath = os.path.join(home, path)
            if os.path.isdir(dirpath):
                break
        if dirpath:
            self.child.sendline(f"cd {path}")
            self.child.expect(f"{self.user}:~/{path}\\$")
            self.child.sendline("cd ..")
            self.child.expect(f"{self.user}:~\\$")
            result = self.child.before.decode("utf8").split("\n", 1)[1]
            self.assertEqual(expected, result)

    def test_07_builtin_cd_tilda(self):
        """F07 | built-in cd - tilda bug"""
        expected = (
            '*** forbidden path -> "/etc/passwd"\r\n*** You have'
            " 1 warning(s) left, before getting kicked out.\r\nThis "
            "incident has been reported.\r\n"
        )
        self.child.sendline("ls ~/../../etc/passwd")
        self.child.expect(f"{self.user}:~\\$")
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_08_builtin_cd_quotes(self):
        """F08 | built-in - quotes in cd "/" """
        expected = (
            '*** forbidden path -> "/"\r\n*** You have'
            " 1 warning(s) left, before getting kicked out.\r\nThis "
            "incident has been reported.\r\n"
        )
        self.child.sendline('ls -ld "/"')
        self.child.expect(f"{self.user}:~\\$")
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_09_external_forbidden_path(self):
        """F09 | external command forbidden path - ls /root"""
        expected = (
            '*** forbidden path -> "/root/"\r\n*** You have'
            " 1 warning(s) left, before getting kicked out.\r\nThis "
            "incident has been reported.\r\n"
        )
        self.child.sendline("ls ~root")
        self.child.expect(f"{self.user}:~\\$")
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_10_builtin_cd_forbidden_path(self):
        """F10 | built-in command forbidden path - cd ~root"""
        expected = (
            '*** forbidden path -> "/root/"\r\n*** You have'
            " 1 warning(s) left, before getting kicked out.\r\nThis "
            "incident has been reported.\r\n"
        )
        self.child.sendline("cd ~root")
        self.child.expect(f"{self.user}:~\\$")
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_11_etc_passwd_1(self):
        """F11 | /etc/passwd: empty variable 'ls "$a"/etc/passwd'"""
        expected = (
            '*** forbidden path -> "/etc/passwd"\r\n*** You have'
            " 1 warning(s) left, before getting kicked out.\r\nThis "
            "incident has been reported.\r\n"
        )
        self.child.sendline('ls "$a"/etc/passwd')
        self.child.expect(f"{self.user}:~\\$")
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_12_etc_passwd_2(self):
        """F12 | /etc/passwd: empty variable 'ls -l .*./.*./etc/passwd'"""
        expected = (
            '*** forbidden path -> "/etc/passwd"\r\n*** You have'
            " 1 warning(s) left, before getting kicked out.\r\nThis "
            "incident has been reported.\r\n"
        )
        self.child.sendline("ls -l .*./.*./etc/passwd")
        self.child.expect(f"{self.user}:~\\$")
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_13_etc_passwd_3(self):
        """F13 | /etc/passwd: empty variable 'ls -l .?/.?/etc/passwd'"""
        expected = (
            '*** forbidden path -> "/etc/passwd"\r\n*** You have'
            " 1 warning(s) left, before getting kicked out.\r\nThis "
            "incident has been reported.\r\n"
        )
        self.child.sendline("ls -l .?/.?/etc/passwd")
        self.child.expect(f"{self.user}:~\\$")
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_14_path_completion_tilda(self):
        """F14 | path completion with ~/"""
        p = subprocess.Popen(
            "ls -F ~/", shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE
        )
        cout = p.stdout
        expected = cout.read().decode("utf8").strip().split()
        self.child.sendline("cd ~/\t\t")
        self.child.expect(f"{self.user}:~\\$")
        output = (
            self.child.before.decode("utf8").strip().split("\n", 1)[1].strip().split()
        )
        output = [
            item
            for item in output
            if not item.startswith("--More--") and not item.startswith("\x1b")
        ]
        self.assertEqual(len(expected), len(output))

    def test_15_cmd_completion_tab_tab(self):
        """F15 | command completion: tab to list commands"""
        expected = (
            "\x07\r\ncd       echo     help     ll       ls       "
            "\r\nclear    exit     history  lpath    lsudo"
        )
        self.child.sendline("\t\t")
        self.child.expect(f"{self.user}:~\\$")
        result = self.child.before.decode("utf8").strip()

        self.assertEqual(expected, result)

    def test_16_exitcode_with_separator_external_cmd(self):
        """F16 | external command exit codes with separator"""
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell "
            f"--config {TOPDIR}/etc/lshell.conf "
            '--forbidden "[]"'
        )
        self.child.expect(f"{self.user}:~\\$")

        expected = "2"
        self.child.sendline("ls nRVmmn8RGypVneYIp8HxyVAvaEaD55; echo $?")
        self.child.expect(f"{self.user}:~\\$")
        result = self.child.before.decode("utf8").split("\n")[2].strip()
        self.assertEqual(expected, result)

    def test_17_exitcode_without_separator_external_cmd(self):
        """F17 | external command exit codes without separator"""
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell "
            f"--config {TOPDIR}/etc/lshell.conf "
            '--forbidden "[]"'
        )
        self.child.expect(f"{self.user}:~\\$")

        expected = "2"
        self.child.sendline("ls nRVmmn8RGypVneYIp8HxyVAvaEaD55")
        self.child.expect(f"{self.user}:~\\$")
        self.child.sendline("echo $?")
        self.child.expect(f"{self.user}:~\\$")
        result = self.child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)

    def test_18_cd_exitcode_with_separator_internal_cmd(self):
        """F18 | built-in command exit codes with separator"""
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell "
            f"--config {TOPDIR}/etc/lshell.conf "
            '--forbidden "[]"'
        )
        self.child.expect(f"{self.user}:~\\$")

        expected = "2"
        self.child.sendline("cd nRVmmn8RGypVneYIp8HxyVAvaEaD55; echo $?")
        self.child.expect(f"{self.user}:~\\$")
        self.child.sendline("echo $?")
        self.child.expect(f"{self.user}:~\\$")
        result = self.child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)

    def test_19_cd_exitcode_without_separator_external_cmd(self):
        """F19 | built-in exit codes without separator"""
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell "
            f"--config {TOPDIR}/etc/lshell.conf "
            '--forbidden "[]"'
        )
        self.child.expect(f"{self.user}:~\\$")

        expected = "2"
        self.child.sendline("cd nRVmmn8RGypVneYIp8HxyVAvaEaD55")
        self.child.expect(f"{self.user}:~\\$")
        self.child.sendline("echo $?")
        self.child.expect(f"{self.user}:~\\$")
        result = self.child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)

    def test_20_cd_with_cmd_unknwon_dir(self):
        """F20 | test built-in cd with command when dir does not exist
        Should be returning error, not executing cmd
        """
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell "
            f"--config {TOPDIR}/etc/lshell.conf "
            '--forbidden "[]"'
        )
        self.child.expect(f"{self.user}:~\\$")

        expected = (
            "lshell: nRVmmn8RGypVneYIp8HxyVAvaEaD55: No such file or " "directory"
        )

        self.child.sendline("cd nRVmmn8RGypVneYIp8HxyVAvaEaD55; echo $?")
        self.child.expect(f"{self.user}:~\\$")
        result = self.child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)

    def test_21_allow_slash(self):
        """F21 | user should able to allow / access minus some directory
        (e.g. /var)
        """
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell "
            f"--config {TOPDIR}/etc/lshell.conf "
            "--path \"['/'] - ['/var']\""
        )
        self.child.expect(f"{self.user}:~\\$")

        expected = "*** forbidden path: /var/"
        self.child.sendline("cd /")
        self.child.expect(f"{self.user}:/\\$")
        self.child.sendline("cd var")
        self.child.expect(f"{self.user}:/\\$")
        result = self.child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)

    def test_22_expand_env_variables(self):
        """F22 | expanding of environment variables"""
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell "
            f"--config {TOPDIR}/etc/lshell.conf "
            "--allowed \"+ ['export']\""
        )
        self.child.expect(f"{self.user}:~\\$")

        expected = f"{os.path.expanduser('~')}/test"
        self.child.sendline("export A=test")
        self.child.expect(f"{self.user}:~\\$")
        self.child.sendline("echo $HOME/$A")
        self.child.expect(f"{self.user}:~\\$")
        result = self.child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)

    def test_23_expand_env_variables_cd(self):
        """F23 | expanding of environment variables when using cd"""
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell "
            f"--config {TOPDIR}/etc/lshell.conf "
            "--allowed \"+ ['export']\""
        )
        self.child.expect(f"{self.user}:~\\$")

        random = utils.random_string(32)

        expected = f"lshell: {os.path.expanduser('~')}/random_{random}: No such file or directory"
        self.child.sendline(f"export A=random_{random}")
        self.child.expect(f"{self.user}:~\\$")
        self.child.sendline("cd $HOME/$A")
        self.child.expect(f"{self.user}:~\\$")
        result = self.child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)

    def test_24_cd_and_command(self):
        """F24 | cd && command should not be interpreted by internal function"""
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell " f"--config {TOPDIR}/etc/lshell.conf"
        )
        self.child.expect(f"{self.user}:~\\$")

        expected = "OK"
        self.child.sendline('cd ~ && echo "OK"')
        self.child.expect(f"{self.user}:~\\$")
        result = self.child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)

    def test_25_keyboard_interrupt(self):
        """F25 | test cat(1) with KeyboardInterrupt, should not exit"""
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell "
            f"--config {TOPDIR}/etc/lshell.conf "
            "--allowed \"+ ['cat']\""
        )
        self.child.expect(f"{self.user}:~\\$")

        self.child.sendline("cat")
        self.child.sendline(" foo ")
        self.child.sendcontrol("c")
        self.child.expect(f"{self.user}:~\\$")
        try:
            result = self.child.before.decode("utf8").split("\n")[1].strip()
            # both behaviors are correct
            if result.startswith("foo"):
                expected = "foo"
            elif result.startswith("^C"):
                expected = "^C"
            else:
                expected = "unknown"
        except IndexError:
            # outputs u' ^C' on Debian
            expected = "^C"
            result = self.child.before.decode("utf8").strip()
        self.assertIn(expected, result)

    def test_26_cmd_completion_dot_slash(self):
        """F26 | command completion: tab to list ./foo1 ./foo2"""
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell "
            f"--config {TOPDIR}/etc/lshell.conf "
            "--allowed \"+ ['./foo1', './foo2']\""
        )
        self.child.expect(f"{self.user}:~\\$")

        expected = "./\x07foo\x07\r\nfoo1  foo2"
        self.child.sendline("./\t\t\t")
        self.child.expect(f"{self.user}:~\\$")
        result = self.child.before.decode("utf8").strip()

        self.assertEqual(expected, result)

    def test_27_checksecure_awk(self):
        """F27 | checksecure awk script with /bin/bash"""
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell "
            f"--config {TOPDIR}/etc/lshell.conf "
            "--allowed \"+ ['awk']\""
        )
        self.child.expect(f"{self.user}:~\\$")

        expected = "*** forbidden path: /usr/bin/bash"
        self.child.sendline("awk 'BEGIN {system(\"/bin/bash\")}'")
        self.child.expect(f"{self.user}:~\\$")
        result = self.child.before.decode("utf8").split("\n")[1].strip()

        self.assertEqual(expected, result)

    def test_28_catch_terminal_ctrl_j(self):
        """F28 | test ctrl-v ctrl-j then command, forbidden/security"""
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell " f"--config {TOPDIR}/etc/lshell.conf "
        )
        self.child.expect(f"{self.user}:~\\$")

        expected = "*** forbidden control char: echo\r"
        self.child.send("echo")
        self.child.sendcontrol("v")
        self.child.sendcontrol("j")
        self.child.sendline("bash")
        self.child.expect(f"{self.user}:~\\$")

        result = self.child.before.decode("utf8").split("\n")

        self.assertIn(expected, result)

    def test_29_catch_terminal_ctrl_k(self):
        """F29 | test ctrl-v ctrl-k then command, forbidden/security"""
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell " f"--config {TOPDIR}/etc/lshell.conf "
        )
        self.child.expect(f"{self.user}:~\\$")

        expected = "*** forbidden control char: echo\x0b() bash && echo\r"
        self.child.send("echo")
        self.child.sendcontrol("v")
        self.child.sendcontrol("k")
        self.child.sendline("() bash && echo")
        self.child.expect(f"{self.user}:~\\$")

        result = self.child.before.decode("utf8").split("\n")[1]

        self.assertIn(expected, result)

    def test_30_disable_exit(self):
        """F31 | test disabled exit command"""
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell "
            f"--config {TOPDIR}/etc/lshell.conf "
            "--disable_exit 1 "
        )
        self.child.expect(f"{self.user}:~\\$")

        expected = ""
        self.child.sendline("exit")
        self.child.expect(f"{self.user}:~\\$")

        result = self.child.before.decode("utf8").split("\n")[1]

        self.assertIn(expected, result)

    def test_31_security_echo_freedom_and_help(self):
        """F31 | test help, then echo FREEDOM! && help () sh && help"""
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell " f"--config {TOPDIR}/etc/lshell.conf "
        )
        self.child.expect(f"{self.user}:~\\$")

        # Step 1: Enter `help` command
        expected_help_output = (
            "cd  clear  echo  exit  help  history  ll  lpath  ls  lsudo"
        )
        self.child.sendline("help")
        self.child.expect(f"{self.user}:~\\$")
        help_output = self.child.before.decode("utf8").split("\n", 1)[1].strip()

        self.assertEqual(expected_help_output, help_output)

        # Step 2: Enter `echo FREEDOM! && help () sh && help`
        expected_output = (
            "FREEDOM!\r\ncd  clear  echo  exit  help  history  ll  lpath  ls  lsudo\r\n"
            "cd  clear  echo  exit  help  history  ll  lpath  ls  lsudo"
        )
        self.child.sendline("echo FREEDOM! && help () sh && help")
        self.child.expect(f"{self.user}:~\\$")

        result = self.child.before.decode("utf8").strip().split("\n", 1)[1].strip()

        # Verify the combined output
        self.assertEqual(expected_output, result)

    def test_32_security_echo_freedom_and_cd(self):
        """F32 | test echo FREEDOM! && cd () bash && cd ~/"""
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell " f"--config {TOPDIR}/etc/lshell.conf "
        )
        self.child.expect(f"{self.user}:~\\$")

        # Step 1: Enter `help` command
        expected_help_output = (
            "cd  clear  echo  exit  help  history  ll  lpath  ls  lsudo"
        )
        self.child.sendline("help")
        self.child.expect(f"{self.user}:~\\$")
        help_output = self.child.before.decode("utf8").split("\n", 1)[1].strip()

        self.assertEqual(expected_help_output, help_output)

        # Step 2: Enter `echo FREEDOM! && help () sh && help`
        expected_output = "FREEDOM!\r\nlshell: () bash: No such file or directory"
        self.child.sendline("echo FREEDOM! && cd () bash && cd ~/")
        self.child.expect(f"{self.user}:~\\$")

        result = self.child.before.decode("utf8").strip().split("\n", 1)[1].strip()

        # Verify the combined output
        self.assertEqual(expected_output, result)

    def test_33_ls_non_existing_directory_and_echo(self):
        """Test: ls non_existing_directory && echo nothing"""
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell --config {TOPDIR}/etc/lshell.conf"
        )
        self.child.expect(f"{self.user}:~\\$")

        self.child.sendline("ls non_existing_directory && echo nothing")
        self.child.expect(f"{self.user}:~\\$")

        output = self.child.before.decode("utf8").split("\n", 1)[1].strip()
        # Since ls fails, echo nothing shouldn't run
        self.assertNotIn("nothing", output)

    def test_34_ls_and_echo_ok(self):
        """Test: ls && echo OK"""
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell --config {TOPDIR}/etc/lshell.conf"
        )
        self.child.expect(f"{self.user}:~\\$")

        self.child.sendline("ls && echo OK")
        self.child.expect(f"{self.user}:~\\$")

        output = self.child.before.decode("utf8").split("\n", 1)[1].strip()
        # ls succeeds, echo OK should run
        self.assertIn("OK", output)

    def test_35_ls_non_existing_directory_or_echo_ok(self):
        """Test: ls non_existing_directory || echo OK"""
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell --config {TOPDIR}/etc/lshell.conf"
        )
        self.child.expect(f"{self.user}:~\\$")

        self.child.sendline("ls non_existing_directory || echo OK")
        self.child.expect(f"{self.user}:~\\$")

        output = self.child.before.decode("utf8").split("\n", 1)[1].strip()
        # ls fails, echo OK should run
        self.assertIn("OK", output)

    def test_36_ls_or_echo_nothing(self):
        """Test: ls || echo nothing"""
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell --config {TOPDIR}/etc/lshell.conf"
        )
        self.child.expect(f"{self.user}:~\\$")

        self.child.sendline("ls || echo nothing")
        self.child.expect(f"{self.user}:~\\$")

        output = self.child.before.decode("utf8").split("\n", 1)[1].strip()
        # ls succeeds, echo nothing should not run
        self.assertNotIn("nothing", output)

    def test_37_env_vars_file_not_found(self):
        """Test missing environment variable file"""
        missing_file_path = "/path/to/missing/file"

        # Inject the environment variable file path
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell --config {TOPDIR}/etc/lshell.conf "
            f"--env_vars_files \"['{missing_file_path}']\""
        )

        # Expect the prompt after shell startup
        self.child.expect(f"{self.user}:~\\$")

        # Simulate what happens when the environment variable file is missing
        expected = (
            f"ERROR: Unable to read environment file: {missing_file_path}\r\n"
            "You are in a limited shell.\r\n"
            "Type '?' or 'help' to get the list of allowed commands\r\n"
        )

        # Check the error message in the output
        self.assertIn(expected, self.child.before.decode("utf8"))

    def test_38_load_env_vars_from_file(self):
        """Test loading environment variables from file"""

        # Create a temporary file to store environment variables
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, dir="/tmp"
        ) as temp_env_file:
            temp_env_file.write("export bar=helloworld\n")
            temp_env_file.flush()  # Ensure data is written to disk
            temp_env_file_path = temp_env_file.name

        # Set the temp env file path in the config
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell --config {TOPDIR}/etc/lshell.conf "
            f"--env_vars_files \"['{temp_env_file_path}']\""
        )
        self.child.expect(f"{self.user}:~\\$")

        # Test if the environment variable was loaded
        self.child.sendline("echo $bar")
        self.child.expect(f"{self.user}:~\\$")

        result = self.child.before.decode("utf8").strip().split("\n", 1)[1].strip()
        self.assertEqual(result, "helloworld")

        # Cleanup the temporary file
        os.remove(temp_env_file_path)

    def test_39_script_execution_with_template(self):
        """Test executing script after modifying shebang and clean up afterward"""

        template_path = f"{TOPDIR}/test/template.lsh"
        test_script_path = f"{TOPDIR}/test/test.lsh"
        wrapper_path = f"{TOPDIR}/bin/lshell_wrapper"

        # Step 1: Create the wrapper script
        with open(wrapper_path, "w") as wrapper:
            wrapper.write(
                f"""#!/bin/bash
exec {TOPDIR}/bin/lshell --config {TOPDIR}/etc/lshell.conf "$@"
"""
            )

        # Make the wrapper executable
        os.chmod(wrapper_path, 0o755)

        # Step 2: Copy template.lsh to test.lsh and replace the shebang
        shutil.copy(template_path, test_script_path)

        # Replace the placeholder in the shebang
        with open(test_script_path, "r+") as f:
            content = f.read()
            content = content.replace("#!SHEBANG", f"#!{wrapper_path}")
            f.seek(0)
            f.write(content)
            f.truncate()

        # Spawn a child process to run the test.lsh script using pexpect
        self.child = pexpect.spawn(f"{test_script_path}")

        # Expected output
        expected_output = """test\r
*** forbidden command: dig\r
*** forbidden path: /tmp/\r
FREEDOM\r
cd  clear  echo  exit  help  history  ll  lpath  ls  lsudo\r
cd  clear  echo  exit  help  history  ll  lpath  ls  lsudo\r
*** forbidden path: /"""

        # Wait for the script to finish executing
        self.child.expect(pexpect.EOF)

        # Capture the output and compare with expected output
        result = self.child.before.decode("utf8").strip()
        self.assertEqual(result, expected_output)

        # Cleanup: remove the test script after the test
        if os.path.exists(test_script_path):
            os.remove(test_script_path)

    def test_40_script_execution_with_template_strict(self):
        """Test executing script after modifying shebang and clean up afterward"""

        template_path = f"{TOPDIR}/test/template.lsh"
        test_script_path = f"{TOPDIR}/test/test.lsh"
        wrapper_path = f"{TOPDIR}/bin/lshell_wrapper"

        # Step 1: Create the wrapper script
        with open(wrapper_path, "w") as wrapper:
            wrapper.write(
                f"""#!/bin/bash
exec {TOPDIR}/bin/lshell --config {TOPDIR}/etc/lshell.conf --strict 1 "$@"
"""
            )

        # Make the wrapper executable
        os.chmod(wrapper_path, 0o755)

        # Step 2: Copy template.lsh to test.lsh and replace the shebang
        shutil.copy(template_path, test_script_path)

        with open(test_script_path, "r+") as f:
            content = f.read()
            content = content.replace("#!SHEBANG", f"#!{wrapper_path}")
            f.seek(0)
            f.write(content)
            f.truncate()

        # Step 3: Spawn a child process to run the test.lsh script using pexpect
        self.child = pexpect.spawn(f"{test_script_path}")

        # Expected output
        expected_output = """test\r
*** forbidden command -> "dig"\r
*** You have 1 warning(s) left, before getting kicked out.\r
This incident has been reported.\r
*** forbidden path -> "/tmp/"\r
*** You have 0 warning(s) left, before getting kicked out.\r
This incident has been reported.\r
FREEDOM\r
cd  clear  echo  exit  help  history  ll  lpath  ls  lsudo\r
cd  clear  echo  exit  help  history  ll  lpath  ls  lsudo\r
*** forbidden path -> "/"\r
*** Kicked out"""

        # Wait for the script to finish executing
        self.child.expect(pexpect.EOF)

        # Capture the output and compare with expected output
        result = self.child.before.decode("utf8").strip()
        self.assertEqual(result, expected_output)

        # Step 5: Cleanup: remove the test script and wrapper after the test
        if os.path.exists(test_script_path):
            os.remove(test_script_path)
        if os.path.exists(wrapper_path):
            os.remove(wrapper_path)

    def test_41_multicmd_with_wrong_arg_should_fail(self):
        """F20 | Allowing 'echo asd': Test 'echo qwe' should fail"""
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell "
            f"--config {TOPDIR}/etc/lshell.conf "
            "--allowed \"['echo asd']\""
        )
        self.child.expect(f"{self.user}:~\\$")

        expected = "*** forbidden command: echo"

        self.child.sendline("echo qwe")
        self.child.expect(f"{self.user}:~\\$")
        result = self.child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)

    def test_42_multicmd_with_near_exact_arg_should_fail(self):
        """F41 | Allowing 'echo asd': Test 'echo asds' should fail"""
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell "
            f"--config {TOPDIR}/etc/lshell.conf "
            "--allowed \"['echo asd']\""
        )
        self.child.expect(f"{self.user}:~\\$")

        expected = "*** forbidden command: echo"

        self.child.sendline("echo asds")
        self.child.expect(f"{self.user}:~\\$")
        result = self.child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)

    def test_43_multicmd_without_arg_should_fail(self):
        """F42 | Allowing 'echo asd': Test 'echo' should fail"""
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell "
            f"--config {TOPDIR}/etc/lshell.conf "
            "--allowed \"['echo asd']\""
        )
        self.child.expect(f"{self.user}:~\\$")

        expected = "*** forbidden command: echo"

        self.child.sendline("echo")
        self.child.expect(f"{self.user}:~\\$")
        result = self.child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)

    def test_44_multicmd_asd_should_pass(self):
        """F43 | Allowing 'echo asd': Test 'echo asd' should pass"""

        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell "
            f"--config {TOPDIR}/etc/lshell.conf "
            "--allowed \"['echo asd']\""
        )
        self.child.expect(f"{self.user}:~\\$")

        expected = "asd"

        self.child.sendline("echo asd")
        self.child.expect(f"{self.user}:~\\$")
        result = self.child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
