"""Sentinel Desktop v18.x — Humanization Engine subpackage.

Makes desktop input flow like a human operator: curved cursor paths, eased
velocity, variable typing cadence, natural micro-pauses. Inserted at the two
existing input chokepoints (core/desktop.py and core/stealth_input.py).

Target level: NATURALISTIC behavioral only. Adversarial/anti-detection is
deferred — see docs/superpowers/notes/future-stealth-mode.md.

Submodules:
- rng      : seeded, reproducible RNG (record/replay requirement for stealth tier)
- profile  : tempo Profile dataclass (extension point for a future StealthProfile)
- motion   : bezier path generation + eased timing + imprecise landing
- typing   : per-keystroke cadence from real distributions
- timing   : click-hold, think-bump, maybe-pause helpers

Master switch: SENTINEL_HUMANIZE env var. ON by default for production runs;
tests/conftest.py forces it OFF so the existing test suite (which asserts
exact coordinates/timings) stays green. See is_enabled().
"""

from __future__ import annotations

import os

__all__ = ["is_enabled"]


def is_enabled() -> bool:
    """Return whether humanization is active.

    Resolved from the ``SENTINEL_HUMANIZE`` env var:
    - unset / "1" / "on" / "true" / "yes" (case-insensitive) → enabled
    - "0" / "off" / "false" / "no"                      → disabled

    Production runs default to ON. The test suite sets SENTINEL_HUMANIZE=0 in
    tests/conftest.py so existing assertions (exact coords/timings) hold —
    this is the safety net that keeps the 7823-test baseline green.
    """
    raw = os.environ.get("SENTINEL_HUMANIZE")
    if raw is None:
        return True  # default ON in production
    return raw.strip().lower() in {"1", "on", "true", "yes"}
