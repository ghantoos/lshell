"""Guardrails for exhaustive configuration-coverage mapping."""

import json
import unittest

from test.config_coverage_manifest_tools import (
    DEFAULT_TRACKED_TESTS_GLOB,
    MANIFEST_PATH,
    collect_python_test_nodeids,
    compute_tests_fingerprint,
    supported_config_keys,
)


def _load_manifest():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


class TestConfigCoverageManifestGuard(unittest.TestCase):
    """Fail fast when config settings lose explicit test coverage."""

    def test_manifest_supported_key_list_matches_runtime(self):
        """Manifest key inventory must exactly match currently supported config keys."""
        manifest = _load_manifest()
        declared = set(manifest.get("supported_keys", []))
        computed = supported_config_keys()
        self.assertEqual(
            declared,
            computed,
            msg=(
                "config_coverage_manifest.json supported_keys does not match "
                "runtime/schema/configparams-derived keys"
            ),
        )

    def test_every_supported_key_has_direct_and_interaction_coverage(self):
        """Every supported key must map to at least one direct and interaction test."""
        manifest = _load_manifest()
        coverage = manifest.get("coverage", {})
        supported = supported_config_keys()

        missing = sorted(key for key in supported if key not in coverage)
        self.assertFalse(
            missing,
            msg=f"Missing coverage entries for supported keys: {', '.join(missing)}",
        )

        for key in sorted(supported):
            entry = coverage[key]
            direct = entry.get("direct", [])
            interaction = entry.get("interaction", [])
            self.assertTrue(
                direct,
                msg=f"Key '{key}' must declare at least one direct test",
            )
            self.assertTrue(
                interaction,
                msg=f"Key '{key}' must declare at least one interaction test",
            )

    def test_manifest_references_existing_python_tests(self):
        """All manifest node IDs must resolve to concrete Python tests in test/."""
        manifest = _load_manifest()
        coverage = manifest.get("coverage", {})
        known_tests = collect_python_test_nodeids()

        missing_test_ids = []
        for key, entry in coverage.items():
            for field in ("direct", "interaction"):
                for nodeid in entry.get(field, []):
                    if nodeid not in known_tests:
                        missing_test_ids.append((key, field, nodeid))

        self.assertFalse(
            missing_test_ids,
            msg=(
                "Manifest references unknown tests: "
                + ", ".join(
                    f"{key}:{field}:{nodeid}"
                    for key, field, nodeid in missing_test_ids
                )
            ),
        )

    def test_manifest_test_fingerprint_matches_current_suite(self):
        """Manifest fingerprint must track current test suite content."""
        manifest = _load_manifest()
        tracked_glob = manifest.get("tracked_tests_glob", DEFAULT_TRACKED_TESTS_GLOB)
        declared_fingerprint = manifest.get("tests_fingerprint_sha256")
        computed_fingerprint = compute_tests_fingerprint(tracked_glob)
        self.assertEqual(
            declared_fingerprint,
            computed_fingerprint,
            msg=(
                "config_coverage_manifest.json test fingerprint is stale. "
                "Run: python3 scripts/update_config_coverage_manifest.py --write"
            ),
        )


if __name__ == "__main__":
    unittest.main()
