"""Security regression coverage for the canonical engine."""

import os
import tempfile
import unittest

from lshell.config.runtime import CheckConfig
from lshell import utils
from lshell.engine import authorizer
from lshell.engine import reasons

TOPDIR = f"{os.path.dirname(os.path.realpath(__file__))}/../"
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"


class DummyLog:
    """Minimal logger stub for command execution tests."""

    def critical(self, _message):
        """Discard critical log writes in unit tests."""
        return None

    def error(self, _message):
        """Discard error log writes in unit tests."""
        return None


class DummyShellContext:
    """Minimal shell context consumed by utils.cmd_parse_execute."""

    def __init__(self, conf):
        self.conf = conf
        self.log = DummyLog()


class TestEngineSecurityRegressions(unittest.TestCase):
    """Regression tests for parser smuggling/substitution/path ACL edges."""

    args = [f"--config={CONFIG}", "--quiet=1"]

    def _policy(self, **overrides):
        policy = {
            "allowed": ["echo", "cd", "ls", "sudo"],
            "forbidden": [],
            "strict": 0,
            "sudo_commands": ["ls"],
            "allowed_file_extensions": [],
            "path": ["/|", ""],
        }
        policy.update(overrides)
        return policy

    def test_smuggling_invalid_operator_chain_is_denied(self):
        """Malformed operator smuggling should fail closed."""
        decision = authorizer.authorize_line(
            "echo ok ||| echo pwn",
            self._policy(),
            mode="policy",
            check_current_dir=False,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason.code, reasons.UNKNOWN_SYNTAX)

    def test_substitution_denied_when_inner_command_not_allowlisted(self):
        """Nested substitution should enforce inner command allow-list."""
        decision = authorizer.authorize_line(
            "echo $(cat /etc/passwd)",
            self._policy(allowed=["echo"], strict=0),
            mode="policy",
            check_current_dir=False,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason.code, reasons.UNKNOWN_SYNTAX)

    def test_braced_substitution_forbidden_token_blocks_line(self):
        """Forbidden '${' token should block braced substitutions."""
        decision = authorizer.authorize_line(
            "echo ${HOME}",
            self._policy(forbidden=["${"], allowed=["echo"]),
            mode="policy",
            check_current_dir=False,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason.code, reasons.FORBIDDEN_CHARACTER)

    def test_path_specific_allow_beats_broader_deny(self):
        """Path ACL specificity must preserve /var deny + /var/log allow behavior."""
        policy = self._policy(
            path=["/|/var/log|", "/var|"],
            allowed=["cd"],
        )

        allowed_decision = authorizer.authorize_line(
            "cd /var/log",
            policy,
            mode="policy",
            check_current_dir=False,
        )
        denied_decision = authorizer.authorize_line(
            "cd /var/tmp",
            policy,
            mode="policy",
            check_current_dir=False,
        )

        self.assertTrue(allowed_decision.allowed)
        self.assertFalse(denied_decision.allowed)
        self.assertEqual(denied_decision.reason.code, reasons.FORBIDDEN_PATH)

    def test_authorizer_blocks_bareword_symlink_operand_for_cat(self):
        """Canonical authorizer must deny bareword symlinks escaping allowed roots."""
        previous_cwd = os.getcwd()
        try:
            with tempfile.TemporaryDirectory(prefix="lshell-engine-symlink-", dir="/tmp") as tmpdir:
                link_path = os.path.join(tmpdir, "passwdlink")
                os.symlink("/etc/passwd", link_path)
                os.chdir(tmpdir)

                decision = authorizer.authorize_line(
                    "cat passwdlink",
                    self._policy(
                        allowed=["cat"],
                        strict=1,
                        path=[f"{tmpdir}|", ""],
                    ),
                    mode="policy",
                    check_current_dir=False,
                )

                self.assertFalse(decision.allowed)
                self.assertEqual(decision.reason.code, reasons.FORBIDDEN_PATH)
        finally:
            os.chdir(previous_cwd)

    def test_authorizer_blocks_bareword_symlink_operand_for_text_filters(self):
        """Canonical authorizer must deny filter file operands escaping allowed roots."""
        previous_cwd = os.getcwd()
        try:
            with tempfile.TemporaryDirectory(prefix="lshell-engine-filter-", dir="/tmp") as tmpdir:
                link_path = os.path.join(tmpdir, "passwdlink")
                os.symlink("/etc/passwd", link_path)
                os.chdir(tmpdir)

                for command in (
                    "awk 1 passwdlink",
                    "awk -f passwdlink",
                    "sed -n 1p passwdlink",
                    "sed -f passwdlink",
                    "sort passwdlink",
                ):
                    with self.subTest(command=command):
                        decision = authorizer.authorize_line(
                            command,
                            self._policy(
                                allowed=["awk", "sed", "sort"],
                                strict=1,
                                path=[f"{tmpdir}|", ""],
                            ),
                            mode="policy",
                            check_current_dir=False,
                        )

                        self.assertFalse(decision.allowed)
                        self.assertEqual(decision.reason.code, reasons.FORBIDDEN_PATH)
        finally:
            os.chdir(previous_cwd)

    def test_runtime_blocks_forbidden_env_assignment(self):
        """Runtime should keep forbidden env-assignment protection."""
        conf = CheckConfig(self.args + ["--forbidden=[]", "--strict=0"]).returnconf()
        shell = DummyShellContext(conf)

        original = os.environ.get("LD_PRELOAD")
        try:
            retcode = utils.cmd_parse_execute(
                "LD_PRELOAD=/tmp/evil.so",
                shell_context=shell,
            )
        finally:
            if original is None:
                os.environ.pop("LD_PRELOAD", None)
            else:
                os.environ["LD_PRELOAD"] = original

        self.assertEqual(retcode, 126)


if __name__ == "__main__":
    unittest.main()
