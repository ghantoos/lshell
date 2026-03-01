"""Functional tests for lshell script execution"""

import os
import unittest
from getpass import getuser
import tempfile
import shutil
import pexpect


TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG = f"{TOPDIR}/test/testfiles/test.conf"
LSHELL = f"{TOPDIR}/bin/lshell"
USER = getuser()
PROMPT = f"{USER}:~\\$"
POLICY_HELP_COMMANDS = [
    "bg",
    "cd",
    "clear",
    "echo",
    "exit",
    "fg",
    "help",
    "history",
    "jobs",
    "lpath",
    "lsudo",
    "policy-path",
    "policy-show",
    "policy-sudo",
    "source",
]


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

    def test_39_script_execution_with_template(self):
        """Test executing script after modifying shebang and clean up afterward"""

        template_path = f"{TOPDIR}/test/template.lsh"
        test_script_path = "/tmp/test.lsh"

        # Step 1: Create the wrapper script
        with tempfile.NamedTemporaryFile(mode="w", delete=False, dir="/tmp") as wrapper:
            wrapper.write(
                f"""#!/bin/sh
exec {LSHELL} --config {CONFIG} --forbidden \"-[';','&']\" "$@"
"""
            )
            wrapper.flush()  # Ensure data is written to disk
            wrapper_path = wrapper.name

        # Step 2: Copy template.lsh to test.lsh and replace the shebang
        shutil.copy(template_path, test_script_path)

        # Make the wrapper executable
        os.chmod(wrapper_path, 0o755)
        os.chmod(test_script_path, 0o755)

        # Replace the placeholder in the shebang
        with open(test_script_path, "r+") as f:
            content = f.read()
            content = content.replace("#!SHEBANG", f"#!{wrapper_path}")
            f.seek(0)
            f.write(content)
            f.truncate()

        # Spawn a child process to run the test.lsh script using pexpect
        child = pexpect.spawn(test_script_path)

        # Wait for the script to finish executing
        child.expect(pexpect.EOF)

        # Capture and validate key output markers while allowing wrapped help output
        result = child.before.decode("utf8").strip()
        self.assertIn("test\r\n", result)
        self.assertIn("lshell: unknown syntax: dig google.com", result)
        self.assertIn('lshell: forbidden path: "/tmp/"', result)
        self.assertIn("lshell: warning: 1 violation remaining", result)
        self.assertIn("FREEDOM", result)
        self.assertIn('lshell: forbidden path: "/"', result)
        self.assertIn("lshell: warning: 0 violations remaining", result)
        for command in POLICY_HELP_COMMANDS:
            self.assertIn(command, result)

        # Cleanup: remove the test script after the test
        if os.path.exists(test_script_path):
            os.remove(test_script_path)
        self.do_exit(child)

    def test_40_script_execution_with_template_strict(self):
        """Test executing script after modifying shebang and clean up afterward"""

        template_path = f"{TOPDIR}/test/template.lsh"
        test_script_path = "/tmp/test.lsh"

        # Step 1: Create the wrapper script
        with tempfile.NamedTemporaryFile(mode="w", delete=False, dir="/tmp") as wrapper:
            wrapper.write(
                f"""#!/bin/sh
exec {LSHELL} --config {CONFIG} --forbidden \"-[';','&']\" --strict 1 "$@"
"""
            )
            wrapper.flush()  # Ensure data is written to disk
            wrapper_path = wrapper.name

        # Step 2: Copy template.lsh to test.lsh and replace the shebang
        shutil.copy(template_path, test_script_path)

        # Make the wrapper executable
        os.chmod(wrapper_path, 0o755)
        os.chmod(test_script_path, 0o755)

        with open(test_script_path, "r+") as f:
            content = f.read()
            content = content.replace("#!SHEBANG", f"#!{wrapper_path}")
            f.seek(0)
            f.write(content)
            f.truncate()

        # Step 3: Spawn a child process to run the test.lsh script using pexpect
        child = pexpect.spawn(test_script_path)

        # Wait for the script to finish executing
        child.expect(pexpect.EOF)

        # Capture and validate key output markers while allowing wrapped help output
        result = child.before.decode("utf8").strip()
        self.assertIn("test\r\n", result)
        self.assertIn('lshell: forbidden command: "dig"', result)
        self.assertIn('lshell: forbidden path: "/tmp/"', result)
        self.assertIn("lshell: warning: 1 violation remaining", result)
        self.assertIn("lshell: warning: 0 violations remaining", result)
        self.assertIn("FREEDOM", result)
        self.assertIn('lshell: forbidden path: "/"', result)
        self.assertIn("lshell: session terminated: warning limit exceeded", result)
        for command in POLICY_HELP_COMMANDS:
            self.assertIn(command, result)

        # Step 5: Cleanup: remove the test script and wrapper after the test
        if os.path.exists(test_script_path):
            os.remove(test_script_path)
        if os.path.exists(wrapper_path):
            os.remove(wrapper_path)
        self.do_exit(child)
