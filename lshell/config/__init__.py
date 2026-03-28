"""Configuration subsystem for runtime loading, resolution, and diagnostics.

Modules:
- schema: parse and validate configuration values.
- resolve: compute effective raw values from layered config sections.
- runtime: build and apply the effective runtime shell configuration.
- diagnostics: inspect/print effective policy resolution for policy-show.
"""

__all__ = ["schema", "resolve", "runtime", "diagnostics"]
