"""Property-based security tests for parser, expansion, and path ACL checks."""

import os
import tempfile
import unittest
from unittest.mock import patch

from lshell.config import diagnostics as policy
from lshell import sec
from lshell import utils

try:
    from hypothesis import HealthCheck
    from hypothesis import assume
    from hypothesis import given
    from hypothesis import settings
    from hypothesis import strategies as st
except ImportError:  # pragma: no cover - environment-dependent skip
    class _DummyStrategy:
        """Placeholder strategy object used when Hypothesis is unavailable."""

    class _DummyStrategies:
        """Minimal strategy API shim so tests can be collected and skipped."""

        @staticmethod
        def characters(*_args, **_kwargs):
            """Return placeholder `characters` strategy."""
            return _DummyStrategy()

        @staticmethod
        def from_regex(*_args, **_kwargs):
            """Return placeholder `from_regex` strategy."""
            return _DummyStrategy()

        @staticmethod
        def integers(*_args, **_kwargs):
            """Return placeholder `integers` strategy."""
            return _DummyStrategy()

        @staticmethod
        def text(*_args, **_kwargs):
            """Return placeholder `text` strategy."""
            return _DummyStrategy()

        @staticmethod
        def sampled_from(*_args, **_kwargs):
            """Return placeholder `sampled_from` strategy."""
            return _DummyStrategy()

        @staticmethod
        def composite(_function):
            """Return placeholder composite-decorator wrapper."""
            def _wrapper(*_args, **_kwargs):
                return _DummyStrategy()

            return _wrapper

    class HealthCheck:  # pragma: no cover - shim only
        """Fallback shim exposing Hypothesis health-check constants."""

        too_slow = "too_slow"

    def assume(_condition):
        """No-op assume shim used only when tests are skipped."""
        return None

    def settings(*_args, **_kwargs):
        """Pass-through decorator when Hypothesis is unavailable."""

        def _decorator(function):
            return function

        return _decorator

    def given(*_args, **_kwargs):
        """Skip decorated tests when Hypothesis is unavailable."""

        def _decorator(function):
            return unittest.skip("hypothesis is not installed")(function)

        return _decorator

    st = _DummyStrategies()


_OPERATOR_TOKENS = ["&&", "||", "|", ";", "&"]
# Keep payloads free of expansion/backtick metacharacters so the generated
# lines stay within this test's "known-valid quoting" scope.
_PAYLOAD_ALPHABET = st.characters(
    blacklist_characters=['"', "'", "\\", "\n", "\r", "`", "$"],
    min_codepoint=32,
    max_codepoint=126,
)
_NAME_STRATEGY = st.from_regex(r"[a-z]{3,8}", fullmatch=True)


@st.composite
def _quoted_operator_sequence(draw):
    """Build `echo "payload"` command chains with explicit operator tokens."""
    command_count = draw(st.integers(min_value=1, max_value=4))
    chunks = []
    expected = []

    for index in range(command_count):
        payload = draw(st.text(_PAYLOAD_ALPHABET, min_size=1, max_size=12))
        command = f'echo "{payload}"'
        chunks.append(command)
        expected.append(command)
        if index < command_count - 1:
            operator = draw(st.sampled_from(_OPERATOR_TOKENS))
            chunks.append(operator)
            expected.append(operator)

    return " ".join(chunks), expected


def _path_conf(allowed_paths, denied_paths=None):
    """Create a minimal path-only security config for `sec.check_path`."""
    if isinstance(allowed_paths, str):
        allowed_paths = [allowed_paths]
    allowed = allowed_paths or []
    denied = denied_paths or []
    allow_acl = "".join(f"{os.path.realpath(path)}|" for path in allowed)
    deny_acl = "".join(f"{os.path.realpath(path)}|" for path in denied)
    return {"path": [allow_acl, deny_acl]}


class TestSecurityPropertyBased(unittest.TestCase):
    """Property-driven tests for parser/auth hardening invariants."""

    @settings(max_examples=100, deadline=None)
    @given(sequence=_quoted_operator_sequence())
    def test_split_command_sequence_round_trips_known_operator_sequences(self, sequence):
        """Parser should preserve explicit command/operator structure."""
        line, expected = sequence
        self.assertEqual(utils.split_command_sequence(line), expected)

    @settings(max_examples=100, deadline=None)
    @given(sequence=_quoted_operator_sequence())
    def test_split_commands_matches_non_operator_tokens_for_valid_sequences(self, sequence):
        """`split_commands` should keep only command segments from valid sequences."""
        line, expected = sequence
        expected_commands = [item for item in expected if item not in _OPERATOR_TOKENS]
        self.assertEqual(utils.split_commands(line), expected_commands)

    @settings(max_examples=100, deadline=None)
    @given(
        left=st.text(_PAYLOAD_ALPHABET, min_size=1, max_size=12),
        operator_a=st.sampled_from(_OPERATOR_TOKENS),
        operator_b=st.sampled_from(_OPERATOR_TOKENS),
        right=st.text(_PAYLOAD_ALPHABET, min_size=1, max_size=12),
    )
    def test_split_command_sequence_rejects_adjacent_operators(
        self, left, operator_a, operator_b, right
    ):
        """Two consecutive top-level operators should fail closed."""
        line = f'echo "{left}" {operator_a} {operator_b} echo "{right}"'
        self.assertIsNone(utils.split_command_sequence(line))

    @settings(max_examples=100, deadline=None)
    @given(payload=st.text(_PAYLOAD_ALPHABET, min_size=1, max_size=24))
    def test_split_command_sequence_does_not_split_operators_inside_single_quotes(
        self, payload
    ):
        """Top-level split must ignore operators that are inside single quotes."""
        line = f"echo '{payload}' && echo done"
        self.assertEqual(
            utils.split_command_sequence(line),
            [f"echo '{payload}'", "&&", "echo done"],
        )

    @settings(max_examples=100, deadline=None)
    @given(payload=st.text(_PAYLOAD_ALPHABET, min_size=1, max_size=24))
    def test_split_command_sequence_does_not_split_operators_inside_double_quotes(
        self, payload
    ):
        """Top-level split must ignore operators that are inside double quotes."""
        line = f'echo "{payload}" || echo done'
        self.assertEqual(
            utils.split_command_sequence(line),
            [f'echo "{payload}"', "||", "echo done"],
        )

    @settings(max_examples=80, deadline=None)
    @given(
        payload=st.text(
            st.characters(
                blacklist_characters=["'", ")", "\\", "\n", "\r"],
                min_codepoint=32,
                max_codepoint=126,
            ),
            min_size=1,
            max_size=16,
        )
    )
    def test_split_command_sequence_does_not_split_operators_inside_substitution(
        self, payload
    ):
        """Top-level split must ignore operators inside command substitution."""
        line = f"echo $(printf '%s' '{payload}') | wc -c"
        self.assertEqual(
            utils.split_command_sequence(line),
            [f"echo $(printf '%s' '{payload}')", "|", "wc -c"],
        )

    @settings(max_examples=100, deadline=None)
    @given(
        variable=st.from_regex(r"[A-Z_][A-Z0-9_]{0,9}", fullmatch=True),
        value=st.text(
            st.characters(
                blacklist_characters=["\\", "'", '"', "\n", "\r", "$"],
                min_codepoint=32,
                max_codepoint=126,
            ),
            min_size=0,
            max_size=20,
        ),
    )
    def test_expand_vars_quoted_keeps_single_quoted_variable_literal(self, variable, value):
        """Single-quoted `$VAR` must remain literal while unquoted `$VAR` expands."""
        line = f"echo '${variable}' ${variable}"
        with patch.dict(os.environ, {variable: value}, clear=False):
            expanded = utils.expand_vars_quoted(line)
        self.assertEqual(expanded, f"echo '${variable}' {value}")

    @settings(max_examples=100, deadline=None)
    @given(
        variable=st.from_regex(r"[A-Z_][A-Z0-9_]{0,9}", fullmatch=True),
        value=st.text(
            st.characters(
                blacklist_characters=["\\", "'", '"', "\n", "\r", "$"],
                min_codepoint=32,
                max_codepoint=126,
            ),
            min_size=0,
            max_size=20,
        ),
    )
    def test_expand_vars_quoted_keeps_backslash_escaped_dollar_literal(
        self, variable, value
    ):
        """Escaped dollars must remain literal and not trigger expansion."""
        line = rf"echo \${variable} ${variable}"
        with patch.dict(os.environ, {variable: value}, clear=False):
            expanded = utils.expand_vars_quoted(line)
        self.assertEqual(expanded, rf"echo \${variable} {value}")

    @settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        allowed_name=_NAME_STRATEGY,
        sibling_suffix=st.from_regex(r"[a-z0-9]{1,6}", fullmatch=True),
    )
    def test_check_path_blocks_sibling_prefix_confusion_property(
        self, allowed_name, sibling_suffix
    ):
        """Allowing `/x/allow` must not allow sibling `/x/allow-*` paths."""
        with tempfile.TemporaryDirectory(prefix="lshell-path-prop-") as tempdir:
            allowed_dir = os.path.join(tempdir, allowed_name)
            sibling_dir = os.path.join(tempdir, f"{allowed_name}-{sibling_suffix}")
            assume(os.path.realpath(allowed_dir) != os.path.realpath(sibling_dir))
            os.makedirs(allowed_dir, exist_ok=True)
            os.makedirs(sibling_dir, exist_ok=True)

            conf = _path_conf(allowed_dir)
            ret, _ = sec.check_path(f"ls {sibling_dir}", conf, completion=1, strict=0)
            self.assertEqual(ret, 1)

    @settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        allowed_name=_NAME_STRATEGY,
        child_a=st.from_regex(r"[a-z0-9]{1,6}", fullmatch=True),
        child_b=st.from_regex(r"[a-z0-9]{1,6}", fullmatch=True),
    )
    def test_check_path_allows_nested_descendants_property(
        self, allowed_name, child_a, child_b
    ):
        """Paths nested under an allow root should pass ACL checks."""
        with tempfile.TemporaryDirectory(prefix="lshell-path-prop-") as tempdir:
            allowed_dir = os.path.join(tempdir, allowed_name)
            nested_dir = os.path.join(allowed_dir, child_a, child_b)
            os.makedirs(nested_dir, exist_ok=True)

            conf = _path_conf(allowed_dir)
            ret, _ = sec.check_path(f"ls {nested_dir}", conf, completion=1, strict=0)
            self.assertEqual(ret, 0)

    @settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        allowed_name=_NAME_STRATEGY,
        denied_name=st.from_regex(r"[a-z]{3,8}", fullmatch=True),
    )
    def test_check_path_glob_fails_closed_when_any_match_is_denied(
        self, allowed_name, denied_name
    ):
        """Glob checks should fail closed if any expanded target is outside allow roots."""
        assume(allowed_name != denied_name)
        with tempfile.TemporaryDirectory(prefix="lshell-path-prop-") as tempdir:
            allowed_dir = os.path.join(tempdir, allowed_name)
            denied_dir = os.path.join(tempdir, denied_name)
            os.makedirs(allowed_dir, exist_ok=True)
            os.makedirs(denied_dir, exist_ok=True)

            conf = _path_conf(allowed_dir)
            ret, _ = sec.check_path(f"ls {tempdir}/*", conf, completion=1, strict=0)
            self.assertEqual(ret, 1)

    @settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        root_name=_NAME_STRATEGY,
        deny_name=st.from_regex(r"[a-z0-9]{1,6}", fullmatch=True),
        reallow_name=st.from_regex(r"[a-z0-9]{1,6}", fullmatch=True),
        leaf_name=st.from_regex(r"[a-z0-9]{1,6}", fullmatch=True),
    )
    def test_check_path_uses_specificity_with_reallow_over_broader_deny(
        self, root_name, deny_name, reallow_name, leaf_name
    ):
        """Most-specific ACL prefix should win for deny/re-allow path chains."""
        with tempfile.TemporaryDirectory(prefix="lshell-path-prop-") as tempdir:
            root_dir = os.path.join(tempdir, root_name)
            denied_root = os.path.join(root_dir, deny_name)
            reallowed_root = os.path.join(denied_root, reallow_name)
            denied_leaf = os.path.join(denied_root, "blocked")
            reallowed_leaf = os.path.join(reallowed_root, leaf_name)
            os.makedirs(denied_leaf, exist_ok=True)
            os.makedirs(reallowed_leaf, exist_ok=True)

            conf = _path_conf([root_dir, reallowed_root], [denied_root])
            denied_ret, _ = sec.check_path(
                f"ls {denied_leaf}", conf, completion=1, strict=0
            )
            allowed_ret, _ = sec.check_path(
                f"ls {reallowed_leaf}", conf, completion=1, strict=0
            )
            self.assertEqual(denied_ret, 1)
            self.assertEqual(allowed_ret, 0)

    @settings(max_examples=80, deadline=None)
    @given(
        command=st.from_regex(r"[a-z]{3,10}", fullmatch=True),
        strict=st.sampled_from([0, 1]),
    )
    def test_policy_command_decision_unknown_command_reason_reflects_strict_mode(
        self, command, strict
    ):
        """Policy decision reasons should differ between strict/non-strict modes."""
        assume(command != "echo")
        runtime_policy = {
            "forbidden": [],
            "allowed": ["echo"],
            "strict": strict,
            "sudo_commands": [],
            "allowed_file_extensions": [],
            "path": ["", ""],
        }

        decision = policy.policy_command_decision(f"{command} arg", runtime_policy)
        self.assertFalse(decision["allowed"])
        if strict:
            self.assertIn("forbidden command", decision["reason"])
        else:
            self.assertIn("unknown syntax", decision["reason"])

    @settings(max_examples=80, deadline=None)
    @given(
        variable=st.from_regex(r"[A-Z_][A-Z0-9_]{0,7}", fullmatch=True),
        value=st.from_regex(r"[A-Za-z0-9_]{0,8}", fullmatch=True),
    )
    def test_policy_command_decision_allows_assignment_prefix_for_allowlisted_full_command(
        self, variable, value
    ):
        """Allowlist checks should still pass when command uses assignment prefixes."""
        runtime_policy = {
            "forbidden": [],
            "allowed": ["echo ok"],
            "strict": 1,
            "sudo_commands": [],
            "allowed_file_extensions": [],
            "path": ["", ""],
        }

        decision = policy.policy_command_decision(
            f"{variable}={value} echo ok", runtime_policy
        )
        self.assertTrue(decision["allowed"])
