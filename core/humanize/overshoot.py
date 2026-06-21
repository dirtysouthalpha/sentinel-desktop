"""Overshoot and sweep-back correction for stealth-tier humanization.

Humans don't pixel-perfect targets — especially small ones. We undershoot or
overshoot slightly, then sweep-back with a micro-correction. This natural
behavior is MISSING from the naturalistic tier (which only adds Gaussian
landing jitter).

This module implements the overshoot + correction trajectory generation
for StealthProfile, with probability scaling by target size.
"""

from __future__ import annotations

import math
import random

from core.humanize.profile import StealthProfile


def apply_overshoot_and_correction(
    target: tuple[int, int],
    target_size: tuple[int, int],
    *,
    rng: random.Random,
    profile: StealthProfile,
) -> tuple[tuple[float, float], tuple[float, float] | None]:
    """Generate overshoot/correction trajectory for a single movement.

    Args:
        target: Intended target position (x, y).
        target_size: Target dimensions (width, height) in pixels.
        rng: Seeded random.Random.
        profile: StealthProfile with overshoot_probability.

    Returns:
        (overshoot_landing, correction_target) tuple:
        - overshoot_landing: The point we intentionally miss by (undershoot or overshoot).
        - correction_target: None if no overshoot this time; otherwise the point to
          sweep-back to (typically the true target center).

    Overshoot is MORE likely for small targets:
    - Large targets (>5000 px²): 10% overshoot rate
    - Medium targets (1000-5000 px²): 30% overshoot rate
    - Small targets (<1000 px²): 60% overshoot rate

    Undershoot vs overshoot is 50/50 (humans do both).
    """
    if not isinstance(profile, StealthProfile):
        return (float(target[0]), float(target[1])), None

    target_area = target_size[0] * target_size[1]

    # Small targets → more overshoot
    if target_area < 1000:
        overshoot_prob = 0.60
    elif target_area < 5000:
        overshoot_prob = 0.30
    else:
        overshoot_prob = 0.10

    if rng.random() > overshoot_prob:
        return (float(target[0]), float(target[1])), None

    # Undershoot (short) vs overshoot (long) — 50/50
    is_overshoot = rng.choice([True, False])

    # Magnitude scales with target size (larger targets → larger miss)
    # Typical miss: 5-15px for small targets, 15-30px for large
    miss_magnitude = rng.uniform(5.0, min(target_size[0], target_size[1]) * 0.15)

    # Direction: random angle
    angle = rng.uniform(0.0, 2.0 * math.pi)
    miss_x = math.cos(angle) * miss_magnitude
    miss_y = math.sin(angle) * miss_magnitude

    if is_overshoot:
        # Land beyond the target
        overshoot_landing = (target[0] + miss_x, target[1] + miss_y)
    else:
        # Land short of the target
        overshoot_landing = (target[0] - miss_x, target[1] - miss_y)

    # Correction target: sweep-back to the true target (jittered)
    correction_jitter = rng.gauss(0.0, 2.0)
    correction_target = (target[0] + correction_jitter, target[1] + correction_jitter)

    return overshoot_landing, correction_target
