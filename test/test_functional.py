import unittest
import pexpect
import os
import subprocess
from getpass import getuser

# import lshell specifics
from lshell import utils

TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


class TestFunctions(unittest.TestCase):

    user = getuser()

    def setUp(self):
        """ spawn lshell with pexpext and return the child """
        self.child = pexpect.spawn('%s/bin/lshell '
                                   '--config %s/etc/lshell.conf --strict 1'
                                   % (TOPDIR, TOPDIR))
        self.child.expect('%s:~\$' % self.user)

    def tearDown(self):
        self.child.close()

    def test_01_welcome_message(self):
        """ F01 | lshell welcome message """
        expected = "You are in a limited shell.\r\nType '?' or 'help' to get" \
            " the list of allowed commands\r\n"
        result = self.child.before.decode('utf8')
        self.assertEqual(expected, result)

    def test_02_builtin_ls_command(self):
        """ F02 | built-in ls command """
        p = subprocess.Popen("ls ~",
                             shell=True,
                             stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE)
        cout = p.stdout
        expected = cout.read(-1)
        self.child.sendline('ls')
        self.child.expect('%s:~\$' % self.user)
        output = self.child.before.decode('utf8').split('ls\r', 1)[1]
        self.assertEqual(len(expected.strip().split()),
                         len(output.strip().split()))

    def test_03_external_echo_command_num(self):
        """ F03 | external echo number """
        expected = "32"
        self.child.sendline('echo 32')
        self.child.expect("%s:~\$" % self.user)
        result = self.child.before.decode('utf8').split()[2]
        self.assertEqual(expected, result)

    def test_04_external_echo_command_string(self):
        """ F04 | external echo random string """
        expected = "bla blabla  32 blibli! plop."
        self.child.sendline('echo "%s"' % expected)
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.decode('utf8').split('\n', 1)[1].strip()
        self.assertEqual(expected, result)

    def test_05_external_echo_forbidden_syntax(self):
        """ F05 | echo forbidden syntax $(bleh) """
        expected = "*** forbidden syntax -> \"echo $(uptime)\"\r\n*** You " \
            "have 1 warning(s) left, before getting kicked out.\r\nThis " \
            "incident has been reported.\r\n"
        self.child.sendline('echo $(uptime)')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.decode('utf8').split('\n', 1)[1]
        self.assertEqual(expected, result)

    def test_06_builtin_cd_change_dir(self):
        """ F06 | built-in cd - change directory """
        expected = ""
        home = os.path.expanduser('~')
        dirpath = None
        for path in os.listdir(home):
            dirpath = os.path.join(home, path)
            if os.path.isdir(dirpath):
                break
        if dirpath:
            self.child.sendline('cd %s' % path)
            self.child.expect('%s:~/%s\$' % (self.user, path))
            self.child.sendline('cd ..')
            self.child.expect('%s:~\$' % self.user)
            result = self.child.before.decode('utf8').split('\n', 1)[1]
            self.assertEqual(expected, result)

    def test_07_builtin_cd_tilda(self):
        """ F07 | built-in cd - tilda bug """
        expected = "*** forbidden path -> \"/etc/passwd\"\r\n*** You have" \
            " 1 warning(s) left, before getting kicked out.\r\nThis " \
            "incident has been reported.\r\n"
        self.child.sendline('ls ~/../../etc/passwd')
        self.child.expect("%s:~\$" % self.user)
        result = self.child.before.decode('utf8').split('\n', 1)[1]
        self.assertEqual(expected, result)

    def test_08_builtin_cd_quotes(self):
        """ F08 | built-in - quotes in cd "/" """
        expected = "*** forbidden path -> \"/\"\r\n*** You have" \
            " 1 warning(s) left, before getting kicked out.\r\nThis " \
            "incident has been reported.\r\n"
        self.child.sendline('ls -ld "/"')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.decode('utf8').split('\n', 1)[1]
        self.assertEqual(expected, result)

    def test_09_external_forbidden_path(self):
        """ F09 | external command forbidden path - ls /root """
        expected = "*** forbidden path -> \"/root/\"\r\n*** You have" \
            " 1 warning(s) left, before getting kicked out.\r\nThis " \
            "incident has been reported.\r\n"
        self.child.sendline('ls ~root')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.decode('utf8').split('\n', 1)[1]
        self.assertEqual(expected, result)

    def test_10_builtin_cd_forbidden_path(self):
        """ F10 | built-in command forbidden path - cd ~root """
        expected = "*** forbidden path -> \"/root/\"\r\n*** You have" \
            " 1 warning(s) left, before getting kicked out.\r\nThis " \
            "incident has been reported.\r\n"
        self.child.sendline('cd ~root')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.decode('utf8').split('\n', 1)[1]
        self.assertEqual(expected, result)

    def test_11_etc_passwd_1(self):
        """ F11 | /etc/passwd: empty variable 'ls "$a"/etc/passwd' """
        expected = "*** forbidden path -> \"/etc/passwd\"\r\n*** You have" \
            " 1 warning(s) left, before getting kicked out.\r\nThis " \
            "incident has been reported.\r\n"
        self.child.sendline('ls "$a"/etc/passwd')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.decode('utf8').split('\n', 1)[1]
        self.assertEqual(expected, result)

    def test_12_etc_passwd_2(self):
        """ F12 | /etc/passwd: empty variable 'ls -l .*./.*./etc/passwd' """
        expected = "*** forbidden path -> \"/etc/passwd\"\r\n*** You have" \
            " 1 warning(s) left, before getting kicked out.\r\nThis " \
            "incident has been reported.\r\n"
        self.child.sendline('ls -l .*./.*./etc/passwd')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.decode('utf8').split('\n', 1)[1]
        self.assertEqual(expected, result)

    def test_13_etc_passwd_3(self):
        """ F13 | /etc/passwd: empty variable 'ls -l .?/.?/etc/passwd' """
        expected = "*** forbidden path -> \"/etc/passwd\"\r\n*** You have" \
            " 1 warning(s) left, before getting kicked out.\r\nThis " \
            "incident has been reported.\r\n"
        self.child.sendline('ls -l .?/.?/etc/passwd')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.decode('utf8').split('\n', 1)[1]
        self.assertEqual(expected, result)

    def test_14_path_completion_tilda(self):
        """ F14 | path completion with ~/ """
        p = subprocess.Popen("ls -F ~/",
                             shell=True,
                             stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE)
        cout = p.stdout
        expected = cout.read(-1)
        self.child.sendline('cd ~/\t\t')
        self.child.expect('%s:~\$' % self.user)
        output = self.child.before.decode('utf8').split('\n', 1)[1]
        self.assertEqual(len(expected.strip().split()),
                         len(output.strip().split()))

    def test_15_cmd_completion_tab_tab(self):
        """ F15 | command completion: tab to list commands """
        expected = '\x07\r\ncd       echo     help     ll       ls       '\
                   '\r\nclear    exit     history  lpath    lsudo'
        self.child.sendline('\t\t')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.decode('utf8').strip()

        self.assertEqual(expected, result)

    def test_16_exitcode_with_separator_external_cmd(self):
        """ F16 | external command exit codes with separator """
        self.child = pexpect.spawn('%s/bin/lshell '
                                   '--config %s/etc/lshell.conf '
                                   '--forbidden "[]"'
                                   % (TOPDIR, TOPDIR))
        self.child.expect('%s:~\$' % self.user)

        expected = "2"
        self.child.sendline('ls nRVmmn8RGypVneYIp8HxyVAvaEaD55; echo $?')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.decode('utf8').split('\n')[2].strip()
        self.assertEqual(expected, result)

    def test_17_exitcode_without_separator_external_cmd(self):
        """ F17 | external command exit codes without separator """
        self.child = pexpect.spawn('%s/bin/lshell '
                                   '--config %s/etc/lshell.conf '
                                   '--forbidden "[]"'
                                   % (TOPDIR, TOPDIR))
        self.child.expect('%s:~\$' % self.user)

        expected = "2"
        self.child.sendline('ls nRVmmn8RGypVneYIp8HxyVAvaEaD55')
        self.child.expect('%s:~\$' % self.user)
        self.child.sendline('echo $?')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.decode('utf8').split('\n')[1].strip()
        self.assertEqual(expected, result)

    def test_18_cd_exitcode_with_separator_internal_cmd(self):
        """ F18 | built-in command exit codes with separator """
        self.child = pexpect.spawn('%s/bin/lshell '
                                   '--config %s/etc/lshell.conf '
                                   '--forbidden "[]"'
                                   % (TOPDIR, TOPDIR))
        self.child.expect('%s:~\$' % self.user)

        expected = "2"
        self.child.sendline('cd nRVmmn8RGypVneYIp8HxyVAvaEaD55; echo $?')
        self.child.expect('%s:~\$' % self.user)
        self.child.sendline('echo $?')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.decode('utf8').split('\n')[1].strip()
        self.assertEqual(expected, result)

    def test_19_cd_exitcode_without_separator_external_cmd(self):
        """ F19 | built-in exit codes without separator """
        self.child = pexpect.spawn('%s/bin/lshell '
                                   '--config %s/etc/lshell.conf '
                                   '--forbidden "[]"'
                                   % (TOPDIR, TOPDIR))
        self.child.expect('%s:~\$' % self.user)

        expected = "2"
        self.child.sendline('cd nRVmmn8RGypVneYIp8HxyVAvaEaD55')
        self.child.expect('%s:~\$' % self.user)
        self.child.sendline('echo $?')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.decode('utf8').split('\n')[1].strip()
        self.assertEqual(expected, result)

    def test_20_cd_with_cmd_unknwon_dir(self):
        """ F20 | test built-in cd with command when dir does not exist
            Should be returning error, not executing cmd
        """
        self.child = pexpect.spawn('%s/bin/lshell '
                                   '--config %s/etc/lshell.conf '
                                   '--forbidden "[]"'
                                   % (TOPDIR, TOPDIR))
        self.child.expect('%s:~\$' % self.user)

        expected = 'lshell: nRVmmn8RGypVneYIp8HxyVAvaEaD55: No such file or '\
                   'directory'

        self.child.sendline('cd nRVmmn8RGypVneYIp8HxyVAvaEaD55; echo $?')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.decode('utf8').split('\n')[1].strip()
        self.assertEqual(expected, result)

    def test_21_allow_slash(self):
        """ F21 | user should able to allow / access minus some directory
            (e.g. /var)
        """
        self.child = pexpect.spawn('%s/bin/lshell '
                                   '--config %s/etc/lshell.conf '
                                   '--path "[\'/\'] - [\'/var\']"'
                                   % (TOPDIR, TOPDIR))
        self.child.expect('%s:~\$' % self.user)

        expected = "*** forbidden path: /var/"
        self.child.sendline('cd /')
        self.child.expect('%s:/\$' % self.user)
        self.child.sendline('cd var')
        self.child.expect('%s:/\$' % self.user)
        result = self.child.before.decode('utf8').split('\n')[1].strip()
        self.assertEqual(expected, result)

    def test_22_expand_env_variables(self):
        """ F22 | expanding of environment variables """
        self.child = pexpect.spawn('%s/bin/lshell '
                                   '--config %s/etc/lshell.conf '
                                   '--allowed "+ [\'export\']"'
                                   % (TOPDIR, TOPDIR))
        self.child.expect('%s:~\$' % self.user)

        expected = "%s/test" % os.path.expanduser('~')
        self.child.sendline('export A=test')
        self.child.expect('%s:~\$' % self.user)
        self.child.sendline('echo $HOME/$A')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.decode('utf8').split('\n')[1].strip()
        self.assertEqual(expected, result)

    def test_23_expand_env_variables_cd(self):
        """ F23 | expanding of environment variables when using cd """
        self.child = pexpect.spawn('%s/bin/lshell '
                                   '--config %s/etc/lshell.conf '
                                   '--allowed "+ [\'export\']"'
                                   % (TOPDIR, TOPDIR))
        self.child.expect('%s:~\$' % self.user)

        random = utils.random_string(32)

        expected = 'lshell: %s/random_%s: No such file or directory' % (
            os.path.expanduser('~'), random)
        self.child.sendline('export A=random_%s' % random)
        self.child.expect('%s:~\$' % self.user)
        self.child.sendline('cd $HOME/$A')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.decode('utf8').split('\n')[1].strip()
        self.assertEqual(expected, result)

    def test_24_cd_and_command(self):
        """ F24 | cd && command should not be interpreted by internal function
        """
        self.child = pexpect.spawn('%s/bin/lshell '
                                   '--config %s/etc/lshell.conf'
                                   % (TOPDIR, TOPDIR))
        self.child.expect('%s:~\$' % self.user)

        expected = "OK"
        self.child.sendline('cd ~ && echo "OK"')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.decode('utf8').split('\n')[1].strip()
        self.assertEqual(expected, result)

    def test_25_KeyboardInterrupt(self):
        """ F25 | test cat(1) with KeyboardInterrupt, should not exit """
        self.child = pexpect.spawn('%s/bin/lshell '
                                   '--config %s/etc/lshell.conf '
                                   '--allowed "+ [\'cat\']"'
                                   % (TOPDIR, TOPDIR))
        self.child.expect('%s:~\$' % self.user)

        self.child.sendline('cat')
        self.child.sendline(' foo ')
        self.child.sendcontrol('c')
        self.child.expect('%s:~\$' % self.user)
        try:
            result = self.child.before.decode('utf8').split('\n')[1].strip()
            # both behaviors are correct
            if result.startswith('foo'):
                expected = 'foo'
            elif result.startswith('^C'):
                expected = '^C'
        except IndexError:
            # outputs u' ^C' on Debian
            expected = u'^C'
            result = self.child.before.decode('utf8').strip()
        self.assertIn(expected, result)

    def test_26_cmd_completion_dot_slash(self):
        """ F26 | command completion: tab to list ./foo1 ./foo2 """
        self.child = pexpect.spawn('%s/bin/lshell '
                                   '--config %s/etc/lshell.conf '
                                   '--allowed "+ [\'./foo1\', \'./foo2\']"'
                                   % (TOPDIR, TOPDIR))
        self.child.expect('%s:~\$' % self.user)

        expected = u'./\x07foo\x07\r\nfoo1  foo2'
        self.child.sendline('./\t\t\t')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.decode('utf8').strip()

        self.assertEqual(expected, result)

    def test_27_checksecure_awk(self):
        """ F27 | checksecure awk script with /bin/bash """
        self.child = pexpect.spawn('%s/bin/lshell '
                                   '--config %s/etc/lshell.conf '
                                   '--allowed "+ [\'awk\']"'
                                   % (TOPDIR, TOPDIR))
        self.child.expect('%s:~\$' % self.user)

        expected = u'*** forbidden path: /bin/bash'
        self.child.sendline('awk \'BEGIN {system("/bin/bash")}\'')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.decode('utf8').split('\n')[1].strip()

        self.assertEqual(expected, result)


if __name__ == '__main__':
    unittest.main()
