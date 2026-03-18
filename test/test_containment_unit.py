"""Unit tests for runtime containment helpers."""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from lshell import containment
from lshell.checkconfig import CheckConfig


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


if __name__ == "__main__":
    unittest.main()
