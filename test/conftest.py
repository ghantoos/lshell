"""Pytest test-suite configuration."""

try:
    from hypothesis import settings
except ImportError:
    settings = None


if settings is not None:
    # Avoid filesystem writes for Hypothesis' example database in locked-down CI
    # containers where the project workspace may be read-only for the test user.
    settings.register_profile("lshell_ci", settings(database=None))
    settings.load_profile("lshell_ci")
