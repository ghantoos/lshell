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

# pylint: disable=C0411
from test import test_utils

TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"
LSHELL = f"{TOPDIR}/bin/lshell"
USER = getuser()
PROMPT = f"{USER}:~\\$"


class TestFunctions(unittest.TestCase):
    """Functional tests for lshell"""

    def setUp(self):
        """spawn lshell with pexpect and return the child"""
        self.child = pexpect.spawn(f"{LSHELL} --config {CONFIG} --strict 1")
        self.child.expect(PROMPT)

    def tearDown(self):
        self.child.close()

    def do_exit(self, child):
        """Exit the shell"""
        child.sendline("exit")
        child.expect(pexpect.EOF)

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
        self.child.expect(PROMPT)
        output = self.child.before.decode("utf8").split("ls\r", 1)[1]
        self.assertEqual(len(expected.strip().split()), len(output.strip().split()))

    def test_03_external_echo_command_num(self):
        """F03 | external echo number"""
        expected = "32"
        self.child.sendline("echo 32")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split()[2]
        self.assertEqual(expected, result)

    def test_04_external_echo_command_string(self):
        """F04 | external echo random string"""
        expected = "bla blabla  32 blibli! plop."
        self.child.sendline(f'echo "{expected}"')
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1].strip()
        self.assertEqual(expected, result)

    def test_05_external_echo_forbidden_syntax(self):
        """F05 | echo forbidden syntax $(bleh)"""
        expected = (
            '*** forbidden character -> "$("\r\n*** You '
            "have 1 warning(s) left, before getting kicked out.\r\nThis "
            "incident has been reported.\r\n"
        )
        self.child.sendline("echo $(uptime)")
        self.child.expect(PROMPT)
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
            self.child.expect(f"{USER}:~/{path}\\$")
            self.child.sendline("cd ..")
            self.child.expect(PROMPT)
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
        self.child.expect(PROMPT)
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
        self.child.expect(PROMPT)
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
        self.child.expect(PROMPT)
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
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_11_etc_passwd_1(self):
        """F11 | /etc/passwd: empty variable 'ls "$a"/etc/passwd'"""
        if test_utils.is_alpine_linux():
            expected = "ls: $a/etc/passwd: No such file or directory\r\n"
        else:
            expected = (
                "ls: cannot access '$a/etc/passwd': No such file or directory\r\n"
            )
        self.child.sendline('ls "$a"/etc/passwd')
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_12_etc_passwd_2(self):
        """F12 | /etc/passwd: empty variable 'ls -l .*./.*./etc/passwd'"""
        if test_utils.is_alpine_linux():
            expected = "ls: .*./.*./etc/passwd: No such file or directory\r\n"
        else:
            expected = (
                "ls: cannot access '.*./.*./etc/passwd': No such file or directory\r\n"
            )
        self.child.sendline("ls -l .*./.*./etc/passwd")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_13a_etc_passwd_3(self):
        """F13(a) | /etc/passwd: empty variable 'ls -l .?/.?/etc/passwd'"""
        if test_utils.is_alpine_linux():
            expected = "ls: .?/.?/etc/passwd: No such file or directory\r\n"
        else:
            expected = (
                "ls: cannot access '.?/.?/etc/passwd': No such file or directory\r\n"
            )
        self.child.sendline("ls -l .?/.?/etc/passwd")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_13b_etc_passwd_4(self):
        """F13(b) | /etc/passwd: empty variable 'ls -l ../../etc/passwd'"""
        expected = (
            '*** forbidden path -> "/etc/passwd"\r\n*** You have'
            " 1 warning(s) left, before getting kicked out.\r\nThis "
            "incident has been reported.\r\n"
        )
        self.child.sendline("ls -l ../../etc/passwd")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_14_path_completion_tilda(self):
        """F14 | path completion with ~/"""
        p = subprocess.Popen(
            "ls -F ~/", shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE
        )
        # Create two random files in the home directory
        file1 = os.path.join("random_file_1.txt")
        file2 = os.path.join("random_file_2.txt")
        with open(file1, "w") as f:
            f.write("This is a random file 1.")
        with open(file2, "w") as f:
            f.write("This is a random file 2.")
        cout = p.stdout
        expected = cout.read().decode("utf8").strip().split()
        self.child.sendline("cd \t\t")
        self.child.expect(PROMPT)
        output = (
            self.child.before.decode("utf8").strip().split("\n", 1)[1].strip().split()
        )
        output = [
            item
            for item in output
            if not item.startswith("--More--") and not item.startswith("\x1b")
        ]
        self.assertEqual(len(expected), len(output))

        # cleanup
        os.remove(file1)
        os.remove(file2)

    def test_15_cmd_completion_tab_tab(self):
        """F15 | command completion: tab to list commands"""
        expected = (
            "\x07\r\ncd       echo     help     ll       ls       "
            "\r\nclear    exit     history  lpath    lsudo"
        )
        self.child.sendline("\t\t")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").strip()

        self.assertEqual(expected, result)

    def test_16a_exitcode_with_separator_external_cmd(self):
        """F16(a) | external command exit codes with separator"""
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG} " '--forbidden "[]"')
        child.expect(PROMPT)

        if test_utils.is_alpine_linux():
            expected_1 = "ls: nRVmmn8RGypVneYIp8HxyVAvaEaD55: No such file or directory"
        else:
            expected_1 = (
                "ls: cannot access 'nRVmmn8RGypVneYIp8HxyVAvaEaD55': "
                "No such file or directory"
            )
        expected_2 = "blabla"
        expected_3 = "0"
        child.sendline("ls nRVmmn8RGypVneYIp8HxyVAvaEaD55; echo blabla; echo $?")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")
        result_1 = result[1].strip()
        result_2 = result[2].strip()
        result_3 = result[3].strip()
        self.assertEqual(expected_1, result_1)
        self.assertEqual(expected_2, result_2)
        self.assertEqual(expected_3, result_3)
        self.do_exit(child)

    def test_16b_exitcode_with_separator_external_cmd(self):
        """F16(b) | external command exit codes with separator"""
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG} " '--forbidden "[]"')
        child.expect(PROMPT)

        if test_utils.is_alpine_linux():
            expected_1 = "ls: nRVmmn8RGypVneYIp8HxyVAvaEaD55: No such file or directory"
            expected_2 = "1"
        else:
            expected_1 = (
                "ls: cannot access 'nRVmmn8RGypVneYIp8HxyVAvaEaD55': "
                "No such file or directory"
            )
            expected_2 = "2"
        child.sendline("ls nRVmmn8RGypVneYIp8HxyVAvaEaD55; echo $?")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")
        result_1 = result[1].strip()
        result_2 = result[2].strip()
        self.assertEqual(expected_1, result_1)
        self.assertEqual(expected_2, result_2)
        self.do_exit(child)

    def test_17_exitcode_without_separator_external_cmd(self):
        """F17 | external command exit codes without separator"""
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG} " '--forbidden "[]"')
        child.expect(PROMPT)

        if test_utils.is_alpine_linux():
            expected = "1"
        else:
            expected = "2"
        child.sendline("ls nRVmmn8RGypVneYIp8HxyVAvaEaD55")
        child.expect(PROMPT)
        child.sendline("echo $?")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_18_cd_exitcode_with_separator_internal_cmd(self):
        """F18 | built-in command exit codes with separator"""
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG} " '--forbidden "[]"')
        child.expect(PROMPT)

        expected = "2"
        child.sendline("cd nRVmmn8RGypVneYIp8HxyVAvaEaD55; echo $?")
        child.expect(PROMPT)
        child.sendline("echo $?")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_19_cd_exitcode_without_separator_external_cmd(self):
        """F19 | built-in exit codes without separator"""
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG} " '--forbidden "[]"')
        child.expect(PROMPT)

        expected = "2"
        child.sendline("cd nRVmmn8RGypVneYIp8HxyVAvaEaD55")
        child.expect(PROMPT)
        child.sendline("echo $?")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_20_cd_with_cmd_unknwon_dir(self):
        """F20 | test built-in cd with command when dir does not exist
        Should be returning error, not executing cmd
        """
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG} " '--forbidden "[]"')
        child.expect(PROMPT)

        expected = (
            "lshell: nRVmmn8RGypVneYIp8HxyVAvaEaD55: No such file or " "directory"
        )

        child.sendline("cd nRVmmn8RGypVneYIp8HxyVAvaEaD55; echo $?")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_21_allow_slash(self):
        """F21 | user should able to allow / access minus some directory
        (e.g. /var)
        """
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--path \"['/'] - ['/var']\""
        )
        child.expect(PROMPT)

        expected = "*** forbidden path: /var/"
        child.sendline("cd /")
        child.expect(f"{USER}:/\\$")
        child.sendline("cd var")
        child.expect(f"{USER}:/\\$")
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_22_expand_env_variables(self):
        """F22 | expanding of environment variables"""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--allowed \"+ ['export']\""
        )
        child.expect(PROMPT)

        expected = f"{os.path.expanduser('~')}/test"
        child.sendline("export A=test")
        child.expect(PROMPT)
        child.sendline("echo $HOME/$A")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_23_expand_env_variables_cd(self):
        """F23 | expanding of environment variables when using cd"""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--allowed \"+ ['export']\""
        )
        child.expect(PROMPT)

        random = utils.random_string(32)

        expected = f"lshell: {os.path.expanduser('~')}/random_{random}: No such file or directory"
        child.sendline(f"export A=random_{random}")
        child.expect(PROMPT)
        child.sendline("cd $HOME/$A")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_24_cd_and_command(self):
        """F24 | cd && command should not be interpreted by internal function"""
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG}")
        child.expect(PROMPT)

        expected = "OK"
        child.sendline('cd ~ && echo "OK"')
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_25_keyboard_interrupt(self):
        """F25 | test cat(1) with KeyboardInterrupt, should not exit"""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--allowed \"+ ['cat']\""
        )
        child.expect(PROMPT)

        child.sendline("cat")
        child.sendline(" foo ")
        child.sendcontrol("c")
        child.expect(PROMPT)
        try:
            result = child.before.decode("utf8").split("\n")[1].strip()
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
            result = child.before.decode("utf8").strip()
        self.assertIn(expected, result)
        self.do_exit(child)

    def test_26_cmd_completion_dot_slash(self):
        """F26 | command completion: tab to list ./foo1 ./foo2"""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--allowed \"+ ['./foo1', './foo2']\""
        )
        child.expect(PROMPT)

        expected = "./\x07foo\x07\r\nfoo1  foo2"
        child.sendline("./\t\t\t")
        child.expect(PROMPT)
        result = child.before.decode("utf8").strip()

        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_27_checksecure_awk(self):
        """F27 | checksecure awk script with /bin/sh"""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--allowed \"+ ['awk']\""
        )
        child.expect(PROMPT)

        if test_utils.is_alpine_linux():
            command = "awk 'BEGIN {system(\"/bin/sh\")}'"
            expected = "*** forbidden path: /bin/busybox"
        else:
            command = "awk 'BEGIN {system(\"/usr/bin/bash\")}'"
            expected = "*** forbidden path: /usr/bin/bash"
        child.sendline(command)
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()

        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_28_catch_terminal_ctrl_j(self):
        """F28 | test ctrl-v ctrl-j then command, forbidden/security"""
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG} ")
        child.expect(PROMPT)

        expected = "*** forbidden control char: echo\r"
        child.send("echo")
        child.sendcontrol("v")
        child.sendcontrol("j")
        child.sendline("bash")
        child.expect(PROMPT)

        result = child.before.decode("utf8").split("\n")

        self.assertIn(expected, result)
        self.do_exit(child)

    def test_29_catch_terminal_ctrl_k(self):
        """F29 | test ctrl-v ctrl-k then command, forbidden/security"""
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG} ")
        child.expect(PROMPT)

        expected = "*** forbidden control char: echo\x0b() bash && echo\r"
        child.send("echo")
        child.sendcontrol("v")
        child.sendcontrol("k")
        child.sendline("() bash && echo")
        child.expect(PROMPT)

        result = child.before.decode("utf8").split("\n")[1]

        self.assertIn(expected, result)
        self.do_exit(child)

    def test_30_disable_exit(self):
        """F31 | test disabled exit command"""
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG} " "--disable_exit 1 ")
        child.expect(PROMPT)

        expected = ""
        child.sendline("exit")
        child.expect(PROMPT)

        result = child.before.decode("utf8").split("\n")[1]

        self.assertIn(expected, result)

    def test_31_security_echo_freedom_and_help(self):
        """F31 | test help, then echo FREEDOM! && help () sh && help"""
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG} ")
        child.expect(PROMPT)

        # Step 1: Enter `help` command
        expected_help_output = (
            "cd  clear  echo  exit  help  history  ll  lpath  ls  lsudo"
        )
        child.sendline("help")
        child.expect(PROMPT)
        help_output = child.before.decode("utf8").split("\n", 1)[1].strip()

        self.assertEqual(expected_help_output, help_output)

        # Step 2: Enter `echo FREEDOM! && help () sh && help`
        expected_output = (
            "FREEDOM!\r\ncd  clear  echo  exit  help  history  ll  lpath  ls  lsudo\r\n"
            "cd  clear  echo  exit  help  history  ll  lpath  ls  lsudo"
        )
        child.sendline("echo FREEDOM! && help () sh && help")
        child.expect(PROMPT)

        result = child.before.decode("utf8").strip().split("\n", 1)[1].strip()

        # Verify the combined output
        self.assertEqual(expected_output, result)
        self.do_exit(child)

    def test_32_security_echo_freedom_and_cd(self):
        """F32 | test echo FREEDOM! && cd () bash && cd ~/"""
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG} ")
        child.expect(PROMPT)

        # Step 1: Enter `help` command
        expected_help_output = (
            "cd  clear  echo  exit  help  history  ll  lpath  ls  lsudo"
        )
        child.sendline("help")
        child.expect(PROMPT)
        help_output = child.before.decode("utf8").split("\n", 1)[1].strip()

        self.assertEqual(expected_help_output, help_output)

        # Step 2: Enter `echo FREEDOM! && help () sh && help`
        expected_output = "FREEDOM!\r\nlshell: () bash: No such file or directory"
        child.sendline("echo FREEDOM! && cd () bash && cd ~/")
        child.expect(PROMPT)

        result = child.before.decode("utf8").strip().split("\n", 1)[1].strip()

        # Verify the combined output
        self.assertEqual(expected_output, result)
        self.do_exit(child)

    def test_33_ls_non_existing_directory_and_echo(self):
        """Test: ls non_existing_directory && echo nothing"""
        child = pexpect.spawn(f"{LSHELL} --config {CONFIG}")
        child.expect(PROMPT)

        child.sendline("ls non_existing_directory && echo nothing")
        child.expect(PROMPT)

        output = child.before.decode("utf8").split("\n", 1)[1].strip()
        # Since ls fails, echo nothing shouldn't run
        self.assertNotIn("nothing", output)
        self.do_exit(child)

    def test_34_ls_and_echo_ok(self):
        """Test: ls && echo OK"""
        child = pexpect.spawn(f"{LSHELL} --config {CONFIG}")
        child.expect(PROMPT)

        child.sendline("ls && echo OK")
        child.expect(PROMPT)

        output = child.before.decode("utf8").split("\n", 1)[1].strip()
        # ls succeeds, echo OK should run
        self.assertIn("OK", output)
        self.do_exit(child)

    def test_35_ls_non_existing_directory_or_echo_ok(self):
        """Test: ls non_existing_directory || echo OK"""
        child = pexpect.spawn(f"{LSHELL} --config {CONFIG}")
        child.expect(PROMPT)

        child.sendline("ls non_existing_directory || echo OK")
        child.expect(PROMPT)

        output = child.before.decode("utf8").split("\n", 1)[1].strip()
        # ls fails, echo OK should run
        self.assertIn("OK", output)
        self.do_exit(child)

    def test_36_ls_or_echo_nothing(self):
        """Test: ls || echo nothing"""
        child = pexpect.spawn(f"{LSHELL} --config {CONFIG}")
        child.expect(PROMPT)

        child.sendline("ls || echo nothing")
        child.expect(PROMPT)

        output = child.before.decode("utf8").split("\n", 1)[1].strip()
        # ls succeeds, echo nothing should not run
        self.assertNotIn("nothing", output)
        self.do_exit(child)

    def test_37_env_vars_file_not_found(self):
        """Test missing environment variable file"""
        missing_file_path = "/path/to/missing/file"

        # Inject the environment variable file path
        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} "
            f"--env_vars_files \"['{missing_file_path}']\""
        )

        # Expect the prompt after shell startup
        child.expect(PROMPT)

        # Simulate what happens when the environment variable file is missing
        expected = (
            f"ERROR: Unable to read environment file: {missing_file_path}\r\n"
            "You are in a limited shell.\r\n"
            "Type '?' or 'help' to get the list of allowed commands\r\n"
        )

        # Check the error message in the output
        self.assertIn(expected, child.before.decode("utf8"))
        self.do_exit(child)

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
        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} "
            f"--env_vars_files \"['{temp_env_file_path}']\""
        )
        child.expect(PROMPT)

        # Test if the environment variable was loaded
        child.sendline("echo $bar")
        child.expect(PROMPT)

        result = child.before.decode("utf8").strip().split("\n", 1)[1].strip()
        self.assertEqual(result, "helloworld")

        # Cleanup the temporary file
        os.remove(temp_env_file_path)
        self.do_exit(child)

    def test_39_script_execution_with_template(self):
        """Test executing script after modifying shebang and clean up afterward"""

        template_path = f"{TOPDIR}/test/template.lsh"
        test_script_path = f"/tmp/test.lsh"

        # Step 1: Create the wrapper script
        with tempfile.NamedTemporaryFile(mode="w", delete=False, dir="/tmp") as wrapper:
            wrapper.write(
                f"""#!/bin/sh
exec {LSHELL} --config {CONFIG} "$@"
"""
            )
            wrapper.flush()  # Ensure data is written to disk
            wrapper_path = wrapper.name

        # Step 2: Copy template.lsh to test.lsh and replace the shebang
        shutil.copy(template_path, test_script_path)

        # Make the wrapper executable
        os.chmod(wrapper_path, 0o755)
        os.chmod(test_script_path, 0o755)

        # Replace the placeholder in the shebang
        with open(test_script_path, "r+") as f:
            content = f.read()
            content = content.replace("#!SHEBANG", f"#!{wrapper_path}")
            f.seek(0)
            f.write(content)
            f.truncate()

        # Spawn a child process to run the test.lsh script using pexpect
        child = pexpect.spawn(test_script_path)

        # Expected output
        expected_output = """test\r
*** forbidden command: dig\r
*** forbidden path: /tmp/\r
FREEDOM\r
cd  clear  echo  exit  help  history  ll  lpath  ls  lsudo\r
cd  clear  echo  exit  help  history  ll  lpath  ls  lsudo\r
*** forbidden path: /"""

        # Wait for the script to finish executing
        child.expect(pexpect.EOF)

        # Capture the output and compare with expected output
        result = child.before.decode("utf8").strip()
        self.assertEqual(result, expected_output)

        # Cleanup: remove the test script after the test
        if os.path.exists(test_script_path):
            os.remove(test_script_path)
        self.do_exit(child)

    def test_40_script_execution_with_template_strict(self):
        """Test executing script after modifying shebang and clean up afterward"""

        template_path = f"{TOPDIR}/test/template.lsh"
        test_script_path = f"/tmp/test.lsh"

        # Step 1: Create the wrapper script
        with tempfile.NamedTemporaryFile(mode="w", delete=False, dir="/tmp") as wrapper:
            wrapper.write(
                f"""#!/bin/sh
exec {LSHELL} --config {CONFIG} --strict 1 "$@"
"""
            )
            wrapper.flush()  # Ensure data is written to disk
            wrapper_path = wrapper.name

        # Step 2: Copy template.lsh to test.lsh and replace the shebang
        shutil.copy(template_path, test_script_path)

        # Make the wrapper executable
        os.chmod(wrapper_path, 0o755)
        os.chmod(test_script_path, 0o755)

        with open(test_script_path, "r+") as f:
            content = f.read()
            content = content.replace("#!SHEBANG", f"#!{wrapper_path}")
            f.seek(0)
            f.write(content)
            f.truncate()

        # Step 3: Spawn a child process to run the test.lsh script using pexpect
        child = pexpect.spawn(test_script_path)

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
        child.expect(pexpect.EOF)

        # Capture the output and compare with expected output
        result = child.before.decode("utf8").strip()
        self.assertEqual(result, expected_output)

        # Step 5: Cleanup: remove the test script and wrapper after the test
        if os.path.exists(test_script_path):
            os.remove(test_script_path)
        if os.path.exists(wrapper_path):
            os.remove(wrapper_path)
        self.do_exit(child)

    def test_41_multicmd_with_wrong_arg_should_fail(self):
        """F20 | Allowing 'echo asd': Test 'echo qwe' should fail"""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--allowed \"['echo asd']\""
        )
        child.expect(PROMPT)

        expected = "*** forbidden command: echo"

        child.sendline("echo qwe")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_42_multicmd_with_near_exact_arg_should_fail(self):
        """F41 | Allowing 'echo asd': Test 'echo asds' should fail"""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--allowed \"['echo asd']\""
        )
        child.expect(PROMPT)

        expected = "*** forbidden command: echo"

        child.sendline("echo asds")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_43_multicmd_without_arg_should_fail(self):
        """F42 | Allowing 'echo asd': Test 'echo' should fail"""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--allowed \"['echo asd']\""
        )
        child.expect(PROMPT)

        expected = "*** forbidden command: echo"

        child.sendline("echo")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_44_multicmd_asd_should_pass(self):
        """F43 | Allowing 'echo asd': Test 'echo asd' should pass"""

        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--allowed \"['echo asd']\""
        )
        child.expect(PROMPT)

        expected = "asd"

        child.sendline("echo asd")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_45_overssh_allowed_command_exit_0(self):
        """F44 | Test 'ssh -c ls' command should exit 0"""
        # add SSH_CLIENT to environment
        if not os.environ.get("SSH_CLIENT"):
            os.environ["SSH_CLIENT"] = "random"

        self.child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " f"--overssh \"['ls']\" " f"-c 'ls'"
        )
        self.child.expect(pexpect.EOF)

        # Assert that the process exited
        self.assertIsNotNone(
            self.child.exitstatus,
            f"The lshell process did not exit as expected: {self.child.exitstatus}",
        )

        # Optionally, you can assert that the exit code is correct
        self.assertEqual(
            self.child.exitstatus,
            0,
            f"The process should exit with code 0, got {self.child.exitstatus}.",
        )

    def test_46_overssh_allowed_command_exit_1(self):
        """F44 | Test 'ssh -c ls' command should exit 1"""
        # add SSH_CLIENT to environment
        if not os.environ.get("SSH_CLIENT"):
            os.environ["SSH_CLIENT"] = "random"

        self.child = pexpect.spawn(
            f"{LSHELL} "
            f"--config {CONFIG} "
            f"--overssh \"['ls']\" "
            f"-c 'ls /random'"
        )
        self.child.expect(pexpect.EOF)

        # Assert that the process exited
        self.assertIsNotNone(
            self.child.exitstatus, "The lshell process did not exit as expected."
        )

        # Optionally, you can assert that the exit code is correct
        self.assertEqual(
            self.child.exitstatus,
            1,
            f"The process should exit with code 1, got {self.child.exitstatus}.",
        )

    def test_46_overssh_not_allowed_command_exit_1(self):
        """F44 | Test 'ssh -c lss' command should succeed"""
        # add SSH_CLIENT to environment
        if not os.environ.get("SSH_CLIENT"):
            os.environ["SSH_CLIENT"] = "random"

        self.child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " f"--overssh \"['ls']\" " f"-c 'lss'"
        )
        self.child.expect(pexpect.EOF)

        # Assert that the process exited
        self.assertIsNotNone(
            self.child.exitstatus, "The lshell process did not exit as expected."
        )

        # Optionally, you can assert that the exit code is correct
        self.assertEqual(
            self.child.exitstatus,
            1,
            f"The process should exit with code 1, got {self.child.exitstatus}.",
        )

    def test_47_backticks(self):
        """F47 | Forbidden backticks should be reported"""
        expected = (
            '*** forbidden character -> "`"\r\n'
            "*** You have 1 warning(s) left, before getting kicked out.\r\n"
            "This incident has been reported.\r\n"
        )
        self.child.sendline("echo `uptime`")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_48_replace_backticks_with_dollar_parentheses(self):
        """F48 | Forbidden syntax $(command) should be reported"""
        expected = (
            '*** forbidden character -> "$("\r\n'
            "*** You have 1 warning(s) left, before getting kicked out.\r\n"
            "This incident has been reported.\r\n"
        )
        self.child.sendline("echo $(uptime)")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_49_env_variable_with_dollar_braces(self):
        """F49 | Syntax ${command} should replace with the variable"""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--env_vars \"{'foo':'OK'}\""
        )
        child.expect(PROMPT)

        child.sendline("echo ${foo}")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n", 1)[1]
        expected = "OK\r\n"
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_50_warnings_then_kickout(self):
        """F50 | kicked out after warning counter"""
        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} --strict 1 --warning_counter 0"
        )
        child.sendline("lslsls")
        child.sendline("lslsls")
        child.expect(pexpect.EOF)

        # Assert that the process exited
        self.assertIsNotNone(
            child.exitstatus, "The lshell process did not exit as expected."
        )

        # Optionally, you can assert that the exit code is correct
        self.assertEqual(child.exitstatus, 1, "The process should exit with code 1.")
        self.do_exit(child)
