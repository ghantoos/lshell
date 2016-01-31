import unittest
import pexpect
import os
import subprocess
from getpass import getuser

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

    def test_01(self):
        """ 01 - test lshell welcome message """
        expected = "You are in a limited shell.\r\nType '?' or 'help' to get" \
            " the list of allowed commands\r\n"
        result = self.child.before
        self.assertEqual(expected, result)

    def test_02(self):
        """ 02 - get the output of ls """
        p = subprocess.Popen("ls ~",
                             shell=True,
                             stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE)
        cout = p.stdout
        expected = cout.read(-1)
        self.child.sendline('ls')
        self.child.expect('%s:~\$' % self.user)
        output = self.child.before.split('ls\r', 1)[1]
        self.assertEqual(len(expected.strip().split()),
                         len(output.strip().split()))

    def test_03(self):
        """ 03 - echo number """
        expected = "32"
        self.child.sendline('echo 32')
        self.child.expect("%s:~\$" % self.user)
        result = self.child.before.split()[2]
        self.assertEqual(expected, result)

    def test_04(self):
        """ 04 - echo anything """
        expected = "bla blabla  32 blibli! plop."
        self.child.sendline('echo "%s"' % expected)
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('\n', 1)[1].strip()
        self.assertEqual(expected, result)

    def test_05(self):
        """ 05 - echo $(uptime) """
        expected = "*** forbidden syntax -> \"echo $(uptime)\"\r\n*** You " \
            "have 1 warning(s) left, before getting kicked out.\r\nThis " \
            "incident has been reported.\r\n"
        self.child.sendline('echo $(uptime)')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('\n', 1)[1]
        self.assertEqual(expected, result)

    def test_06_0(self):
        """ 06.0 - change directory """
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
            result = self.child.before.split('\n', 1)[1]
            self.assertEqual(expected, result)

    def test_06_1(self):
        """ 06.1 - tilda bug """
        expected = "*** forbidden path -> \"/etc/passwd\"\r\n*** You have" \
            " 1 warning(s) left, before getting kicked out.\r\nThis " \
            "incident has been reported.\r\n"
        self.child.sendline('ls ~/../../etc/passwd')
        self.child.expect("%s:~\$" % self.user)
        result = self.child.before.split('\n', 1)[1]
        self.assertEqual(expected, result)

    def test_07(self):
        """ 07 - quotes in cd "/" """
        expected = "*** forbidden path -> \"/\"\r\n*** You have" \
            " 1 warning(s) left, before getting kicked out.\r\nThis " \
            "incident has been reported.\r\n"
        self.child.sendline('ls -ld "/"')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('\n', 1)[1]
        self.assertEqual(expected, result)

    def test_08(self):
        """ 08 - ls ~root """
        expected = "*** forbidden path -> \"/root/\"\r\n*** You have" \
            " 1 warning(s) left, before getting kicked out.\r\nThis " \
            "incident has been reported.\r\n"
        self.child.sendline('ls ~root')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('\n', 1)[1]
        self.assertEqual(expected, result)

    def test_09(self):
        """ 09 - cd ~root """
        expected = "*** forbidden path -> \"/root/\"\r\n*** You have" \
            " 1 warning(s) left, before getting kicked out.\r\nThis " \
            "incident has been reported.\r\n"
        self.child.sendline('cd ~root')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('\n', 1)[1]
        self.assertEqual(expected, result)

    def test_10(self):
        """ 10 - empty variable 'ls "$a"/etc/passwd' """
        expected = "*** forbidden path -> \"/etc/passwd\"\r\n*** You have" \
            " 1 warning(s) left, before getting kicked out.\r\nThis " \
            "incident has been reported.\r\n"
        self.child.sendline('ls "$a"/etc/passwd')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('\n', 1)[1]
        self.assertEqual(expected, result)

    def test_11(self):
        """ 11 - empty variable 'ls -l .*./.*./etc/passwd' """
        expected = "*** forbidden path -> \"/etc/passwd\"\r\n*** You have" \
            " 1 warning(s) left, before getting kicked out.\r\nThis " \
            "incident has been reported.\r\n"
        self.child.sendline('ls -l .*./.*./etc/passwd')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('\n', 1)[1]
        self.assertEqual(expected, result)

    def test_12(self):
        """ 12 - empty variable 'ls -l .?/.?/etc/passwd' """
        expected = "*** forbidden path -> \"/etc/passwd\"\r\n*** You have" \
            " 1 warning(s) left, before getting kicked out.\r\nThis " \
            "incident has been reported.\r\n"
        self.child.sendline('ls -l .?/.?/etc/passwd')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('\n', 1)[1]
        self.assertEqual(expected, result)

    def test_13(self):
        """ 13 - completion with ~/ """
        p = subprocess.Popen("ls -F ~/",
                             shell=True,
                             stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE)
        cout = p.stdout
        expected = cout.read(-1)
        self.child.sendline('cd ~/\t\t')
        self.child.expect('%s:~\$' % self.user)
        output = self.child.before.split('\n', 1)[1]
        self.assertEqual(len(expected.strip().split()),
                         len(output.strip().split()))

#    def test_14(self):
#        """ 14 - command over ssh """

    def test_15(self):
        """ 15 - tab to list commands """
        expected = '\x07\r\ncd       echo     help     ll       ls       \r\n'\
            'clear    exit     history  lpath    lsudo'
        self.child.sendline('\t\t')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.strip()
        self.assertEqual(expected, result)

#    def test_exit(self):
#        expected = ''
#        self.child.sendline('exit')
#        self.child.expect('$')
#        result = self.child.before
#        self.assertEqual(expected, result)

    def test_16a_exitcode_with_separator_external_cmd(self):
        """ 16a - test external command exit codes with separator """
        self.child = pexpect.spawn('%s/bin/lshell '
                                   '--config %s/etc/lshell.conf --forbidden "[]"'
                                   % (TOPDIR, TOPDIR))
        self.child.expect('%s:~\$' % self.user)

        expected = "2"
        self.child.sendline('ls nRVmmn8RGypVneYIp8HxyVAvaEaD55; echo $?')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('\n')[2].strip()
        self.assertEqual(expected, result)

    def test_16b_exitcode_without_separator_external_cmd(self):
        """ 16b - test external command exit codes without separator """
        self.child = pexpect.spawn('%s/bin/lshell '
                                   '--config %s/etc/lshell.conf --forbidden "[]"'
                                   % (TOPDIR, TOPDIR))
        self.child.expect('%s:~\$' % self.user)

        expected = "2"
        self.child.sendline('ls nRVmmn8RGypVneYIp8HxyVAvaEaD55')
        self.child.expect('%s:~\$' % self.user)
        self.child.sendline('echo $?')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('\n')[1].strip()
        self.assertEqual(expected, result)

    def test_17a_exitcode_with_separator_internal_cmd(self):
        """ 17a - test built-in command exit codes with separator """
        self.child = pexpect.spawn('%s/bin/lshell '
                                   '--config %s/etc/lshell.conf --forbidden "[]"'
                                   % (TOPDIR, TOPDIR))
        self.child.expect('%s:~\$' % self.user)

        expected = "2"
        self.child.sendline('cd nRVmmn8RGypVneYIp8HxyVAvaEaD55; echo $?')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('\n')[2].strip()
        self.assertEqual(expected, result)

    def test_17b_exitcode_without_separator_external_cmd(self):
        """ 17b - test built-in exit codes without separator """
        self.child = pexpect.spawn('%s/bin/lshell '
                                   '--config %s/etc/lshell.conf --forbidden "[]"'
                                   % (TOPDIR, TOPDIR))
        self.child.expect('%s:~\$' % self.user)

        expected = "2"
        self.child.sendline('cd nRVmmn8RGypVneYIp8HxyVAvaEaD55')
        self.child.expect('%s:~\$' % self.user)
        self.child.sendline('echo $?')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('\n')[1].strip()
        self.assertEqual(expected, result)

    def test_18_allow_slash(self):
        """ 18 - user should able to allow / access minus some directory (e.g. /var) """
        self.child = pexpect.spawn('%s/bin/lshell '
                                   '--config %s/etc/lshell.conf --path "[\'/\'] - [\'/var\']"'
                                   % (TOPDIR, TOPDIR))
        self.child.expect('%s:~\$' % self.user)

        expected = "*** forbidden path: /var/"
        self.child.sendline('cd /')
        self.child.expect('%s:/\$' % self.user)
        self.child.sendline('cd var')
        self.child.expect('%s:/\$' % self.user)
        result = self.child.before.split('\n')[1].strip()
        self.assertEqual(expected, result)

    def test_19_expand_env_variables(self):
        """ 19 - test expanding of environment variables """
        self.child = pexpect.spawn('%s/bin/lshell '
                                   '--config %s/etc/lshell.conf --allowed "+ [\'export\']"'
                                   % (TOPDIR, TOPDIR))
        self.child.expect('%s:~\$' % self.user)

        expected = "%s/test" % os.path.expanduser('~')
        self.child.sendline('export A=test')
        self.child.expect('%s:~\$' % self.user)
        self.child.sendline('echo $HOME/$A')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('\n')[1].strip()
        self.assertEqual(expected, result)

    def test_20_expand_env_variables_cd(self):
        """ 20 - test expanding of environment variables when using cd """
        self.child = pexpect.spawn('%s/bin/lshell '
                                   '--config %s/etc/lshell.conf --allowed "+ [\'export\']"'
                                   % (TOPDIR, TOPDIR))
        self.child.expect('%s:~\$' % self.user)

        import random
        import string

        random = ''.join([random.choice(string.ascii_letters + string.digits) for n in xrange(32)])

        expected = "lshell: %s/random_%s: No such file or directory" \
                                            % (os.path.expanduser('~'),random)
        self.child.sendline('export A=random_%s' % random)
        self.child.expect('%s:~\$' % self.user)
        self.child.sendline('cd $HOME/$A')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('\n')[1].strip()
        self.assertEqual(expected, result)

    def test_21_cd_and_command(self):
        """ 07 - cd && command should not be interpreted by internal function """
        self.child = pexpect.spawn('%s/bin/lshell '
                                   '--config %s/etc/lshell.conf'
                                   % (TOPDIR, TOPDIR))
        self.child.expect('%s:~\$' % self.user)

        expected = "OK"
        self.child.sendline('cd ~ && echo "OK"')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('\n')[1].strip()
        self.assertEqual(expected, result)

    def test_22_KeyboardInterrupt(self):
        """ 07 - test cat(1) with KeyboardInterrupt, should not exit """
        self.child = pexpect.spawn('%s/bin/lshell '
                                   '--config %s/etc/lshell.conf --allowed "+ [\'cat\']"'
                                   % (TOPDIR, TOPDIR))
        self.child.expect('%s:~\$' % self.user)

        expected = ""
        self.child.sendline('cat')
        self.child.sendcontrol('c');
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('\n')[1].strip()
        self.assertEqual(expected, result)

if __name__ == '__main__':
    unittest.main()
