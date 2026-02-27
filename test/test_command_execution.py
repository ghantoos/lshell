"""Functional tests for lshell command execution"""

import os
import random
import unittest
from getpass import getuser
import pexpect

# pylint: disable=C0411
from test import test_utils

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

    def test_03_external_echo_command_num(self):
        """F03 | external echo number"""
        expected = "32"
        self.child.sendline("echo 32")
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split()[2]
        self.assertEqual(expected, result)

    def test_04_external_echo_command_string(self):
        """F04 | external echo random string"""
        expected = "bla blabla  32 blibli! plop."
        self.child.sendline(f'echo "{expected}"')
        self.child.expect(PROMPT)
        result = self.child.before.decode("utf8").split("\n", 1)[1].strip()
        self.assertEqual(expected, result)

    def test_16a_exitcode_with_separator_external_cmd(self):
        """F16(a) | external command exit codes with separator"""
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG} " '--forbidden "[]"')
        child.expect(PROMPT)

        if test_utils.is_alpine_linux():
            expected_1 = "ls: nRVmmn8RGypVneYIp8HxyVAvaEaD55: No such file or directory"
        else:
            expected_1 = (
                "ls: cannot access 'nRVmmn8RGypVneYIp8HxyVAvaEaD55': "
                "No such file or directory"
            )
        expected_2 = "blabla"
        expected_3 = "0"
        child.sendline("ls nRVmmn8RGypVneYIp8HxyVAvaEaD55; echo blabla; echo $?")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")
        result_1 = result[1].strip()
        result_2 = result[2].strip()
        result_3 = result[3].strip()
        self.assertEqual(expected_1, result_1)
        self.assertEqual(expected_2, result_2)
        self.assertEqual(expected_3, result_3)
        self.do_exit(child)

    def test_16b_exitcode_with_separator_external_cmd(self):
        """F16(b) | external command exit codes with separator"""
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG} " '--forbidden "[]"')
        child.expect(PROMPT)

        if test_utils.is_alpine_linux():
            expected_1 = "ls: nRVmmn8RGypVneYIp8HxyVAvaEaD55: No such file or directory"
            expected_2 = "1"
        else:
            expected_1 = (
                "ls: cannot access 'nRVmmn8RGypVneYIp8HxyVAvaEaD55': "
                "No such file or directory"
            )
            expected_2 = "2"
        child.sendline("ls nRVmmn8RGypVneYIp8HxyVAvaEaD55; echo $?")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")
        result_1 = result[1].strip()
        result_2 = result[2].strip()
        self.assertEqual(expected_1, result_1)
        self.assertEqual(expected_2, result_2)
        self.do_exit(child)

    def test_17_exitcode_without_separator_external_cmd(self):
        """F17 | external command exit codes without separator"""
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG} " '--forbidden "[]"')
        child.expect(PROMPT)

        if test_utils.is_alpine_linux():
            expected = "1"
        else:
            expected = "2"
        child.sendline("ls nRVmmn8RGypVneYIp8HxyVAvaEaD55")
        child.expect(PROMPT)
        child.sendline("echo $?")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_24_cd_and_command(self):
        """F24 | cd && command should not be interpreted by internal function"""
        child = pexpect.spawn(f"{LSHELL} " f"--config {CONFIG} --forbidden \"-['&']\"")
        child.expect(PROMPT)

        expected = "OK"
        child.sendline('cd ~ && echo "OK"')
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_33_ls_non_existing_directory_and_echo(self):
        """Test: ls non_existing_directory && echo nothing"""
        child = pexpect.spawn(f"{LSHELL} --config {CONFIG}")
        child.expect(PROMPT)

        child.sendline("ls non_existing_directory && echo nothing")
        child.expect(PROMPT)

        output = child.before.decode("utf8").split("\n", 1)[1].strip()
        # Since ls fails, echo nothing shouldn't run
        self.assertNotIn("nothing", output)
        self.do_exit(child)

    def test_34_ls_and_echo_ok(self):
        """Test: ls && echo OK"""
        child = pexpect.spawn(f"{LSHELL} --config {CONFIG} --forbidden \"-['&']\"")
        child.expect(PROMPT)

        child.sendline("ls && echo OK")
        child.expect(PROMPT)

        output = child.before.decode("utf8").split("\n", 1)[1].strip()
        # ls succeeds, echo OK should run
        self.assertIn("OK", output)
        self.do_exit(child)

    def test_35_ls_non_existing_directory_or_echo_ok(self):
        """Test: ls non_existing_directory || echo OK"""
        child = pexpect.spawn(f"{LSHELL} --config {CONFIG} --forbidden \"-['|']\"")
        child.expect(PROMPT)

        child.sendline("ls non_existing_directory || echo OK")
        child.expect(PROMPT)

        output = child.before.decode("utf8").split("\n", 1)[1].strip()
        # ls fails, echo OK should run
        self.assertIn("OK", output)
        self.do_exit(child)

    def test_36_ls_or_echo_nothing(self):
        """Test: ls || echo nothing"""
        child = pexpect.spawn(f"{LSHELL} --config {CONFIG}")
        child.expect(PROMPT)

        child.sendline("ls || echo nothing")
        child.expect(PROMPT)

        output = child.before.decode("utf8").split("\n", 1)[1].strip()
        # ls succeeds, echo nothing should not run
        self.assertNotIn("nothing", output)
        self.do_exit(child)

    def test_41_multicmd_with_wrong_arg_should_fail(self):
        """F20 | Allowing 'echo asd': Test 'echo qwe' should fail"""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--allowed \"['echo asd']\""
        )
        child.expect(PROMPT)

        expected = "*** forbidden command: echo"

        child.sendline("echo qwe")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_42_multicmd_with_near_exact_arg_should_fail(self):
        """F41 | Allowing 'echo asd': Test 'echo asds' should fail"""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--allowed \"['echo asd']\""
        )
        child.expect(PROMPT)

        expected = "*** forbidden command: echo"

        child.sendline("echo asds")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_43_multicmd_without_arg_should_fail(self):
        """F42 | Allowing 'echo asd': Test 'echo' should fail"""
        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--allowed \"['echo asd']\""
        )
        child.expect(PROMPT)

        expected = "*** forbidden command: echo"

        child.sendline("echo")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_44_multicmd_asd_should_pass(self):
        """F43 | Allowing 'echo asd': Test 'echo asd' should pass"""

        child = pexpect.spawn(
            f"{LSHELL} " f"--config {CONFIG} " "--allowed \"['echo asd']\""
        )
        child.expect(PROMPT)

        expected = "asd"

        child.sendline("echo asd")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n")[1].strip()
        self.assertEqual(expected, result)
        self.do_exit(child)

    def test_45_pipeline_is_shell_compatible(self):
        """F45 | Pipeline should pass stdout between commands."""
        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} "
            "--forbidden \"-['|']\" --allowed \"+['printf', 'wc']\""
        )
        child.expect(PROMPT)

        child.sendline("printf foo | wc -c")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n", 1)[1].strip()
        self.assertEqual("3", result)
        self.do_exit(child)

    def test_46_redirection_is_shell_compatible(self):
        """F46 | Redirections should be handled by shell semantics."""
        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} --path \"['/tmp']\" "
            "--forbidden \"-['>','<','&']\" --allowed \"+['cat']\""
        )
        child.expect(PROMPT)

        child.sendline("ls does_not_exist >/tmp/lshell_redir_test 2>&1")
        child.expect(PROMPT)
        child.sendline("cat /tmp/lshell_redir_test")
        child.expect(PROMPT)
        result = child.before.decode("utf8").split("\n", 1)[1]
        self.assertIn("does_not_exist", result)
        self.do_exit(child)

    def test_68_interactive_seeded_fuzz_session(self):
        """F68 | Seeded interactive fuzzing should keep the shell responsive."""
        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} --strict 1 "
            "--forbidden \"[]\" "
            "--allowed \"+['printf','wc','cat','pwd','true','false','sleep']\""
        )
        rng = random.Random(6842)
        temp_file = f"/tmp/lshell_fuzz_{os.getpid()}_{rng.randint(1000, 9999)}.txt"
        payloads = [
            "alpha beta",
            "quoted  words",
            "tabs\tand\tspaces",
            "symbols !@#",
            "mix_'\"_chars",
        ]

        def assert_prompt_and_no_traceback():
            child.expect(PROMPT)
            output = child.before.decode("utf8", errors="replace")
            self.assertNotIn("Traceback (most recent call last)", output)
            self.assertNotIn("Exception:", output)
            self.assertNotIn("KeyboardInterrupt", output)
            return output

        try:
            child.expect(PROMPT)
            scripted_commands = [
                "help",
                "history",
                "pwd",
                "cd /tmp && pwd",
                "false || echo OR_BRANCH",
                "true && echo AND_BRANCH",
                f'echo "warmup" > {temp_file}',
                f'echo "alpha beta" >> {temp_file}',
                f"cat {temp_file}",
                "printf fuzz | wc -c",
                "echo 'First line' \\",
                "'Second line'",
                "echo 123 \\",
                "__CTRL_C__",
                'echo "unterminated',
                "__CTRL_C__",
                "jobs",
            ]

            for command in scripted_commands:
                if command == "__CTRL_C__":
                    child.sendcontrol("c")
                    assert_prompt_and_no_traceback()
                    continue
                child.sendline(command)
                if command.endswith("\\") or command.count('"') % 2 == 1:
                    child.expect(">")
                    continue
                output = assert_prompt_and_no_traceback()
                if command == "printf fuzz | wc -c":
                    self.assertIn("4", output)

            for _ in range(35):
                payload = rng.choice(payloads)
                safe_payload = payload.replace('"', '\\"')
                mode = rng.randrange(6)
                if mode == 0:
                    command = f'echo "{safe_payload}"'
                elif mode == 1:
                    command = f'printf "{safe_payload}" | wc -c'
                elif mode == 2:
                    command = f'true && echo "ok {safe_payload}"'
                elif mode == 3:
                    command = f'false || echo "recover {safe_payload}"'
                elif mode == 4:
                    command = f'echo "{safe_payload}" >> {temp_file}'
                else:
                    command = f"cat {temp_file}"

                child.sendline(command)
                assert_prompt_and_no_traceback()

            child.sendline(f"cat {temp_file}")
            output = assert_prompt_and_no_traceback()
            self.assertIn("warmup", output)
            self.assertIn("alpha beta", output)
            self.do_exit(child)
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            if child.isalive():
                child.close()

    def test_69_operator_matrix_fuzz(self):
        """F69 | Operator and expansion matrix should remain stable."""
        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} --strict 1 "
            "--forbidden \"[]\" "
            "--allowed \"+['printf','wc','cat','pwd','true','false']\""
        )
        temp_file = f"/tmp/lshell_matrix_{os.getpid()}.txt"

        def expect_clean_prompt():
            child.expect(PROMPT)
            output = child.before.decode("utf8", errors="replace")
            self.assertNotIn("Traceback (most recent call last)", output)
            self.assertNotIn("Exception:", output)
            return output

        try:
            child.expect(PROMPT)
            matrix = [
                ("echo MATRIX_START", ["MATRIX_START"]),
                ("echo 'a b c' | wc -w", ["3"]),
                ("printf matrix | wc -c", ["6"]),
                (f"echo one > {temp_file}", []),
                (f"echo two >> {temp_file}", []),
                (f"cat {temp_file}", ["one", "two"]),
                ("true && echo branch_true", ["branch_true"]),
                ("false || echo branch_false", ["branch_false"]),
                ("cd /tmp && pwd", ["/tmp"]),
                ("echo $(printf nested_ok)", ["nested_ok"]),
                ('NAME=ALPHA echo "$NAME"', ["ALPHA"]),
                ("echo ${HOME}", ["/"]),
            ]

            for command, expected_bits in matrix:
                child.sendline(command)
                output = expect_clean_prompt()
                for expected in expected_bits:
                    self.assertIn(expected, output)

            self.do_exit(child)
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            if child.isalive():
                child.close()

    def test_70_multiline_and_interrupt_storm(self):
        """F70 | Repeated multiline and Ctrl-C should recover cleanly."""
        child = pexpect.spawn(f"{LSHELL} --config {CONFIG} --strict 1 --forbidden \"[]\"")

        def expect_clean_prompt():
            child.expect(PROMPT)
            output = child.before.decode("utf8", errors="replace")
            self.assertNotIn("Traceback (most recent call last)", output)
            self.assertNotIn("Exception:", output)
            return output

        try:
            child.expect(PROMPT)
            for idx in range(10):
                child.sendline(f"echo iteration_{idx} \\")
                child.expect(">")
                if idx % 2 == 0:
                    child.sendcontrol("c")
                    expect_clean_prompt()
                else:
                    child.sendline(f'"tail_{idx}"')
                    output = expect_clean_prompt()
                    self.assertIn(f"iteration_{idx} tail_{idx}", output)

            child.sendline('echo "unterminated')
            child.expect(">")
            child.sendcontrol("c")
            expect_clean_prompt()

            child.sendline("echo AFTER_STORM")
            output = expect_clean_prompt()
            self.assertIn("AFTER_STORM", output)
            self.do_exit(child)
        finally:
            if child.isalive():
                child.close()

    def test_71_history_randomized_session_consistency(self):
        """F71 | History should retain randomized interactive command stream."""
        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} --strict 1 "
            "--forbidden \"[]\" "
            "--allowed \"+['printf','wc','pwd','true','false']\""
        )
        rng = random.Random(7101)
        executed_commands = []

        def expect_clean_prompt():
            child.expect(PROMPT)
            output = child.before.decode("utf8", errors="replace")
            self.assertNotIn("Traceback (most recent call last)", output)
            self.assertNotIn("Exception:", output)
            return output

        try:
            child.expect(PROMPT)
            command_pool = [
                "pwd",
                "true && echo HIST_TRUE",
                "false || echo HIST_FALSE",
                "echo plain_text",
                "printf abc | wc -c",
            ]
            for _ in range(25):
                command = rng.choice(command_pool)
                executed_commands.append(command)
                child.sendline(command)
                expect_clean_prompt()

            child.sendline("history")
            history_out = expect_clean_prompt()
            for command in executed_commands[-8:]:
                self.assertIn(command, history_out)

            self.do_exit(child)
        finally:
            if child.isalive():
                child.close()

    def test_72_background_job_lifecycle(self):
        """F72 | Background jobs should appear and then complete cleanly."""
        child = pexpect.spawn(
            f"{LSHELL} --config {CONFIG} --strict 1 "
            "--forbidden \"[]\" "
            "--allowed \"+['sleep']\""
        )

        def expect_clean_prompt():
            child.expect(PROMPT)
            output = child.before.decode("utf8", errors="replace")
            self.assertNotIn("Traceback (most recent call last)", output)
            self.assertNotIn("Exception:", output)
            return output

        try:
            child.expect(PROMPT)
            child.sendline("sleep 1 &")
            expect_clean_prompt()

            child.sendline("jobs")
            jobs_before = expect_clean_prompt()
            self.assertIn("sleep 1", jobs_before)

            child.sendline("sleep 2")
            expect_clean_prompt()

            child.sendline("jobs")
            jobs_after = expect_clean_prompt()
            self.assertNotIn("sleep 1", jobs_after)
            self.do_exit(child)
        finally:
            if child.isalive():
                child.close()
