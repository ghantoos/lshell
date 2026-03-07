"""Unit tests for the source built-in command."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from lshell import builtincmd

TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SOURCE_FIXTURE = f"{TOPDIR}/test/testfiles/source_command_fixture.lsh"


class TestSourceCommand(unittest.TestCase):
    """Tests for sourcing environment files into the current shell context."""

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
    def test_cmd_source_expands_tilde_paths(self):
        """Resolve home-relative source paths the same way the shell does."""
        with tempfile.TemporaryDirectory(dir=".") as home_dir:
            file_path = os.path.join(home_dir, ".lshell_env")
            with open(file_path, "w", encoding="utf-8") as env_file:
                env_file.write("export HOME_SCOPED=value\n")

            with patch.dict(os.environ, {"HOME": home_dir}, clear=True):
                self.assertEqual(builtincmd.cmd_source("~/.lshell_env"), 0)
                self.assertEqual(os.environ.get("HOME_SCOPED"), "value")


if __name__ == "__main__":
    unittest.main()
