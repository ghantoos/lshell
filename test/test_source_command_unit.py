"""Unit tests for the source built-in command."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from lshell import builtincmd
from lshell.config.runtime import CheckConfig

TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SOURCE_FIXTURE = f"{TOPDIR}/test/testfiles/source_command_fixture.lsh"
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"


class TestSourceCommand(unittest.TestCase):
    """Tests for sourcing environment files into the current shell context."""

    def test_source_is_not_enabled_by_default(self):
        """Default allowed builtins should not expose source implicitly."""
        conf = CheckConfig([f"--config={CONFIG}", "--quiet=1"]).returnconf()
        self.assertNotIn("source", conf["allowed"])

    @patch.dict(os.environ, {}, clear=True)
    def test_cmd_source_loads_fixture_exports(self):
        """Load exported values from a checked-in source fixture."""
        self.assertEqual(builtincmd.cmd_source(SOURCE_FIXTURE), 0)
        self.assertEqual(os.environ.get("SOURCE_SIMPLE"), "value")
        self.assertEqual(os.environ.get("SOURCE_SINGLE_QUOTED"), "two words")
        self.assertEqual(os.environ.get("SOURCE_DOUBLE_QUOTED"), "hello world")
        self.assertEqual(os.environ.get("SOURCE_EMPTY"), "")
        self.assertEqual(os.environ.get("SOURCE_WITH_EQUALS"), "a=b=c")
        self.assertIsNone(os.environ.get("IGNORED_ASSIGNMENT"))

    def test_cmd_source_missing_file_returns_error(self):
        """Return an error and stderr message when the source file is missing."""
        missing = "/tmp/lshell_missing_source_file"
        if os.path.exists(missing):
            os.remove(missing)
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.assertEqual(builtincmd.cmd_source(missing), 1)
        self.assertIn("lshell: unable to read environment file", stderr.getvalue())

    @patch.dict(os.environ, {}, clear=True)
    def test_cmd_source_preserves_quoted_values_with_spaces(self):
        """Load quoted export values without truncating them at the first space."""
        with tempfile.NamedTemporaryFile("w", delete=False) as env_file:
            env_file.write('export GREETING="hello world"\n')
            env_file.write("export TARGET='two words here'\n")
            file_path = env_file.name

        try:
            self.assertEqual(builtincmd.cmd_source(file_path), 0)
            self.assertEqual(os.environ.get("GREETING"), "hello world")
            self.assertEqual(os.environ.get("TARGET"), "two words here")
        finally:
            os.remove(file_path)

    @patch.dict(os.environ, {}, clear=True)
    def test_cmd_source_blocks_bash_function_import_exports(self):
        """Reject BASH_FUNC_* exports sourced from files."""
        with tempfile.NamedTemporaryFile("w", delete=False) as env_file:
            env_file.write("export BASH_FUNC_echo%%='() { id; }'\n")
            file_path = env_file.name

        stderr = io.StringIO()
        try:
            with redirect_stderr(stderr):
                self.assertEqual(builtincmd.cmd_source(file_path), 1)
            self.assertIn(
                "lshell: forbidden environment variable: BASH_FUNC_echo%%",
                stderr.getvalue(),
            )
            self.assertIsNone(os.environ.get("BASH_FUNC_echo%%"))
        finally:
            os.remove(file_path)

    @patch.dict(os.environ, {}, clear=True)
    def test_cmd_source_expands_tilde_paths(self):
        """Resolve home-relative source paths the same way the shell does."""
        with tempfile.TemporaryDirectory(dir=".") as home_dir:
            file_path = os.path.join(home_dir, ".lshell_env")
            with open(file_path, "w", encoding="utf-8") as env_file:
                env_file.write("export HOME_SCOPED=value\n")

            with patch.dict(os.environ, {"HOME": home_dir}, clear=True):
                self.assertEqual(builtincmd.cmd_source("~/.lshell_env"), 0)
                self.assertEqual(os.environ.get("HOME_SCOPED"), "value")

    @patch.dict(os.environ, {}, clear=True)
    def test_cmd_source_expands_environment_variable_paths(self):
        """Resolve $VARNAME paths before opening env source files."""
        with tempfile.TemporaryDirectory(dir=".") as home_dir:
            file_path = os.path.join(home_dir, ".lshell_env")
            with open(file_path, "w", encoding="utf-8") as env_file:
                env_file.write("export ENV_SCOPED=value\n")

            with patch.dict(
                os.environ,
                {"HOME": home_dir, "ENV_FILE_PATH": file_path},
                clear=True,
            ):
                self.assertEqual(builtincmd.cmd_source("$ENV_FILE_PATH"), 0)
                self.assertEqual(os.environ.get("ENV_SCOPED"), "value")

    @patch.dict(os.environ, {}, clear=True)
    def test_cmd_source_rejects_forbidden_environment_variables(self):
        """Dangerous environment variables must be rejected when sourcing files."""
        with tempfile.NamedTemporaryFile("w", delete=False) as env_file:
            env_file.write("export SHELLOPTS=xtrace\n")
            file_path = env_file.name

        stderr = io.StringIO()
        try:
            with redirect_stderr(stderr):
                self.assertEqual(builtincmd.cmd_source(file_path), 1)
            self.assertIsNone(os.environ.get("SHELLOPTS"))
            self.assertIn(
                "lshell: forbidden environment variable: SHELLOPTS",
                stderr.getvalue(),
            )
        finally:
            os.remove(file_path)


if __name__ == "__main__":
    unittest.main()
