"""Functional tests for lshell regex handling"""

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

    def test_51_grep_valid_log_entry(self):
        """F51 | Test that grep matches a valid log entry format."""
        pattern = (
            r"\[\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}\s+(?:-|\+)\d{4}\].+UID=[\w.]+"
        )
        f_name = inspect.currentframe().f_code.co_name
        log_file = f"{TOPDIR}/test/testfiles/{f_name}.log"
        command = f"grep -P '{pattern}' {log_file}"

        child = pexpect.spawn(
            (
                f"{LSHELL} --config {CONFIG} "
                f'--allowed "+ [\'grep\']" --forbidden "[]"'
            )
        )
        child.expect(PROMPT)

        child.sendline(command)
        child.expect(PROMPT)
        output = child.before.decode("utf-8")
        self.assertIn("user123", output)
        self.do_exit(child)

    def test_52_grep_invalid_date_format(self):
        """F52 | Test that grep matches a valid log entry format."""
        pattern = (
            r"\[\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}\s+(?:-|\+)\d{4}\].+UID=[\w.]+"
        )
        f_name = inspect.currentframe().f_code.co_name
        log_file = f"{TOPDIR}/test/testfiles/{f_name}.log"

        command = f"grep -P '{pattern}' {log_file}"

        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} " '--allowed "+ [\'grep\']" --forbidden "[]"'
        )
        child.expect(PROMPT)

        child.sendline(command)
        child.expect(PROMPT)
        output = child.before.decode("utf-8")
        self.assertNotIn("user123", output)
        self.do_exit(child)

    def test_53_grep_missing_uid(self):
        """F53 | Test that grep matches a valid log entry format."""
        pattern = (
            r"\[\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}\s+(?:-|\+)\d{4}\].+UID=[\w.]+"
        )
        f_name = inspect.currentframe().f_code.co_name
        log_file = f"{TOPDIR}/test/testfiles/{f_name}.log"

        command = f"grep -P '{pattern}' {log_file}"

        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} " '--allowed "+ [\'grep\']" --forbidden "[]"'
        )
        child.expect(PROMPT)

        child.sendline(command)
        child.expect(PROMPT)
        output = child.before.decode("utf-8")
        self.assertNotIn("user123", output)
        self.do_exit(child)

    def test_54_grep_special_characters_in_uid(self):
        """F54 | Test that grep matches a valid log entry format."""
        pattern = (
            r"\[\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}\s+(?:-|\+)\d{4}\].+UID=[\w.]+"
        )
        f_name = inspect.currentframe().f_code.co_name
        log_file = f"{TOPDIR}/test/testfiles/{f_name}.log"
        command = f"grep -P '{pattern}' {log_file}"

        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} " '--allowed "+ [\'grep\']" --forbidden "[]"'
        )
        child.expect(PROMPT)

        child.sendline(command)
        child.expect(PROMPT)
        output = child.before.decode("utf-8")
        self.assertIn("user.name", output)
        self.do_exit(child)
