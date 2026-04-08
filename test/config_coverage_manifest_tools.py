"""Shared helpers for config-coverage manifest maintenance and guard tests."""

import ast
import hashlib
from pathlib import Path

from lshell import variables
from lshell.config import schema


MANIFEST_PATH = Path(__file__).with_name("config_coverage_manifest.json")
NON_SETTING_CLI_PARAMS = {"config", "log"}
DEFAULT_TRACKED_TESTS_GLOB = "test/test_*.py"


def supported_config_keys():
    """Return the full set of currently supported runtime config keys."""
    keys = set()

    for option in variables.configparams:
        if option.endswith("="):
            key = option[:-1]
            if key not in NON_SETTING_CLI_PARAMS:
                keys.add(key)

    keys.update(schema.LIST_VALUE_KEYS)
    keys.update(schema.INT_VALUE_KEYS)
    keys.update(schema.DICT_VALUE_KEYS)
    keys.update(schema.STRING_VALUE_KEYS)

    # Runtime-only accepted key (not exposed in variables.configparams).
    keys.add("login_script")
    # Global include lookup is merge-time behavior.
    keys.add("include_dir")
    # Global logging destination is consumed before user policy materialization.
    keys.add("logpath")

    return keys


def collect_python_test_nodeids():
    """Collect pytest-style node IDs for top-level and unittest-style tests."""
    nodeids = set()
    test_dir = Path(__file__).parent
    repo_root = Path(__file__).resolve().parents[1]
    for path in sorted(test_dir.glob("test_*.py")):
        module = ast.parse(path.read_text(encoding="utf-8"))
        try:
            rel_path = path.relative_to(repo_root).as_posix()
        except ValueError:
            rel_path = path.as_posix()

        for node in module.body:
            if isinstance(node, ast.ClassDef):
                for member in node.body:
                    if isinstance(member, ast.FunctionDef) and member.name.startswith(
                        "test_"
                    ):
                        nodeids.add(f"{rel_path}::{node.name}::{member.name}")
                continue

            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                nodeids.add(f"{rel_path}::{node.name}")

    return nodeids


def compute_tests_fingerprint(tracked_glob=DEFAULT_TRACKED_TESTS_GLOB):
    """Hash tracked test file paths and contents for manifest freshness checks."""
    repo_root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(repo_root.glob(tracked_glob)):
        if not path.is_file():
            continue
        rel_path = path.relative_to(repo_root).as_posix().encode("utf-8")
        digest.update(rel_path)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
