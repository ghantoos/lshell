#!/usr/bin/env python3
"""Update or check test/config_coverage_manifest.json."""

from __future__ import annotations

import argparse
import difflib
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from test.config_coverage_manifest_tools import (
    DEFAULT_TRACKED_TESTS_GLOB,
    MANIFEST_PATH,
    supported_config_keys,
    compute_tests_fingerprint,
)


def _normalized_manifest(current_manifest):
    supported_keys = sorted(supported_config_keys())
    coverage = current_manifest.get("coverage", {})

    normalized_coverage = {}
    for key in supported_keys:
        entry = coverage.get(key, {})
        direct = sorted(set(entry.get("direct", [])))
        interaction = sorted(set(entry.get("interaction", [])))
        normalized_coverage[key] = {
            "direct": direct,
            "interaction": interaction,
        }

    tracked_glob = current_manifest.get("tracked_tests_glob", DEFAULT_TRACKED_TESTS_GLOB)

    normalized = {
        "version": 1,
        "tracked_tests_glob": tracked_glob,
        "tests_fingerprint_sha256": compute_tests_fingerprint(tracked_glob),
        "supported_keys": supported_keys,
        "coverage": normalized_coverage,
    }
    return normalized


def _render(data):
    return json.dumps(data, indent=2, sort_keys=False) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--write",
        action="store_true",
        help="Write normalized manifest content to disk.",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="Check manifest is up to date (default mode).",
    )
    args = parser.parse_args(argv)

    with open(MANIFEST_PATH, "r", encoding="utf-8") as handle:
        current = json.load(handle)

    normalized = _normalized_manifest(current)
    current_text = _render(current)
    normalized_text = _render(normalized)

    if args.write:
        with open(MANIFEST_PATH, "w", encoding="utf-8") as handle:
            handle.write(normalized_text)
        print(f"Updated {MANIFEST_PATH}")
        return 0

    if current_text != normalized_text:
        diff = difflib.unified_diff(
            current_text.splitlines(),
            normalized_text.splitlines(),
            fromfile="current",
            tofile="expected",
            lineterm="",
        )
        print("\n".join(diff))
        print(
            "\nManifest is stale. Run: python3 scripts/update_config_coverage_manifest.py --write"
        )
        return 1

    print("Manifest is up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
