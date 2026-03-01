"""Unit tests for parser utilities and job-control built-ins."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from lshell import builtincmd
from lshell import completion
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
        """Return the configured poll status."""
        return self._poll_value

    def wait(self):
        """Mark the fake job as waited and return its final code."""
        self.wait_called = True
        self._poll_value = self.returncode
        return self.returncode


class FakeProcess:
    """Simple fake subprocess object used by exec_cmd signal tests."""

    def __init__(self, pid=12345, returncode=0, trigger_suspend=False):
        self.pid = pid
        self.returncode = returncode
        self.trigger_suspend = trigger_suspend
        self.lshell_cmd = ""
        self.args = ["tail", "-f", "blabla"]
        self._poll_value = None
        self._signal_handlers = {}

    def poll(self):
        """Report running state until the fake process completes."""
        return self._poll_value

    def communicate(self):
        """Simulate command execution, optionally triggering Ctrl+Z."""
        if self.trigger_suspend:
            handler = self._signal_handlers.get(utils.signal.SIGTSTP)
            if handler is not None:
                handler(utils.signal.SIGTSTP, None)
        self._poll_value = self.returncode


class TestParserUtilities(unittest.TestCase):
    """Tests for shell command parsing and env expansion helpers."""

    def test_split_command_sequence_keeps_quoted_operators(self):
        """Keep logical operators literal when they are inside quotes."""
        line = 'echo "a&&b||c" && echo done'
        self.assertEqual(utils.split_command_sequence(line), ['echo "a&&b||c"', "&&", "echo done"])

    def test_split_command_sequence_keeps_substitution_content(self):
        """Avoid splitting on operators located inside command substitution."""
        line = "echo $(printf '%s' 'a|b') | wc -c"
        self.assertEqual(
            utils.split_command_sequence(line),
            ["echo $(printf '%s' 'a|b')", "|", "wc -c"],
        )

    def test_split_command_sequence_rejects_unbalanced_quote(self):
        """Reject command lines with unmatched quotes."""
        self.assertIsNone(utils.split_command_sequence('echo "unterminated'))

    def test_split_command_sequence_does_not_split_redirection_ampersand(self):
        """Keep redirection forms like 2>&1 in the same command token."""
        line = "echo hi >/tmp/out 2>&1"
        self.assertEqual(utils.split_command_sequence(line), [line])

    @patch.dict(os.environ, {"A": "VALUE_A", "B": "VALUE_B"}, clear=False)
    def test_expand_vars_quoted_respects_single_quotes(self):
        """Expand variables except those protected by single quotes."""
        line = "echo $A '$A' \"$B\" ${A}"
        self.assertEqual(
            utils.expand_vars_quoted(line),
            "echo VALUE_A '$A' \"VALUE_B\" VALUE_A",
        )

    def test_parse_command_extracts_assignments_and_command(self):
        """Split assignments from executable and arguments."""
        executable, argument, split, assignments = utils._parse_command(
            "A=1 B=two echo hello world"
        )
        self.assertEqual(executable, "echo")
        self.assertEqual(argument, "hello world")
        self.assertEqual(split, ["A=1", "B=two", "echo", "hello", "world"])
        self.assertEqual(assignments, [("A", "1"), ("B", "two")])

    def test_parse_command_assignment_only(self):
        """Handle assignment-only input with no executable command."""
        executable, argument, split, assignments = utils._parse_command("A=1 B=two")
        self.assertEqual(executable, "")
        self.assertEqual(argument, "")
        self.assertEqual(split, ["A=1", "B=two"])
        self.assertEqual(assignments, [("A", "1"), ("B", "two")])

    def test_complete_list_dir_filters_by_prefix(self):
        """List completion should only return entries matching the typed prefix."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.mkdir(os.path.join(tmpdir, "blipdir"))
            open(os.path.join(tmpdir, "blabla"), "w", encoding="utf-8").close()
            open(os.path.join(tmpdir, "alpha"), "w", encoding="utf-8").close()
            conf = {"home_path": tmpdir, "path": ["", ""]}
            with patch("lshell.completion.os.getcwd", return_value=tmpdir), patch(
                "lshell.completion.sec.check_path", return_value=(0, conf)
            ):
                result = completion.complete_list_dir(
                    conf, "bl", "tail -f bl", 8, 10
                )

        self.assertIn("blipdir/", result)
        self.assertIn("blabla ", result)
        self.assertNotIn("alpha ", result)

    def test_complete_list_dir_filters_for_prefixed_path(self):
        """Completion should filter basenames when the token includes a directory path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.mkdir(os.path.join(tmpdir, "blipdir"))
            open(os.path.join(tmpdir, "blabla"), "w", encoding="utf-8").close()
            open(os.path.join(tmpdir, "beta"), "w", encoding="utf-8").close()
            token = os.path.join(tmpdir, "bl")
            line = f"tail -f {token}"
            begidx = line.rfind(token)
            endidx = len(line)
            conf = {"home_path": tmpdir, "path": ["", ""]}
            with patch("lshell.completion.sec.check_path", return_value=(0, conf)):
                result = completion.complete_list_dir(
                    conf, token, line, begidx, endidx
                )

        self.assertIn("blipdir/", result)
        self.assertIn("blabla ", result)
        self.assertNotIn("beta ", result)

    def test_complete_list_dir_empty_token_lists_current_directory(self):
        """Trailing-space completion should list all entries in the working directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.mkdir(os.path.join(tmpdir, "lshell"))
            open(os.path.join(tmpdir, "bla"), "w", encoding="utf-8").close()
            open(os.path.join(tmpdir, "blabla"), "w", encoding="utf-8").close()
            open(os.path.join(tmpdir, "123"), "w", encoding="utf-8").close()
            conf = {"home_path": tmpdir, "path": ["", ""]}
            with patch("lshell.completion.os.getcwd", return_value=tmpdir), patch(
                "lshell.completion.sec.check_path", return_value=(0, conf)
            ):
                result = completion.complete_list_dir(
                    conf, "", "tail -f ", 8, 8
                )

        self.assertIn("lshell/", result)
        self.assertIn("bla ", result)
        self.assertIn("blabla ", result)
        self.assertIn("123 ", result)

    def test_complete_list_dir_subdirectory_with_empty_text(self):
        """Slash-delimited completion should list entries from the selected subdirectory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = os.path.join(tmpdir, "lshell")
            os.mkdir(subdir)
            open(os.path.join(subdir, "README.md"), "w", encoding="utf-8").close()
            os.mkdir(os.path.join(subdir, "test"))
            open(os.path.join(tmpdir, ".bashrc"), "w", encoding="utf-8").close()
            conf = {"home_path": tmpdir, "path": ["", ""]}
            line = "tail -f lshell/"
            begidx = len(line)
            endidx = len(line)
            with patch("lshell.completion.os.getcwd", return_value=tmpdir), patch(
                "lshell.completion.sec.check_path", return_value=(0, conf)
            ):
                result = completion.complete_list_dir(conf, "", line, begidx, endidx)

        self.assertIn("README.md ", result)
        self.assertIn("test/", result)
        self.assertNotIn(".bashrc ", result)

    def test_complete_list_dir_subdirectory_prefix_completion(self):
        """Path-prefix completion should resolve candidates from the subdirectory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = os.path.join(tmpdir, "lshell")
            os.mkdir(subdir)
            os.mkdir(os.path.join(subdir, "rpm"))
            os.mkdir(os.path.join(subdir, "source"))
            open(os.path.join(subdir, "README.md"), "w", encoding="utf-8").close()
            conf = {"home_path": tmpdir, "path": ["", ""]}
            line = "tail -f lshell/rp"
            begidx = len("tail -f lshell/")
            endidx = len(line)
            with patch("lshell.completion.os.getcwd", return_value=tmpdir), patch(
                "lshell.completion.sec.check_path", return_value=(0, conf)
            ):
                result = completion.complete_list_dir(conf, "rp", line, begidx, endidx)

        self.assertEqual(result, ["rpm/"])

    def test_complete_list_dir_returns_empty_when_path_denied(self):
        """Denied paths should return an empty completion list."""
        conf = {"home_path": "/tmp", "path": ["", ""]}
        with patch(
            "lshell.completion.sec.check_path", return_value=(1, conf)
        ), patch("lshell.completion.os.getcwd", return_value="/tmp"):
            result = completion.complete_list_dir(conf, "bl", "tail -f bl", 8, 10)

        self.assertEqual(result, [])


class TestBuiltinsJobsAndSource(unittest.TestCase):
    """Tests for built-in commands around source and job control."""

    def setUp(self):
        """Save and clear global background job state before each test."""
        self._previous_jobs = list(builtincmd.BACKGROUND_JOBS)
        builtincmd.BACKGROUND_JOBS.clear()

    def tearDown(self):
        """Restore global background job state after each test."""
        builtincmd.BACKGROUND_JOBS.clear()
        builtincmd.BACKGROUND_JOBS.extend(self._previous_jobs)

    @patch.dict(os.environ, {}, clear=True)
    def test_cmd_source_loads_exported_values(self):
        """Load exported entries from a source file into the environment."""
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
        """Return an error and stderr message when the source file is missing."""
        missing = "/tmp/lshell_missing_source_file"
        if os.path.exists(missing):
            os.remove(missing)
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.assertEqual(builtincmd.cmd_source(missing), 1)
        self.assertIn("ERROR: Unable to read environment file", stderr.getvalue())

    def test_cmd_bg_fg_no_jobs(self):
        """Report failure when attempting fg with no jobs queued."""
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            ret = builtincmd.cmd_bg_fg("fg", "")
        self.assertEqual(ret, 1)
        self.assertIn("no such job", stdout.getvalue())

    def test_cmd_bg_fg_invalid_job_id(self):
        """Reject non-numeric fg job identifiers."""
        builtincmd.BACKGROUND_JOBS.append(FakeJob())
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            ret = builtincmd.cmd_bg_fg("fg", "abc")
        self.assertEqual(ret, 1)
        self.assertIn("Invalid job ID.", stdout.getvalue())

    @patch("os.getpgid", return_value=4242)
    @patch("os.killpg")
    def test_cmd_bg_fg_resumes_and_removes_job(self, mock_killpg, _mock_getpgid):
        """Resume a running job in foreground and remove it once completed."""
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

    @patch("lshell.builtincmd.os.getpgid", return_value=4242)
    @patch("lshell.builtincmd.os.killpg")
    def test_cmd_bg_fg_ctrl_z_keeps_single_job_entry(self, mock_killpg, _mock_getpgid):
        """Ctrl+Z during fg should not duplicate the same job or raise."""
        job = FakeJob(poll_value=None, returncode=0, pid=9876, cmd="tail -f blabla")
        builtincmd.BACKGROUND_JOBS.append(job)
        stdout = io.StringIO()
        handlers = {}

        def fake_signal(signum, handler):
            handlers[signum] = handler
            return None

        def trigger_ctrl_z():
            job.wait_called = True
            handlers[utils.signal.SIGTSTP](utils.signal.SIGTSTP, None)

        job.wait = trigger_ctrl_z

        with patch("lshell.builtincmd.signal.getsignal", return_value=None), patch(
            "lshell.builtincmd.signal.signal", side_effect=fake_signal
        ):
            with redirect_stdout(stdout):
                ret = builtincmd.cmd_bg_fg("fg", "1")

        self.assertEqual(ret, 0)
        self.assertTrue(job.wait_called)
        self.assertEqual(len(builtincmd.BACKGROUND_JOBS), 1)
        self.assertIn("Stopped", stdout.getvalue())
        self.assertEqual(mock_killpg.call_count, 2)

    @patch("lshell.utils.os.getpgid", return_value=4242)
    @patch("lshell.utils.os.killpg")
    def test_exec_cmd_ctrl_z_restores_handlers_and_deduplicates_job(
        self, _mock_killpg, _mock_getpgid
    ):
        """exec_cmd should restore original handlers and avoid duplicate job entries."""
        fake_proc = FakeProcess(pid=9876, trigger_suspend=True)
        builtincmd.BACKGROUND_JOBS.append(fake_proc)
        signal_handlers = {}
        initial_sigtstp = object()
        initial_sigcont = object()

        def fake_getsignal(signum):
            if signum == utils.signal.SIGTSTP:
                return initial_sigtstp
            if signum == utils.signal.SIGCONT:
                return initial_sigcont
            return None

        def fake_signal(signum, handler):
            signal_handlers[signum] = handler
            return None

        fake_proc._signal_handlers = signal_handlers
        with patch("lshell.utils.signal.getsignal", side_effect=fake_getsignal), patch(
            "lshell.utils.signal.signal", side_effect=fake_signal
        ), patch("lshell.utils.subprocess.Popen", return_value=fake_proc):
            ret = utils.exec_cmd("tail -f blabla")

        self.assertEqual(ret, 0)
        self.assertEqual(len(builtincmd.BACKGROUND_JOBS), 1)
        self.assertIs(signal_handlers[utils.signal.SIGTSTP], initial_sigtstp)
        self.assertIs(signal_handlers[utils.signal.SIGCONT], initial_sigcont)

    def test_cmd_jobs_displays_symbols(self):
        """Render job list with expected current and previous markers."""
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
        """Drop completed jobs and print completion status."""
        builtincmd.BACKGROUND_JOBS.append(
            FakeJob(poll_value=0, returncode=0, cmd="sleep 1")
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            builtincmd.check_background_jobs()

        self.assertEqual(len(builtincmd.BACKGROUND_JOBS), 0)
        self.assertIn("Done", stdout.getvalue())

    def test_check_background_jobs_suppresses_user_interrupted_job_message(self):
        """Do not print completion output for user-interrupted jobs."""
        builtincmd.BACKGROUND_JOBS.append(
            FakeJob(poll_value=130, returncode=-2, cmd="sleep 1")
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            builtincmd.check_background_jobs()

        self.assertEqual(len(builtincmd.BACKGROUND_JOBS), 0)
        self.assertEqual(stdout.getvalue(), "")

    def test_check_background_jobs_prunes_all_completed_entries(self):
        """Completed jobs should all be removed without skipping entries."""
        builtincmd.BACKGROUND_JOBS.extend(
            [
                FakeJob(poll_value=0, returncode=0, cmd="sleep 1"),
                FakeJob(poll_value=1, returncode=1, cmd="sleep 2"),
                FakeJob(poll_value=0, returncode=0, cmd="sleep 3"),
            ]
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            builtincmd.check_background_jobs()

        self.assertEqual(len(builtincmd.BACKGROUND_JOBS), 0)
        output = stdout.getvalue()
        self.assertEqual(output.count("Done"), 2)
        self.assertEqual(output.count("Failed"), 1)

    def test_jobs_prunes_finished_and_reindexes_running(self):
        """jobs() should drop non-running jobs and reindex active ones from 1."""
        builtincmd.BACKGROUND_JOBS.extend(
            [
                FakeJob(poll_value=0, returncode=0, cmd="done job"),
                FakeJob(poll_value=1, returncode=1, cmd="failed job"),
                FakeJob(poll_value=None, returncode=0, cmd="running job"),
            ]
        )

        joblist = builtincmd.jobs()

        self.assertEqual(joblist, [[1, "Stopped", "running job"]])
        self.assertEqual(len(builtincmd.BACKGROUND_JOBS), 1)
        self.assertEqual(builtincmd.BACKGROUND_JOBS[0].lshell_cmd, "running job")
