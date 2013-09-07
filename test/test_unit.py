import unittest

import lshell
from lshell.shellcmd import ShellCmd, LshellTimeOut
from lshell.checkconfig import CheckConfig
import os

TOPDIR="%s/../" % os.path.dirname(os.path.realpath(__file__))

class TestStringsTest(unittest.TestCase):
  args = ['--config=%s/etc/lshell.conf' % TOPDIR, "--quiet=1"]
  userconf = CheckConfig(args).returnconf()
  shell = ShellCmd(userconf, args)

  def test_checksecure_doublequote(self):
    """ quoted text should not be forbidden """
    INPUT = 'ls -E "1|2" tmp/test'
    return self.assertEqual(self.shell.check_secure(INPUT), 0)

  def test_checksecure_simplequote(self):
    """ quoted text should not be forbidden """
    INPUT = "ls -E '1|2' tmp/test"
    return self.assertEqual(self.shell.check_secure(INPUT), 0)

  def test_checksecure_doublepipe(self):
    """ double pipes should be allowed, even if pipe is forbidden """
    args = self.args + ["--forbidden=['|']"]
    userconf = CheckConfig(args).returnconf()
    shell = ShellCmd(userconf, args)
    INPUT = "ls || ls"
    return self.assertEqual(shell.check_secure(INPUT), 0)

  def test_checksecure_forbiddenpipe(self):
    """ forbid pipe, should return 1 """
    args = self.args + ["--forbidden=['|']"]
    userconf = CheckConfig(args).returnconf()
    shell = ShellCmd(userconf, args)
    INPUT = "ls | ls"
    return self.assertEqual(shell.check_secure(INPUT), 1)

  def test_checksecure_forbiddenchar(self):
    """ forbid character, should return 1 """
    args = self.args + ["--forbidden=['l']"]
    userconf = CheckConfig(args).returnconf()
    shell = ShellCmd(userconf, args)
    INPUT = "ls"
    return self.assertEqual(shell.check_secure(INPUT), 1)

  def test_checksecure_sudo_command(self):
    """ quoted text should not be forbidden """
    INPUT = "sudo ls"
    return self.assertEqual(self.shell.check_secure(INPUT), 1)

  def test_checksecure_notallowed_command(self):
    """ forbidden command, should return 1 """
    args = self.args + ["--allowed=['ls']"]
    userconf = CheckConfig(args).returnconf()
    shell = ShellCmd(userconf, args)
    INPUT = "ll"
    return self.assertEqual(shell.check_secure(INPUT), 1)

  def test_checkpath_notallowed_path(self):
    """ forbidden command, should return 1 """
    args = self.args + ["--path=['/home', '/var']"]
    userconf = CheckConfig(args).returnconf()
    shell = ShellCmd(userconf, args)
    INPUT = "cd /tmp"
    return self.assertEqual(shell.check_path(INPUT), 1)

  def test_checkpath_dollarparenthesis(self):
    """ when $() is allowed, return 0 if path allowed """
    args = self.args + ["--forbidden=[';', '&', '|','`','>','<', '${']"]
    userconf = CheckConfig(args).returnconf()
    shell = ShellCmd(userconf, args)
    INPUT = "echo $(echo aze)"
    return self.assertEqual(shell.check_path(INPUT), 0)

  def test_checkconfig_configoverwrite(self):
    """ forbid ';', then check_secure should return 1 """
    args = ['--config=%s/etc/lshell.conf' % TOPDIR, '--strict=123']
    userconf = CheckConfig(args).returnconf()
    return self.assertEqual(userconf['strict'], 123)

  def test_overssh(self):
    """ test command over ssh """
    args = self.args + ["--overssh=['exit']", '-c exit']
    os.environ['SSH_CLIENT'] = '8.8.8.8 36000 22'
    if os.environ.has_key('SSH_TTY'):
      os.environ.pop('SSH_TTY')
    with self.assertRaises(SystemExit) as cm:
      userconf = CheckConfig(args).returnconf()
    return self.assertEqual(cm.exception.code, 0)

if __name__ == "__main__":
    unittest.main()
