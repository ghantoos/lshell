"""Functional tests for file extension restrictions"""

import os
import unittest
import tempfile
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

    def test_allowed_extension_success(self):
        """F60 | allow extension and cat file with similar extension"""

        log_file = f"{TOPDIR}/test/testfiles/test_60_allowed_extension_success.log"
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

    def test_allowed_extension_fail(self):
        """F61 | allow extension and cat file with different extension"""

        command = f"cat {CONFIG}"
        expected = f"lshell: forbidden file extension ['.conf']: \"cat {CONFIG}\""

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

    def test_allowed_extension_empty(self):
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

    def test_extensionless_filename_is_forbidden(self):
        """F63 | extensionless file arguments are rejected when extensions are enforced."""
        target = os.path.join(tempfile.gettempdir(), "lshell_extensionless_target")
        if os.path.exists(target):
            os.remove(target)

        command = f"touch {target}"
        expected = f"lshell: forbidden file extension ['<none>']: \"{command}\""

        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} "
            "--allowed \"+ ['touch']\" "
            "--allowed_file_extensions \"['.log']\""
        )
        child.expect(PROMPT)

        child.sendline(command)
        child.expect(PROMPT)
        output = child.before.decode("utf-8").split("\n")[1].strip()
        self.assertEqual(expected, output)
        self.assertFalse(os.path.exists(target))
        self.do_exit(child)

    def test_allowed_file_extensions_plus_minus_chain(self):
        """F64 | +/- merge on allowed_file_extensions controls warning outcome."""
        f_name = "test_60_allowed_extension_success"
        log_file = f"{TOPDIR}/test/testfiles/{f_name}.log"
        conf_file = CONFIG

        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} "
            "--allowed \"+ ['cat']\" "
            "--allowed_file_extensions \"['.log'] + ['.conf'] - ['.log']\" "
            "--warning_counter 2 --strict 1"
        )
        child.expect(PROMPT)

        child.sendline(f"cat {log_file}")
        child.expect(PROMPT)
        denied_output = child.before.decode("utf-8")
        self.assertIn("forbidden file extension ['.log']", denied_output)
        self.assertIn("lshell: warning: 1 violation remaining", denied_output)

        child.sendline(f"cat {conf_file}")
        child.expect(PROMPT)
        allowed_output = child.before.decode("utf-8")
        self.assertIn("[global]", allowed_output)

        self.do_exit(child)
