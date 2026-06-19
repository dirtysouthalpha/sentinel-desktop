"""Action-timing helpers: click hold, think-bump, occasional hesitation.

These are the only timing values the action layer should ever use. The
stealth-readiness rule (see docs/superpowers/specs/2026-06-18-humanization-engine-design.md)
is that NO timing constant lives in action_executor.py — everything flows
through here via the active Profile, so a future StealthProfile can override
globally without touching call sites.

Contract:
- click_hold_duration(*, rng, profile) -> float  : down→up time for a click
- think_bump(*, rng, profile) -> float            : inter-action micro-pause
- maybe_pause(prob=None, *, rng, profile) -> float: 0.0 most of the time,
  occasionally a longer hesitation (simulates a human second-guessing)
"""

from __future__ import annotations

import random

from core.humanize.profile import Profile

# Default chance that maybe_pause() actually pauses (when prob is omitted).
# Kept modest so the agent doesn't constantly stall.
_DEFAULT_PAUSE_PROBABILITY = 0.12

# When a pause DOES fire, it's a "longer hesitation" — a few think-bumps'
# worth up to ~1.5s. This is the human "wait, let me check..." moment.
_HESITATION_RANGE_S = (0.30, 1.50)


def click_hold_duration(*, rng: random.Random, profile: Profile) -> float:
    """Return a click down→up duration (seconds) sampled from the profile.

    Args:
        rng:     Seeded random.Random.
        profile: Tempo profile (uses ``click_hold_s`` (lo, hi) range).

    Returns:
        A duration in [lo, hi].
    """
    lo, hi = profile.click_hold_s
    if hi <= lo:
        return max(0.0, lo)
    return rng.uniform(lo, hi)


def think_bump(*, rng: random.Random, profile: Profile) -> float:
    """Return an inter-action micro-pause (seconds) from the profile.

    Args:
        rng:     Seeded random.Random.
        profile: Tempo profile (uses ``think_bump_s`` (lo, hi) range).

    Returns:
        A pause duration in [lo, hi].
    """
    lo, hi = profile.think_bump_s
    if hi <= lo:
        return max(0.0, lo)
    return rng.uniform(lo, hi)


def maybe_pause(
    prob: float | None = None,
    *,
    rng: random.Random,
    profile: Profile,
) -> float:
    """Return 0.0 most of the time; occasionally a longer hesitation.

    Args:
        prob:    Probability of actually pausing. None → use the module
                 default (_DEFAULT_PAUSE_PROBABILITY).
        rng:     Seeded random.Random.
        profile: Tempo profile (currently informational; hesitation range is
                 fixed but could be made profile-driven later).

    Returns:
        0.0 if no pause this call; otherwise a hesitation duration in
        [_HESITATION_RANGE_S[0], _HESITATION_RANGE_S[1]].
    """
    p = _DEFAULT_PAUSE_PROBABILITY if prob is None else prob
    p = max(0.0, min(1.0, p))
    if p <= 0.0:
        return 0.0
    if rng.random() >= p:
        return 0.0
    lo, hi = _HESITATION_RANGE_S
    return rng.uniform(lo, hi)
