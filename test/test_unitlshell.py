import unittest

import lshell
from lshell.shellcmd import ShellCmd, LshellTimeOut
from lshell.checkconfig import CheckConfig
import os

TOPDIR="%s/../" % os.path.dirname(os.path.realpath(__file__))

class TestStringsTest(unittest.TestCase):
  args = ['--config=%s/etc/lshell.conf' % TOPDIR]
  userconf = CheckConfig(args).returnconf()
  shell = ShellCmd(userconf, args)

  def test_doublequote(self):
    """ quoted text should not be forbidden """
    INPUT = 'ls -E "1|2" tmp/test'
    return self.assertEqual(self.shell.check_secure(INPUT), 0)

  def test_simplequote(self):
    """ quoted text should not be forbidden """
    INPUT = "ls -E '1|2' tmp/test"
    return self.assertEqual(self.shell.check_secure(INPUT), 0)

  def test_semicolon(self):
    """ forbid ';', then check_secure should return 1 """
    INPUT = "ls;ls"
    return self.assertEqual(self.shell.check_secure(INPUT), 1)

  def test_configoverwrite(self):
    """ forbid ';', then check_secure should return 1 """
    args = ['--config=%s/etc/lshell.conf' % TOPDIR, '--strict=123']
    userconf = CheckConfig(args).returnconf()
    return self.assertEqual(userconf['strict'], 123)

if __name__ == "__main__":
    unittest.main()
