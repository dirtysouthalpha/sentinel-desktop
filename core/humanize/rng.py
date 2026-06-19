"""Seeded, reproducible RNG for humanization.

Why this exists:
- Determinism for a fixed seed is required for session replay (forensic log →
  identical humanized paths).
- The deferred adversarial/stealth tier (future-stealth-mode.md) hard-requires
  record/replayable trajectories; the RNG contract is fixed now so that tier
  can slot in without changing call sites.

Contract:
- get_rng(seed=None) -> random.Random — a fresh instance seeded by `seed`.
  When seed is None, the module-level default rng is returned (unchanged).
  Calling get_rng(seed=...) never disturbs the module-level rng state.
- reset(seed=None) -> None — resets the module-level default rng to `seed`.
  seed=None → time-seeded (non-reproducible), used for live runs.
"""

from __future__ import annotations

import random
import time

# Module-level default RNG. Time-seeded at import so live runs are varied;
# tests and replay call reset(seed=...) for determinism.
_default_rng: random.Random = random.Random(time.time())  # noqa: S311


def get_rng(seed: int | None = None) -> random.Random:
    """Return a random.Random.

    Args:
        seed: If given, returns a *new* Random seeded with it (does not touch
            the module-level default rng). If None, returns the shared
            module-level default rng.

    Returns:
        A random.Random instance.
    """
    if seed is not None:
        return random.Random(seed)  # noqa: S311
    return _default_rng


def reset(seed: int | None = None) -> None:
    """Reset the module-level default RNG.

    Args:
        seed: Seed value. None → time-seeded (non-reproducible; for live runs).
    """
    global _default_rng
    _default_rng = random.Random(seed if seed is not None else time.time())  # noqa: S311
