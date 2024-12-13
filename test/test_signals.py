"""Functional tests for lshell terminal signals"""

import os
import unittest
import time
from getpass import getuser
import pexpect


TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"
LSHELL = f"{TOPDIR}/bin/lshell"
USER = getuser()
PROMPT = f"{USER}:~\\$"


class TestFunctions(unittest.TestCase):
    """Functional tests for lshell"""

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

    def test_25_keyboard_interrupt(self):
        """F25 | test cat(1) with KeyboardInterrupt, should not exit"""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--allowed \"+ ['cat']\""
        )
        child.expect(PROMPT)

        child.sendline("cat")
        child.sendline(" foo ")
        child.sendcontrol("c")
        child.expect(PROMPT)
        try:
            result = child.before.decode("utf8").split("\n")[1].strip()
            # both behaviors are correct
            if result.startswith("foo"):
                expected = "foo"
            elif result.startswith("^C"):
                expected = "^C"
            else:
                expected = "unknown"
        except IndexError:
            # outputs u' ^C' on Debian
            expected = "^C"
            result = child.before.decode("utf8").strip()
        self.assertIn(expected, result)
        self.do_exit(child)

    def test_28_catch_terminal_ctrl_j(self):
        """F28 | test ctrl-v ctrl-j then command, forbidden/security"""
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG} ")
        child.expect(PROMPT)

        expected = "bash\r"
        child.send("echo")
        child.sendcontrol("v")
        child.sendcontrol("j")
        child.sendline("bash")
        child.expect(PROMPT)

        result = child.before.decode("utf8").split("\n")[1]

        self.assertIn(expected, result)
        self.do_exit(child)

    def test_29_catch_terminal_ctrl_k(self):
        """F29 | test ctrl-v ctrl-k then command, forbidden/security"""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} --forbidden \"-['&',';']\""
        )
        child.expect(PROMPT)

        expected = "*** forbidden command: echo()\r"
        child.send("echo")
        child.sendcontrol("v")
        child.sendcontrol("k")
        child.sendline("() bash && echo")
        child.expect(PROMPT)

        result = child.before.decode("utf8").split("\n")[1]

        self.assertIn(expected, result)
        self.do_exit(child)

    def test_71_backgrounding_with_ctrl_z(self):
        """F71 | est backgrounding a command with Ctrl+Z."""
        child = pexpect.spawn(f"{LSHELL} --config {CONFIG} --allowed \"+['tail']\"")
        child.expect(PROMPT)

        # Start a long-running command
        for file in ["file1", "file2", "file3"]:
            with open(file, "w") as f:
                f.write(f"{file} content")
            child.sendline(f"tail -f {file}")
            time.sleep(1)
            child.sendcontrol("z")
            # Verify stopped job message
            child.expect(r"\[\d+\]\+  Stopped        tail -f", timeout=1)

        # Check jobs output
        child.expect(PROMPT)
        child.sendline("jobs")
        child.expect(PROMPT)
        output = child.before.decode("utf-8").split("\n", 1)[1].strip()
        expected_output = (
            "[1]   Stopped        tail -f file1\r\n"
            "[2]-  Stopped        tail -f file2\r\n"
            "[3]+  Stopped        tail -f file3"
        )

        assert (
            output == expected_output
        ), f"Expected '{expected_output}', got '{output}'"

        # Resume the stopped job
        child.sendline("fg")
        child.sendcontrol("c")
        child.sendline("fg")
        child.sendcontrol("c")
        child.sendline("fg")
        child.sendcontrol("c")
        time.sleep(1)
        child.expect(PROMPT)

    def test_72_background_command_with_ampersand(self):
        """F72 | Test backgrounding a command with `&`."""
        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} --allowed \"+['sleep']\" --forbidden \"-['&',';']\""
        )
        child.expect(PROMPT)

        # Run a background command with &
        child.sendline("sleep 60 &")
        child.expect(r"\[\d+\] sleep 60 \(pid: \d+\)", timeout=5)
        child.sendline("sleep 60 &")
        child.expect(r"\[\d+\] sleep 60 \(pid: \d+\)", timeout=5)
        child.sendline("sleep 60 &")
        child.expect(r"\[\d+\] sleep 60 \(pid: \d+\)", timeout=5)

        # Verify it's listed in jobs
        child.expect(PROMPT)
        child.sendline("jobs")
        child.expect(PROMPT)
        output = child.before.decode("utf-8").split("\n", 1)[1].strip()
        expected_output = (
            "[1]   Stopped        sleep 60\r\n"
            "[2]-  Stopped        sleep 60\r\n"
            "[3]+  Stopped        sleep 60"
        )

        assert (
            output == expected_output
        ), f"Expected '{expected_output}', got '{output}'"

    def test_73_exit_with_stopped_jobs(self):
        """F73 | Test exiting with stopped jobs."""
        child = pexpect.spawn(f"{LSHELL} --config {CONFIG} --allowed \"+['tail']\"")
        child.expect(PROMPT)

        # Start a long-running command and background it
        child.sendline("tail -f")
        time.sleep(1)
        child.sendcontrol("z")
        child.expect(r"\[\d+\]\+  Stopped        tail -f", timeout=1)

        # Attempt to exit
        child.sendline("exit")
        child.expect("There are stopped jobs.", timeout=5)

        # Verify stopped jobs are listed
        child.sendline("jobs")
        child.expect(r"\[\d+\]\+  Stopped        tail -f", timeout=5)

        # Exit again
        child.sendline("exit")
        child.expect(pexpect.EOF, timeout=5)

    def test_74_resume_stopped_jobs(self):
        """F74 | Test resuming stopped jobs."""
        child = pexpect.spawn(f"{LSHELL} --config {CONFIG} --allowed \"+['tail']\"")
        child.expect(PROMPT)

        # Start and stop multiple jobs
        child.sendline("tail -f")
        time.sleep(1)
        child.sendcontrol("z")
        child.expect(r"\[\d+\]\+  Stopped        tail -f", timeout=1)
        child.sendline("tail -ff")
        time.sleep(1)
        child.sendcontrol("z")
        child.expect(r"\[\d+\]\+  Stopped        tail -ff", timeout=1)
        child.sendline("tail -fff")
        time.sleep(1)
        child.sendcontrol("z")
        child.expect(r"\[\d+\]\+  Stopped        tail -fff", timeout=1)
        child.sendline("tail -ffff")
        time.sleep(1)
        child.sendcontrol("z")
        child.expect(r"\[\d+\]\+  Stopped        tail -ffff", timeout=1)

        # Resume the second job
        child.sendline("fg 2")
        child.expect("tail -ff", timeout=5)
        child.sendcontrol("c")  # Send Ctrl+C to stop the job
        child.expect(PROMPT)

        # Resume the first job
        child.sendline("fg 1")
        child.expect("tail -f", timeout=5)
        child.sendcontrol("c")  # Send Ctrl+C to stop the job
        child.expect(PROMPT)

        # Resume the last two jobs
        child.sendline("fg")
        child.expect("tail -ffff", timeout=5)
        child.sendcontrol("c")  # Send Ctrl+C to stop the job
        child.expect(PROMPT)
        child.sendline("fg")
        child.expect("tail -fff", timeout=5)
        child.sendcontrol("c")  # Send Ctrl+C to stop the job
        child.expect(PROMPT)

    def test_75_interrupt_background_commands(self):
        """F75 | Test that `Ctrl+C` does not interrupt background commands."""
        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} --allowed \"+['sleep']\" --forbidden \"-['&',';']\""
        )
        child.expect(PROMPT)

        # Run a background command
        child.sendline("sleep 60 &")
        child.expect(r"\[\d+\] sleep 60 \(pid: \d+\)", timeout=5)

        # Interrupt the foreground process (should not affect background)
        child.sendcontrol("c")
        child.expect(PROMPT)

        # Verify the background command is still running
        child.sendline("jobs")
        child.expect(r"\[\d+\]\+  Stopped        sleep 60", timeout=5)

    def test_76_jobs_after_completion(self):
        """F76 | Test that completed jobs are removed from the `jobs` list."""
        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} --allowed \"+['sleep']\" --forbidden \"-['&',';']\""
        )
        child.expect(PROMPT)

        # Run a short-lived background command
        child.sendline("sleep 2 &")
        child.expect(r"\[\d+\] sleep 2 \(pid: \d+\)", timeout=5)

        # Wait for the process to complete
        time.sleep(3)

        # Verify jobs output is empty
        child.sendline("jobs")
        child.expect(PROMPT)
        output = child.before.decode("utf-8").split("\n", 1)[1].strip()
        assert output == "", f"Expected no jobs, got: '{output}'"

    def test_77_mix_background_and_foreground(self):
        """F77 | Test mixing background and foreground commands."""
        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} --allowed \"+['sleep', 'tail']\" --forbidden \"-['&',';']\""
        )
        child.expect(PROMPT)

        # Start a background command
        child.sendline("sleep 60 &")
        child.expect(r"\[\d+\] sleep 60 \(pid: \d+\)", timeout=5)

        # Start and stop a foreground command
        child.sendline("tail -f file1")
        time.sleep(1)
        child.sendcontrol("z")
        child.expect(r"\[\d+\]\+  Stopped        tail -f", timeout=1)

        # Verify jobs output
        child.expect(PROMPT)
        child.sendline("jobs")
        child.expect(PROMPT)
        output = child.before.decode("utf-8").split("\n", 1)[1].strip()
        expected_output = (
            "[1]-  Stopped        sleep 60\r\n[2]+  Stopped        tail -f file1"
        )

        assert (
            output == expected_output
        ), f"Expected '{expected_output}', got '{output}'"
