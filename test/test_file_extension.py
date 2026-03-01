"""Functional tests for file extension restrictions"""

import os
import unittest
import inspect
from getpass import getuser
import pexpect


TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"
LSHELL = f"{TOPDIR}/bin/lshell"
USER = getuser()
PROMPT = f"{USER}:~\\$"


class TestFunctions(unittest.TestCase):
    """Functional tests for lshell"""

    def do_exit(self, child):
        """Exit the shell"""
        child.sendline("exit")
        child.expect(pexpect.EOF)

    def test_60_allowed_extension_success(self):
        """F60 | allow extension and cat file with similar extension"""

        f_name = inspect.currentframe().f_code.co_name
        log_file = f"{TOPDIR}/test/testfiles/{f_name}.log"
        command = f"cat {log_file}"
        expected = "Hello world!"

        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} "
            "--allowed \"+ ['cat']\" "
            "--allowed_file_extensions \"['.log']\""
        )
        child.expect(PROMPT)

        child.sendline(command)
        child.expect(PROMPT)
        output = child.before.decode("utf-8").split("\n")[1].strip()
        self.assertEqual(expected, output)
        self.do_exit(child)

    def test_61_allowed_extension_fail(self):
        """F61 | allow extension and cat file with different extension"""

        command = f"cat {CONFIG}"
        expected = f"*** forbidden file extension ['.conf']: \"cat {CONFIG}\""

        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} "
            "--allowed \"+ ['cat']\" "
            "--allowed_file_extensions \"['.log']\""
        )
        child.expect(PROMPT)

        child.sendline(command)
        child.expect(PROMPT)
        output = child.before.decode("utf-8").split("\n")[1].strip()
        self.assertEqual(expected, output)
        self.do_exit(child)

    def test_62_allowed_extension_empty(self):
        """F62 | allow extension empty and cat any file extension"""

        command = f"cat {CONFIG}"
        expected = "[global]"

        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} "
            "--allowed \"+ ['cat']\" "
            '--allowed_file_extensions "[]"'
        )
        child.expect(PROMPT)

        child.sendline(command)
        child.expect(PROMPT)
        output = child.before.decode("utf-8").split("\n")[1].strip()
        self.assertEqual(expected, output)
        self.do_exit(child)
