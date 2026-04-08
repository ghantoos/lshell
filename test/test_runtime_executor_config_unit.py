"""Unit tests for runtime executor configuration and trusted bash resolver."""

import os
import unittest
from unittest.mock import patch

from lshell.config.runtime import CheckConfig
from lshell import utils

TOPDIR = f"{os.path.dirname(os.path.realpath(__file__))}/../"
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"


class TestRuntimeExecutorConfig(unittest.TestCase):
    """Validate runtime_executor configuration semantics."""

    args = [f"--config={CONFIG}", "--quiet=1"]

    def test_shellless_defaults_are_fail_closed(self):
        """Default runtime config should stay shellless."""
        conf = CheckConfig(self.args).returnconf()
        self.assertEqual(conf["runtime_executor"], "shellless")

    def test_runtime_executor_accepts_bash_compat(self):
        """bash_compat should be accepted as an explicit mode."""
        conf = CheckConfig(self.args + ["--runtime_executor=bash_compat"]).returnconf()
        self.assertEqual(conf["runtime_executor"], "bash_compat")

    def test_runtime_executor_rejects_unknown_value(self):
        """runtime_executor must be one of the supported values."""
        with self.assertRaises(SystemExit):
            CheckConfig(self.args + ["--runtime_executor=unknown_mode"]).returnconf()


class TestTrustedBashResolver(unittest.TestCase):
    """Trusted bash resolver must only accept absolute executable candidates."""

    def test_resolver_ignores_non_absolute_candidates(self):
        """Relative bash candidate names must never be trusted."""
        with (
            patch("lshell.utils.os.path.isfile", return_value=True),
            patch("lshell.utils.os.access", return_value=True),
        ):
            self.assertIsNone(utils.resolve_trusted_bash_path(("bash",)))

    def test_resolver_returns_first_executable_absolute_candidate(self):
        """Resolver should pick the first matching absolute candidate."""
        with (
            patch(
                "lshell.utils.os.path.isfile",
                side_effect=lambda path: path == "/bin/bash",
            ),
            patch("lshell.utils.os.access", return_value=True),
        ):
            resolved = utils.resolve_trusted_bash_path(
                ("bash", "/bin/bash", "/usr/bin/bash")
            )
        self.assertEqual(resolved, "/bin/bash")


if __name__ == "__main__":
    unittest.main()
