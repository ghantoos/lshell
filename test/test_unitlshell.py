import unittest

import lshell
from lshell.shellcmd import ShellCmd, LshellTimeOut
from lshell.checkconfig import CheckConfig
import os

TOPDIR="%s/../" % os.path.dirname(os.path.realpath(__file__))

class TestStringsTest(unittest.TestCase):
    args = ['--config', '%s/etc/lshell.conf' % TOPDIR]
    userconf = CheckConfig(args).returnconf()
    shell = ShellCmd(userconf, args)

    def test_doublequote(self):
        INPUT = 'ls -E "1|2" tmp/test'
        return self.assertEqual(self.shell.check_secure(INPUT), 0)

    def test_simplequote(self):
        INPUT = "ls -E '1|2' tmp/test"
        return self.assertEqual(self.shell.check_secure(INPUT), 0)

if __name__ == "__main__":
    unittest.main()
