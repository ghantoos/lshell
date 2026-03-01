"""Functional security-hardening tests for script-mode execution."""

import os
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest

TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"
LSHELL = f"{TOPDIR}/bin/lshell"


class TestSecurityHardeningFunctional(unittest.TestCase):
    """Functional tests for attack-oriented script execution scenarios."""

    def _run_lsh_script(self, script_body, extra_shell_args=""):
        """Run a temporary .lsh script and return subprocess.CompletedProcess."""
        with tempfile.TemporaryDirectory(prefix="lshell-hardening-") as tempdir:
            wrapper_path = os.path.join(tempdir, "wrapper.sh")
            script_path = os.path.join(tempdir, "attack_case.lsh")

            wrapper = textwrap.dedent(
                f"""\
                #!/bin/sh
                exec "{LSHELL}" --config "{CONFIG}" {extra_shell_args} "$@"
                """
            )
            with open(wrapper_path, "w", encoding="utf-8") as handle:
                handle.write(wrapper)
            os.chmod(wrapper_path, stat.S_IRWXU)

            script = textwrap.dedent(script_body)
            with open(script_path, "w", encoding="utf-8") as handle:
                handle.write(script)
            os.chmod(script_path, stat.S_IRWXU)

            return subprocess.run(
                [wrapper_path, script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

    def test_inline_assignment_does_not_persist_between_commands(self):
        """Inline VAR=... command should not leak into following commands."""
        result = self._run_lsh_script(
            script_body="A=INLINE printenv A\nprintenv A\necho DONE\n",
            extra_shell_args="--forbidden \"[]\" --allowed \"+['printenv']\"",
        )
        self.assertEqual(result.returncode, 0)
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        self.assertIn("INLINE", lines)
        self.assertIn("DONE", lines)
        self.assertEqual(lines.count("INLINE"), 1)

    def test_assignment_only_command_persists_in_shell_context(self):
        """Assignment-only command should update environment in current shell."""
        result = self._run_lsh_script(
            script_body="LSH_PERSIST=YES\necho $LSH_PERSIST\n",
            extra_shell_args="--forbidden \"[]\"",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("YES", result.stdout)

    def test_forbidden_redirection_is_blocked_and_file_not_created(self):
        """Forbidden redirection should fail closed and not write output file."""
        output_path = "/tmp/lshell_hardening_forbidden_redir.txt"
        if os.path.exists(output_path):
            if os.path.isdir(output_path):
                shutil.rmtree(output_path)
            else:
                os.remove(output_path)

        result = self._run_lsh_script(
            script_body=f"echo hacked > {output_path}\necho AFTER\n",
            extra_shell_args="--strict 0",
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn('lshell: forbidden character: ">"', result.stdout + result.stderr)
        self.assertIn("AFTER", result.stdout)
        self.assertFalse(os.path.exists(output_path))

    def test_operator_smuggling_reports_syntax_error_and_does_not_execute_payload(self):
        """Malformed operator chains should not execute hidden payload commands."""
        result = self._run_lsh_script(
            script_body="echo ONE ||| echo TWO\necho SAFE\n",
            extra_shell_args="--forbidden \"[]\"",
        )
        self.assertEqual(result.returncode, 0)
        combined = result.stdout + result.stderr
        self.assertIn("lshell: unknown syntax:", combined)
        self.assertIn("SAFE", combined)
        self.assertNotIn("TWO", result.stdout)

    def test_path_hijack_via_inline_assignment_should_not_override_allowed_command(self):
        """Security expectation: PATH=... cmd should not allow binary hijacking."""
        with tempfile.TemporaryDirectory(prefix="lshell-path-hijack-") as tempdir:
            rogue_id = os.path.join(tempdir, "id")
            with open(rogue_id, "w", encoding="utf-8") as handle:
                handle.write("#!/bin/sh\necho PWNED_PATH_HIJACK\n")
            os.chmod(rogue_id, stat.S_IRWXU)

            result = self._run_lsh_script(
                script_body=f"PATH={tempdir} id\n",
                extra_shell_args="--forbidden \"[]\" --allowed \"+['id']\"",
            )

            self.assertEqual(result.returncode, 0)
            self.assertNotIn(
                "PWNED_PATH_HIJACK",
                result.stdout,
                msg="allowed command resolution should not be hijackable via PATH assignment",
            )

    def test_bash_env_persistence_should_not_inject_into_future_commands(self):
        """Security expectation: assignment-only BASH_ENV should not affect exec_cmd shells."""
        with tempfile.NamedTemporaryFile("w", delete=False, prefix="lshell-bashenv-") as handle:
            handle.write("echo BASH_ENV_INJECTION\n")
            bash_env = handle.name

        try:
            result = self._run_lsh_script(
                script_body=f"BASH_ENV={bash_env}\necho SAFE\n",
                extra_shell_args="--forbidden \"[]\"",
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("SAFE", result.stdout)
            self.assertNotIn(
                "BASH_ENV_INJECTION",
                result.stdout,
                msg="BASH_ENV assignment should be blocked or sanitized for command execution",
            )
        finally:
            if os.path.exists(bash_env):
                os.remove(bash_env)
