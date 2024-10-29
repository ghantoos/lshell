"""Functional tests for lshell"""

import os
import unittest
import inspect
from getpass import getuser
import pexpect

TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class TestFunctions(unittest.TestCase):
    """Functional tests for lshell"""

    user = getuser()

    def setUp(self):
        """spawn lshell with pexpect and return the child"""
        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell --config {TOPDIR}/etc/lshell.conf --strict 1"
        )
        self.child.expect(f"{self.user}:~\\$")

    def tearDown(self):
        self.child.close()

    def test_51_grep_valid_log_entry(self):
        """Test that grep matches a valid log entry format."""
        pattern = (
            r"\[\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}\s+(?:-|\+)\d{4}\].+UID=[\w.]+"
        )
        f_name = inspect.currentframe().f_code.co_name
        log_file = f"{TOPDIR}/test/testfiles/{f_name}.log"
        command = f"grep -P '{pattern}' {log_file}"

        self.child = pexpect.spawn(
            (
                f"{TOPDIR}/bin/lshell --config {TOPDIR}/etc/lshell.conf "
                f'--allowed "+ [\'grep\']" --forbidden "[]"'
            )
        )
        self.child.expect(f"{self.user}:~\\$")

        self.child.sendline(command)
        self.child.expect(f"{self.user}:~\\$")
        output = self.child.before.decode("utf-8")
        self.assertIn("user123", output)

    def test_52_grep_invalid_date_format(self):
        """Test that grep matches a valid log entry format."""
        pattern = (
            r"\[\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}\s+(?:-|\+)\d{4}\].+UID=[\w.]+"
        )
        f_name = inspect.currentframe().f_code.co_name
        log_file = f"{TOPDIR}/test/testfiles/{f_name}.log"
        command = f"grep -P '{pattern}' {log_file}"

        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell --config {TOPDIR}/etc/lshell.conf "
            '--allowed "+ [\'grep\']" --forbidden "[]"'
        )
        self.child.expect(f"{self.user}:~\\$")

        self.child.sendline(command)
        self.child.expect(f"{self.user}:~\\$")
        output = self.child.before.decode("utf-8")
        self.assertNotIn("user123", output)

    def test_53_grep_missing_uid(self):
        """Test that grep matches a valid log entry format."""
        pattern = (
            r"\[\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}\s+(?:-|\+)\d{4}\].+UID=[\w.]+"
        )
        f_name = inspect.currentframe().f_code.co_name
        log_file = f"{TOPDIR}/test/testfiles/{f_name}.log"
        command = f"grep -P '{pattern}' {log_file}"

        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell --config {TOPDIR}/etc/lshell.conf "
            '--allowed "+ [\'grep\']" --forbidden "[]"'
        )
        self.child.expect(f"{self.user}:~\\$")

        self.child.sendline(command)
        self.child.expect(f"{self.user}:~\\$")
        output = self.child.before.decode("utf-8")
        self.assertNotIn("user123", output)

    def test_54_grep_special_characters_in_uid(self):
        """Test that grep matches a valid log entry format."""
        pattern = (
            r"\[\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}\s+(?:-|\+)\d{4}\].+UID=[\w.]+"
        )
        f_name = inspect.currentframe().f_code.co_name
        log_file = f"{TOPDIR}/test/testfiles/{f_name}.log"
        command = f"grep -P '{pattern}' {log_file}"

        self.child = pexpect.spawn(
            f"{TOPDIR}/bin/lshell --config {TOPDIR}/etc/lshell.conf "
            '--allowed "+ [\'grep\']" --forbidden "[]"'
        )
        self.child.expect(f"{self.user}:~\\$")

        self.child.sendline(command)
        self.child.expect(f"{self.user}:~\\$")
        output = self.child.before.decode("utf-8")
        self.assertIn("user.name", output)
