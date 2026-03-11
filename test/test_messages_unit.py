"""Unit tests for centralized message templates."""

import unittest

from lshell import messages


class TestMessagesUnit(unittest.TestCase):
    """Validate default and custom message rendering."""

    def test_unknown_syntax_message(self):
        """Render the unknown syntax message from default and custom config."""
        conf = {}
        self.assertEqual(
            messages.get_message(conf, "unknown_syntax", command="echo nope"),
            "lshell: unknown syntax: echo nope",
        )

        custom_conf = {"messages": {"unknown_syntax": "custom syntax: {command}"}}
        self.assertEqual(
            messages.get_message(
                custom_conf, "unknown_syntax", command="echo nope"
            ),
            "custom syntax: echo nope",
        )

    def test_forbidden_generic_message(self):
        """Render the generic forbidden message from default and custom config."""
        conf = {}
        self.assertEqual(
            messages.get_message(
                conf,
                "forbidden_generic",
                messagetype="sudo command",
                command="sudo cat /etc/passwd",
            ),
            'lshell: forbidden sudo command: "sudo cat /etc/passwd"',
        )

        custom_conf = {
            "messages": {
                "forbidden_generic": "blocked {messagetype}: {command}",
            }
        }
        self.assertEqual(
            messages.get_message(
                custom_conf,
                "forbidden_generic",
                messagetype="sudo command",
                command="sudo cat /etc/passwd",
            ),
            "blocked sudo command: sudo cat /etc/passwd",
        )

    def test_command_not_found_message(self):
        """Render the command-not-found message from default and custom config."""
        conf = {}
        self.assertEqual(
            messages.get_message(conf, "command_not_found", command="catt"),
            'lshell: command not found: "catt"',
        )

        custom_conf = {"messages": {"command_not_found": "missing: {command}"}}
        self.assertEqual(
            messages.get_message(custom_conf, "command_not_found", command="catt"),
            "missing: catt",
        )

    def test_forbidden_command_message(self):
        """Render the forbidden command message from default and custom config."""
        conf = {}
        self.assertEqual(
            messages.get_message(conf, "forbidden_command", command="id"),
            'lshell: forbidden command: "id"',
        )

        custom_conf = {"messages": {"forbidden_command": "blocked command: {command}"}}
        self.assertEqual(
            messages.get_message(custom_conf, "forbidden_command", command="id"),
            "blocked command: id",
        )

    def test_forbidden_path_message(self):
        """Render the forbidden path message from default and custom config."""
        conf = {}
        self.assertEqual(
            messages.get_message(conf, "forbidden_path", command="/root/"),
            'lshell: forbidden path: "/root/"',
        )

        custom_conf = {"messages": {"forbidden_path": "blocked path: {command}"}}
        self.assertEqual(
            messages.get_message(custom_conf, "forbidden_path", command="/root/"),
            "blocked path: /root/",
        )

    def test_forbidden_character_message(self):
        """Render the forbidden character message from default and custom config."""
        conf = {}
        self.assertEqual(
            messages.get_message(conf, "forbidden_character", command=";"),
            'lshell: forbidden character: ";"',
        )

        custom_conf = {
            "messages": {"forbidden_character": "blocked character: {command}"}
        }
        self.assertEqual(
            messages.get_message(custom_conf, "forbidden_character", command=";"),
            "blocked character: ;",
        )

    def test_forbidden_control_char_message(self):
        """Render the forbidden control-char message from default and custom config."""
        conf = {}
        self.assertEqual(
            messages.get_message(
                conf, "forbidden_control_char", command="echo\x08test"
            ),
            'lshell: forbidden control char: "echo\x08test"',
        )

        custom_conf = {
            "messages": {
                "forbidden_control_char": "blocked control char: {command}"
            }
        }
        self.assertEqual(
            messages.get_message(
                custom_conf, "forbidden_control_char", command="echo\x08test"
            ),
            "blocked control char: echo\x08test",
        )

    def test_forbidden_command_over_ssh_message(self):
        """Render the forbidden SSH command message from default and custom config."""
        conf = {}
        self.assertEqual(
            messages.get_message(
                conf,
                "forbidden_command_over_ssh",
                message="command over SSH",
                command="id",
            ),
            'lshell: forbidden command over SSH: "id"',
        )

        custom_conf = {
            "messages": {
                "forbidden_command_over_ssh": "ssh blocked {message}: {command}"
            }
        }
        self.assertEqual(
            messages.get_message(
                custom_conf,
                "forbidden_command_over_ssh",
                message="command over SSH",
                command="id",
            ),
            "ssh blocked command over SSH: id",
        )

    def test_forbidden_scp_over_ssh_message(self):
        """Render the forbidden SCP-over-SSH message from default and custom config."""
        conf = {}
        self.assertEqual(
            messages.get_message(
                conf, "forbidden_scp_over_ssh", message="SCP connection"
            ),
            "lshell: forbidden SCP connection",
        )

        custom_conf = {
            "messages": {"forbidden_scp_over_ssh": "scp blocked: {message}"}
        }
        self.assertEqual(
            messages.get_message(
                custom_conf, "forbidden_scp_over_ssh", message="SCP connection"
            ),
            "scp blocked: SCP connection",
        )

    def test_warning_remaining_message(self):
        """Render the warning counter message from default and custom config."""
        conf = {}
        self.assertEqual(
            messages.get_message(
                conf,
                "warning_remaining",
                remaining=1,
                violation_label="violation",
            ),
            "lshell: warning: 1 violation remaining before session termination",
        )

        custom_conf = {
            "messages": {
                "warning_remaining": "*** {remaining} {violation_label} left"
            }
        }
        self.assertEqual(
            messages.get_message(
                custom_conf,
                "warning_remaining",
                remaining=1,
                violation_label="violation",
            ),
            "*** 1 violation left",
        )

    def test_session_terminated_message(self):
        """Render the session termination message from default and custom config."""
        conf = {}
        self.assertEqual(
            messages.get_message(conf, "session_terminated"),
            "lshell: session terminated: warning limit exceeded",
        )

        custom_conf = {"messages": {"session_terminated": "session closed"}}
        self.assertEqual(
            messages.get_message(custom_conf, "session_terminated"),
            "session closed",
        )

    def test_incident_reported_message(self):
        """Render the incident reported message from default and custom config."""
        conf = {}
        self.assertEqual(
            messages.get_message(conf, "incident_reported"),
            "This incident has been reported.",
        )

        custom_conf = {"messages": {"incident_reported": "Incident logged."}}
        self.assertEqual(
            messages.get_message(custom_conf, "incident_reported"),
            "Incident logged.",
        )

    def test_get_forbidden_message_prefers_specific_template(self):
        """Prefer the specific forbidden template when one exists."""
        conf = {}
        self.assertEqual(
            messages.get_forbidden_message(conf, "command", "id"),
            'lshell: forbidden command: "id"',
        )

    def test_get_forbidden_message_falls_back_to_generic_template(self):
        """Fall back to the generic forbidden template for dynamic message types."""
        conf = {}
        self.assertEqual(
            messages.get_forbidden_message(conf, "sudo command", "sudo -u root"),
            'lshell: forbidden sudo command: "sudo -u root"',
        )

        custom_conf = {
            "messages": {"forbidden_generic": "blocked {messagetype}: {command}"}
        }
        self.assertEqual(
            messages.get_forbidden_message(
                custom_conf, "sudo command", "sudo -u root"
            ),
            "blocked sudo command: sudo -u root",
        )

    def test_validate_messages_config_accepts_all_supported_keys(self):
        """Accept a messages dictionary containing every supported key."""
        overrides = {
            "unknown_syntax": "a {command}",
            "command_not_found": "a {command}",
            "forbidden_generic": "a {messagetype} {command}",
            "forbidden_command": "a {command}",
            "forbidden_path": "a {command}",
            "forbidden_character": "a {command}",
            "forbidden_control_char": "a {command}",
            "forbidden_command_over_ssh": "a {message} {command}",
            "forbidden_scp_over_ssh": "a {message}",
            "warning_remaining": "a {remaining} {violation_label}",
            "session_terminated": "a",
            "incident_reported": "b",
        }
        self.assertEqual(messages.validate_messages_config(overrides), overrides)


if __name__ == "__main__":
    unittest.main()
