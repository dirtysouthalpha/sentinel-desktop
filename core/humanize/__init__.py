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
"""

from __future__ import annotations

__all__: list[str] = []
