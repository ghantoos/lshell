"""Functional tests for lshell path handling"""

import os
import unittest
from getpass import getuser
import pexpect

TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"
LSHELL = f"{TOPDIR}/bin/lshell"
USER = getuser()
PROMPT = f"{USER}:~\\$"


class TestFunctions(unittest.TestCase):
    """Functional tests for lshell"""

    @staticmethod
    def _normalized_path_for_message(path):
        """Return canonical path text matching lshell forbidden-path formatting."""
        resolved = os.path.realpath(path)
        if os.path.isdir(resolved) and not resolved.endswith("/"):
            return f"{resolved}/"
        return resolved

    @staticmethod
    def _normalize_output(output):
        """Normalize terminal output line endings for stable assertions."""
        return output.replace("\r\n", "\n")

    @staticmethod
    def _expected_warning_line(remaining):
        """Return exact warning line text for strict mode violations."""
        violation_label = "violation" if remaining == 1 else "violations"
        return (
            f"lshell: warning: {remaining} {violation_label} "
            "remaining before session termination\n"
        )

    def _assert_forbidden_path_output(self, output, forbidden_path, remaining):
        """Assert exact forbidden-path output block with no extra lines."""
        expected = (
            f'lshell: forbidden path: "{forbidden_path}"\n'
            f"{self._expected_warning_line(remaining)}"
        )
        self.assertEqual(expected, self._normalize_output(output))

    def _assert_exact_missing_path_error(self, output, path_literal):
        """Assert exact single-line ls missing-path errors across GNU/BSD variants."""
        normalized = self._normalize_output(output)
        expected_variants = {
            f"ls: cannot access '{path_literal}': No such file or directory\n",
            f"ls: {path_literal}: No such file or directory\n",
        }
        self.assertIn(normalized, expected_variants)

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

    def test_external_echo_forbidden_syntax(self):
        """F05 | echo forbidden syntax $(bleh)"""
        expected = (
            'lshell: forbidden character: "$("\r\n'
            "lshell: warning: 1 violation remaining before session termination\r\n"
        )
        self.child.sendline("echo $(uptime)")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self.assertEqual(expected, result)

    def test_external_forbidden_path(self):
        """F09 | external command forbidden path - ls /root"""
        forbidden_root = self._normalized_path_for_message(os.path.expanduser("~root"))
        self.child.sendline("ls ~root")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self._assert_forbidden_path_output(result, forbidden_root, remaining=1)

    def test_builtin_cd_forbidden_path(self):
        """F10 | built-in command forbidden path - cd ~root"""
        forbidden_root = self._normalized_path_for_message(os.path.expanduser("~root"))
        self.child.sendline("cd ~root")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self._assert_forbidden_path_output(result, forbidden_root, remaining=1)

    def test_etc_passwd_1(self):
        """F11 | /etc/passwd: empty variable 'ls "$a"/etc/passwd'"""
        forbidden_path = self._normalized_path_for_message("/etc/passwd")
        self.child.sendline('ls "$a"/etc/passwd')
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self._assert_forbidden_path_output(result, forbidden_path, remaining=1)

    def test_etc_passwd_2(self):
        """F12 | /etc/passwd: empty variable 'ls -l .*./.*./etc/passwd'"""
        self.child.sendline("ls -l .*./.*./etc/passwd")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self._assert_exact_missing_path_error(result, ".*./.*./etc/passwd")

    def test_etc_passwd_3(self):
        """F13(a) | /etc/passwd: empty variable 'ls -l .?/.?/etc/passwd'"""
        self.child.sendline("ls -l .?/.?/etc/passwd")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self._assert_exact_missing_path_error(result, ".?/.?/etc/passwd")

    def test_etc_passwd_4(self):
        """F13(b) | /etc/passwd: empty variable 'ls -l ../../etc/passwd'"""
        forbidden_path = self._normalized_path_for_message("/etc/passwd")
        self.child.sendline("ls -l ../../etc/passwd")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1]
        self._assert_forbidden_path_output(result, forbidden_path, remaining=1)

    def test_allow_slash(self):
        """F21 | user should able to allow / access minus some directory
        (e.g. /var)
        """
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--path \"['/'] - ['/var']\""
        )
        child.expect(PROMPT)

        forbidden_var = self._normalized_path_for_message("/var")
        child.sendline("cd /")
        child.expect(f"{USER}:/\\$")
        child.sendline("cd var")
        child.expect(f"{USER}:/\\$")
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(f'lshell: forbidden path: "{forbidden_var}"', result)
        self.do_exit(child)

    def test_path_plus_minus_reallow_and_warning_messages(self):
        """F22 | path +/- chain should re-allow child path and keep warning countdown."""
        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} "
            "--path \"['/'] - ['/var/','/var/lib/'] + ['/var/log']\" "
            "--warning_counter 2 --strict 1"
        )
        child.expect(PROMPT)

        child.sendline("cd /var")
        child.expect(PROMPT)
        output_1 = child.before.decode("utf8").split("\n", 1)[1]
        self._assert_forbidden_path_output(
            output_1,
            self._normalized_path_for_message("/var"),
            remaining=1,
        )

        child.sendline("cd /var/log")
        canonical_log_prompt_path = os.path.realpath("/var/log")
        child.expect(f"{USER}:{canonical_log_prompt_path}\\$")

        child.sendline("cd /var/lib")
        child.expect(f"{USER}:{canonical_log_prompt_path}\\$")
        output_2 = child.before.decode("utf8").split("\n", 1)[1]
        self._assert_forbidden_path_output(
            output_2,
            self._normalized_path_for_message("/var/lib"),
            remaining=0,
        )

        self.do_exit(child)
