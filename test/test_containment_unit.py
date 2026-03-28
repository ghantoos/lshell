"""Unit tests for runtime containment helpers."""

import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from lshell import containment
from lshell import utils
from lshell.config.runtime import CheckConfig


TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"


class TestContainmentConfigValidation(unittest.TestCase):
    """Validate max_sessions_per_user parsing and bounds."""

    base_args = [f"--config={CONFIG}", "--quiet=1"]

    def test_max_sessions_per_user_defaults_disabled(self):
        """Runtime containment keys should default to disabled mode."""
        conf = CheckConfig(self.base_args).returnconf()
        self.assertEqual(conf["max_sessions_per_user"], 0)
        self.assertEqual(conf["max_background_jobs"], 0)
        self.assertEqual(conf["command_timeout"], 0)

    def test_max_sessions_per_user_rejects_negative_values(self):
        """Runtime containment integer keys must be non-negative."""
        for key in containment.RUNTIME_LIMIT_INT_KEYS:
            with self.subTest(key=key):
                with self.assertRaises(SystemExit):
                    CheckConfig(self.base_args + [f"--{key}=-1"]).returnconf()


class TestSessionAccounting(unittest.TestCase):
    """Exercise session accounting limits and stale cleanup."""

    def _session_conf(self, session_id):
        return {
            "username": "testuser",
            "session_id": session_id,
            "max_sessions_per_user": 1,
        }

    def test_session_accounting_enforces_cap(self):
        """Second session should be denied when cap is reached."""
        with tempfile.TemporaryDirectory(prefix="lshell-session-unit-") as session_dir:
            with patch.dict(
                os.environ,
                {"LSHELL_SESSION_DIR": session_dir},
                clear=False,
            ):
                first = containment.SessionAccountant(self._session_conf("one"))
                first.acquire()

                second = containment.SessionAccountant(self._session_conf("two"))
                with self.assertRaises(containment.ContainmentViolation) as violation:
                    second.acquire()

                self.assertIn(
                    "runtime_limit.max_sessions_per_user_exceeded",
                    violation.exception.reason_code,
                )
                first.release()

    def test_session_accounting_cleans_stale_entries(self):
        """Dead PID records should be removed before counting active sessions."""
        with tempfile.TemporaryDirectory(prefix="lshell-session-unit-") as session_dir:
            with patch.dict(
                os.environ,
                {"LSHELL_SESSION_DIR": session_dir},
                clear=False,
            ):
                accountant = containment.SessionAccountant(self._session_conf("active"))
                os.makedirs(accountant.user_dir, exist_ok=True)
                stale_path = os.path.join(accountant.user_dir, "session-stale.json")
                with open(stale_path, "w", encoding="utf-8") as handle:
                    json.dump(
                        {
                            "pid": 999999,
                            "pid_start": "1",
                            "session_id": "stale",
                            "username": "testuser",
                        },
                        handle,
                    )

                accountant.acquire()
                self.assertFalse(os.path.exists(stale_path))
                accountant.release()


class TestRuntimeExecutionHelpers(unittest.TestCase):
    """Validate timeout helper behavior."""

    def test_exec_cmd_timeout_returns_124(self):
        """Foreground commands should be killed when command_timeout is exceeded."""
        conf = {
            "command_timeout": 1,
            "max_sessions_per_user": 0,
            "max_background_jobs": 0,
            "security_audit_json": 0,
        }
        started = time.monotonic()
        ret = utils.exec_cmd("sleep 2", conf=conf)
        elapsed = time.monotonic() - started

        self.assertEqual(ret, 124)
        self.assertLess(elapsed, 2.5)

    def test_apply_rlimits_applies_max_processes(self):
        """rlimit helper should apply max_processes via RLIMIT_NPROC."""

        class FakeResource:
            """Minimal resource-module stub capturing setrlimit calls."""

            RLIMIT_NPROC = 1

            def __init__(self):
                self.calls = []

            def setrlimit(self, key, value):
                """Record the requested resource limit tuple."""
                self.calls.append((key, value))

        fake_resource = FakeResource()
        limits = containment.RuntimeLimits(max_processes=10)
        unsupported = containment.apply_rlimits(limits, resource_module=fake_resource)

        self.assertEqual(unsupported, [])
        self.assertIn((FakeResource.RLIMIT_NPROC, (10, 10)), fake_resource.calls)

    def test_apply_rlimits_reports_unsupported_max_processes(self):
        """Missing RLIMIT_NPROC should be reported, not crash."""

        class MissingResource:
            """Resource stub without RLIMIT constants for unsupported-path tests."""

            def setrlimit(self, _key, _value):
                """Fail if called since no RLIMIT constants are exposed."""
                raise AssertionError("setrlimit should not be called without constants")

        limits = containment.RuntimeLimits(max_processes=1)
        unsupported = containment.apply_rlimits(
            limits,
            resource_module=MissingResource(),
        )

        self.assertIn("max_processes", unsupported)


if __name__ == "__main__":
    unittest.main()
