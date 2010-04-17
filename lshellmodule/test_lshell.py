#!/usr/bin/env python

import unittest
import pexpect
import os
from getpass import getuser

class TestFunctions(unittest.TestCase):

    user = getuser()
    child = pexpect.spawn('./lshell.py --config ../etc/lshell.conf ')

    def spawnlshell(self, oldchild=None):
        """ spawn lshell with pexpext and return the child """
        child = pexpect.spawn('./lshell.py --config ../etc/lshell.conf ')
        if oldchild:
            oldchild.close()
            child.expect('%s:~\$' % getuser())
        return child

    def test_01(self):
        """ 01 - test lshell welcome message """
        expected = "You are in a limited shell.\r\nType '?' or 'help' to get " \
                   "the list of allowed commands\r\n"
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before
        self.assertEqual(expected, result)

    def test_02(self):
        """ 02 - get the output of ls """
        cin, cout = os.popen2('ls ~')
        expected = map(lambda x: x.strip(), cout)
        self.child.sendline('ls')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('ls\r',1)[1].split()
        self.assertEqual(expected, result)

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
        expected = "*** forbidden syntax -> \"echo $(uptime)\"\r\n*** You have"\
                 + " 0 warning(s) left, before getting kicked out.\r\nThis "   \
                 + "incident has been reported.\r\n"
        self.child.sendline('echo $(uptime)')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('\n', 1)[1]
        self.assertEqual(expected, result)

    def test_06_0(self):
        """ 06.0 - change directory """
        self.child = self.spawnlshell(self.child)
        expected = ""
        self.child.sendline('cd tmp')
        self.child.expect('%s:~/tmp\$' % self.user)
        self.child.sendline('cd ..')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('\n', 1)[1]
        self.assertEqual(expected, result)

    def test_06_1(self):
        """ 06.1 - tilda bug """
        self.child = self.spawnlshell(self.child)
        expected = "*** forbidden path -> \"/etc/passwd\"\r\n*** You have"     \
                 + " 0 warning(s) left, before getting kicked out.\r\nThis "   \
                 + "incident has been reported.\r\n"
        self.child.sendline('cd tmp')
        self.child.expect('%s:~/tmp\$' % self.user)
        self.child.sendline('ls ~/../../etc/passwd')
        self.child.expect('%s:~/tmp\$' % self.user)
        result = self.child.before.split('\n', 1)[1]
        self.assertEqual(expected, result)

    def test_07(self):
        """ 07 - quotes in cd "/" """
        self.child = self.spawnlshell(self.child)
        expected = "*** forbidden path -> \"/\"\r\n*** You have"               \
                 + " 0 warning(s) left, before getting kicked out.\r\nThis "   \
                 + "incident has been reported.\r\n"
        self.child.sendline('ls -ld "/"')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('\n', 1)[1]
        self.assertEqual(expected, result)

    def test_08(self):
        """ 08 - ls ~root """
        self.child = self.spawnlshell(self.child)
        expected = "*** forbidden path -> \"/root/\"\r\n*** You have"          \
                 + " 0 warning(s) left, before getting kicked out.\r\nThis "   \
                 + "incident has been reported.\r\n"
        self.child.sendline('ls ~root')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('\n', 1)[1]
        self.assertEqual(expected, result)

    def test_09(self):
        """ 09 - cd ~root """
        self.child = self.spawnlshell(self.child)
        expected = "*** forbidden path -> \"/root/\"\r\n*** You have"          \
                 + " 0 warning(s) left, before getting kicked out.\r\nThis "   \
                 + "incident has been reported.\r\n"
        self.child.sendline('cd ~root')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('\n', 1)[1]
        self.assertEqual(expected, result)

    def test_10(self):
        """ 10 - empty variable 'ls "$a"/etc/passwd' """
        self.child = self.spawnlshell(self.child)
        expected = "*** forbidden path -> \"/etc/passwd\"\r\n*** You have"    \
                 + " 0 warning(s) left, before getting kicked out.\r\nThis "   \
                 + "incident has been reported.\r\n"
        self.child.sendline('ls "$a"/etc/passwd')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('\n', 1)[1]
        self.assertEqual(expected, result)

    def test_11(self):
        """ 11 - empty variable 'ls -l .*./.*./etc/passwd' """
        self.child = self.spawnlshell(self.child)
        expected = "*** forbidden path -> \"/etc/passwd\"\r\n*** You have"    \
                 + " 0 warning(s) left, before getting kicked out.\r\nThis "   \
                 + "incident has been reported.\r\n"
        self.child.sendline('ls -l .*./.*./etc/passwd')
        self.child.expect('%s:~\$' % self.user)  
        result = self.child.before.split('\n', 1)[1]
        self.assertEqual(expected, result)

    def test_12(self):
        """ 12 - empty variable 'ls -l .?/.?/etc/passwd' """
        self.child = self.spawnlshell(self.child)
        expected = "*** forbidden path -> \"/etc/passwd\"\r\n*** You have"    \
                 + " 0 warning(s) left, before getting kicked out.\r\nThis "   \
                 + "incident has been reported.\r\n"
        self.child.sendline('ls -l .?/.?/etc/passwd')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('\n', 1)[1]
        self.assertEqual(expected, result)

    def test_13(self):
        """ 13 - completion with ~/ """
        self.child = self.spawnlshell(self.child)
        cin, cout = os.popen2('ls -F ~/tmp')
        expected = map(lambda x: x.strip(), cout)
        self.child.sendline('cd ~/tmp/\t\t')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('\n',1)[1].split()
        result.sort()
        self.assertEqual(expected, result)

#    def test_14(self):
#        """ 14 - command over ssh """
        

    def test_99(self):
        """ 99 - tab to list commands """
        self.child = self.spawnlshell(self.child)
        expected = '\x07\r\ncd     clear  echo   exit   help   ll     lpath  ls'
        self.child.sendline('\t\t')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.strip()
        self.assertEqual(expected, result)

    def test_99(self):
        """ 99 - completion test 1 """
        self.child = self.spawnlshell(self.child)
        cin, cout = os.popen2('\nls -F ~')
        expected = map(lambda x: x.strip(), cout)
        self.child.sendline('ls ~\t\t')
        self.child.expect('%s:~\$' % self.user)
        result = self.child.before.split('\n', 1)[1].split()
        self.assertEqual(expected, result)

#    def test_exit(self):
#        expected = ''
#        self.child.sendline('exit')
#        self.child.expect('$')
#        result = self.child.before
#        self.assertEqual(expected, result)


if __name__ == '__main__':
    unittest.main()
