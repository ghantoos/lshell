"""Unit tests for parser utilities and job-control built-ins."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from lshell import builtincmd
from lshell import utils


class FakeJob:
    """Simple fake subprocess object for background job tests."""

    def __init__(self, poll_value=None, returncode=0, pid=12345, args=None, cmd=None):
        self._poll_value = poll_value
        self.returncode = returncode
        self.pid = pid
        self.args = args or ["sleep", "60"]
        self.lshell_cmd = cmd or "sleep 60"
        self.wait_called = False

    def poll(self):
        return self._poll_value

    def wait(self):
        self.wait_called = True
        self._poll_value = self.returncode
        return self.returncode


class TestParserUtilities(unittest.TestCase):
    """Tests for shell command parsing and env expansion helpers."""

    def test_split_command_sequence_keeps_quoted_operators(self):
        line = 'echo "a&&b||c" && echo done'
        self.assertEqual(utils.split_command_sequence(line), ['echo "a&&b||c"', "&&", "echo done"])

    def test_split_command_sequence_keeps_substitution_content(self):
        line = "echo $(printf '%s' 'a|b') | wc -c"
        self.assertEqual(
            utils.split_command_sequence(line),
            ["echo $(printf '%s' 'a|b')", "|", "wc -c"],
        )

    def test_split_command_sequence_rejects_unbalanced_quote(self):
        self.assertIsNone(utils.split_command_sequence('echo "unterminated'))

    def test_split_command_sequence_does_not_split_redirection_ampersand(self):
        line = "echo hi >/tmp/out 2>&1"
        self.assertEqual(utils.split_command_sequence(line), [line])

    @patch.dict(os.environ, {"A": "VALUE_A", "B": "VALUE_B"}, clear=False)
    def test_expand_vars_quoted_respects_single_quotes(self):
        line = "echo $A '$A' \"$B\" ${A}"
        self.assertEqual(
            utils.expand_vars_quoted(line),
            "echo VALUE_A '$A' \"VALUE_B\" VALUE_A",
        )

    def test_parse_command_extracts_assignments_and_command(self):
        executable, argument, split, assignments = utils._parse_command(
            "A=1 B=two echo hello world"
        )
        self.assertEqual(executable, "echo")
        self.assertEqual(argument, "hello world")
        self.assertEqual(split, ["A=1", "B=two", "echo", "hello", "world"])
        self.assertEqual(assignments, [("A", "1"), ("B", "two")])

    def test_parse_command_assignment_only(self):
        executable, argument, split, assignments = utils._parse_command("A=1 B=two")
        self.assertEqual(executable, "")
        self.assertEqual(argument, "")
        self.assertEqual(split, ["A=1", "B=two"])
        self.assertEqual(assignments, [("A", "1"), ("B", "two")])


class TestBuiltinsJobsAndSource(unittest.TestCase):
    """Tests for built-in commands around source and job control."""

    def setUp(self):
        self._previous_jobs = list(builtincmd.BACKGROUND_JOBS)
        builtincmd.BACKGROUND_JOBS.clear()

    def tearDown(self):
        builtincmd.BACKGROUND_JOBS.clear()
        builtincmd.BACKGROUND_JOBS.extend(self._previous_jobs)

    @patch.dict(os.environ, {}, clear=True)
    def test_cmd_source_loads_exported_values(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as env_file:
            env_file.write("export FIRST=one\n")
            env_file.write("NOPE=ignore\n")
            env_file.write("export SECOND='two_words'\n")
            file_path = env_file.name

        try:
            self.assertEqual(builtincmd.cmd_source(file_path), 0)
            self.assertEqual(os.environ.get("FIRST"), "one")
            self.assertIsNone(os.environ.get("NOPE"))
            self.assertEqual(os.environ.get("SECOND"), "two_words")
        finally:
            os.remove(file_path)

    def test_cmd_source_missing_file_returns_error(self):
        missing = "/tmp/lshell_missing_source_file"
        if os.path.exists(missing):
            os.remove(missing)
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.assertEqual(builtincmd.cmd_source(missing), 1)
        self.assertIn("ERROR: Unable to read environment file", stderr.getvalue())

    def test_cmd_bg_fg_no_jobs(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            ret = builtincmd.cmd_bg_fg("fg", "")
        self.assertEqual(ret, 1)
        self.assertIn("no such job", stdout.getvalue())

    def test_cmd_bg_fg_invalid_job_id(self):
        builtincmd.BACKGROUND_JOBS.append(FakeJob())
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            ret = builtincmd.cmd_bg_fg("fg", "abc")
        self.assertEqual(ret, 1)
        self.assertIn("Invalid job ID.", stdout.getvalue())

    @patch("os.getpgid", return_value=4242)
    @patch("os.killpg")
    def test_cmd_bg_fg_resumes_and_removes_job(self, mock_killpg, _mock_getpgid):
        job = FakeJob(poll_value=None, returncode=0, pid=9876, cmd="sleep 10")
        builtincmd.BACKGROUND_JOBS.append(job)
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            ret = builtincmd.cmd_bg_fg("fg", "1")

        self.assertEqual(ret, 0)
        self.assertTrue(job.wait_called)
        self.assertEqual(len(builtincmd.BACKGROUND_JOBS), 0)
        self.assertIn("sleep 10", stdout.getvalue())
        mock_killpg.assert_called_once()

    def test_cmd_jobs_displays_symbols(self):
        builtincmd.BACKGROUND_JOBS.extend(
            [
                FakeJob(poll_value=None, cmd="sleep 1"),
                FakeJob(poll_value=None, cmd="sleep 2"),
                FakeJob(poll_value=None, cmd="sleep 3"),
            ]
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            ret = builtincmd.cmd_jobs()

        self.assertEqual(ret, 0)
        output = stdout.getvalue()
        self.assertIn("[1]   Stopped        sleep 1", output)
        self.assertIn("[2]-  Stopped        sleep 2", output)
        self.assertIn("[3]+  Stopped        sleep 3", output)

    def test_check_background_jobs_removes_completed_job(self):
        builtincmd.BACKGROUND_JOBS.append(
            FakeJob(poll_value=0, returncode=0, cmd="sleep 1")
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            builtincmd.check_background_jobs()

        self.assertEqual(len(builtincmd.BACKGROUND_JOBS), 0)
        self.assertIn("Done", stdout.getvalue())

    def test_check_background_jobs_suppresses_user_interrupted_job_message(self):
        builtincmd.BACKGROUND_JOBS.append(
            FakeJob(poll_value=130, returncode=-2, cmd="sleep 1")
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            builtincmd.check_background_jobs()

        self.assertEqual(len(builtincmd.BACKGROUND_JOBS), 0)
        self.assertEqual(stdout.getvalue(), "")
