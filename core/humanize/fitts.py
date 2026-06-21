"""Fitts's-Law targeting time for stealth-tier humanization.

Fitts's Law states that movement time depends on BOTH distance AND target width:
    time = a + b * ID
    ID = log2(2 * distance / target_width)

Small targets (e.g., 16×16 icon) require longer, more careful movements than large
targets (e.g., 200×40 button), even at the same distance. This is a key signal that
ML-based anti-bot detectors use to flag robotic input.

The naturalistic tier (motion.py._total_duration) uses distance-only timing.
This module adds target-width sensitivity for the stealth tier.

No new dependencies. Pure math + random.
"""

from __future__ import annotations

import math
import random

from core.humanize.motion import _total_duration
from core.humanize.profile import Profile, StealthProfile


def fitts_move_duration(
    start: tuple[int, int],
    target: tuple[int, int],
    target_size: tuple[int, int],
    *,
    rng: random.Random,
    profile: Profile,
) -> float:
    """Return movement duration (seconds) from Fitts's Law.

    Args:
        start: Current cursor position (x, y).
        target: Intended target position (x, y).
        target_size: Target dimensions (width, height) in pixels.
        rng: Seeded random.Random (use core.humanize.rng.get_rng for the
                shared default; pass a seeded one for replay).
        profile: Tempo profile (must be StealthProfile for Fitts's-Law).

    Returns:
        Duration in seconds. Falls back to distance-only timing if profile
        is not a StealthProfile.

    Algorithm:
        1. Compute effective width = min(target_width, target_height)
        2. Clamp width to minimum 5px to avoid pathological values
        3. Compute distance via Euclidean distance
        4. Compute Index of Difficulty: ID = log2(2 * distance / width)
        5. Apply Fitts's-Law: time = a + b * ID + jitter
           - a ≈ 0.05s (intercept, fixed start-up cost)
           - b ≈ 0.10s * fitts_width_scaling (slope, from profile)
           - jitter ≈ Gaussian(0, 0.02s) for realism

    Edge cases:
        - Zero distance: returns base intercept time (a) + jitter
        - Tiny target (< 5px): clamped to 5px to avoid division issues
        - Non-StealthProfile: falls back to distance-only naturalistic timing
    """
    # Fall back to naturalistic timing for non-stealth profiles
    if not isinstance(profile, StealthProfile):
        distance_px = math.hypot(target[0] - start[0], target[1] - start[1])
        return _total_duration(distance_px, profile)

    # Compute effective width (smaller dimension for rectangular targets)
    width = float(min(target_size[0], target_size[1]))

    # Clamp to minimum to avoid pathological values for tiny targets
    width = max(width, 5.0)

    # Compute distance
    distance_px = math.hypot(target[0] - start[0], target[1] - start[1])

    # Zero-distance move: return base intercept time
    if distance_px < 0.5:
        jitter = rng.gauss(0.0, 0.02)
        return max(0.0, 0.05 + jitter)

    # Index of Difficulty (Fitts's ID)
    # ID = log2(2 * distance / width)
    id = math.log2(2.0 * distance_px / width)

    # Fitts's-Law coefficients
    # a: intercept (fixed start-up cost, ~0.05s from biometric samples)
    # b: slope (sensitivity to ID, scaled by profile's width_scaling factor)
    a = 0.05
    b = 0.10 * profile.fitts_width_scaling

    # Add jitter (humans aren't perfectly Fittsian)
    jitter = rng.gauss(0.0, 0.02)

    # Return non-negative duration
    return max(0.0, a + b * id + jitter)
