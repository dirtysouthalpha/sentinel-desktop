"""Inertial scroll momentum for stealth-tier humanization.

When a user "flicks" the scroll wheel, the content continues scrolling with
momentum, not a discrete line jump. Mechanical scroll (fixed delta per click)
is robotic and a fingerprint for ML detectors.

This module implements momentum scroll trajectories for StealthProfile,
with exponential decay and per-frame jitter to simulate mechanical imperfection.
"""

from __future__ import annotations

import random

from core.humanize.profile import StealthProfile


def momentum_scroll_trajectory(
    initial_delta_px: int,
    *,
    rng: random.Random,
    profile: StealthProfile,
) -> list[tuple[int, float]]:
    """Generate a momentum scroll trajectory (pixel deltas, frame durations).

    Args:
        initial_delta_px: The initial scroll delta (from scroll wheel event).
        rng: Seeded random.Random.
        profile: StealthProfile with scroll_momentum, scroll_jitter_px.

    Returns:
        List of (delta_px, dwell_s) tuples. Each entry is one scroll "frame":
        - delta_px: Pixels to scroll in this frame (decays over time).
        - dwell_s: How long to wait before the next frame.

    The trajectory follows exponential decay:
        delta[t] = delta[0] * momentum^t

    With per-frame jitter to simulate mechanical imperfection.

    For non-StealthProfile (naturalistic tier), returns a single discrete scroll:
    [(initial_delta_px, 0.0)]
    """
    if not isinstance(profile, StealthProfile):
        # Naturalistic tier: single discrete scroll
        return [(initial_delta_px, 0.0)]

    # Clamp momentum to valid range [0.0, 1.0]
    momentum = max(0.0, min(1.0, profile.scroll_momentum))
    trajectory: list[tuple[int, float]] = []

    current_delta = float(initial_delta_px)
    frame_count = 0

    # Continue until delta < 1px (effectively stopped)
    while abs(current_delta) > 1.0:
        # Add jitter (mechanical imperfection)
        jitter = rng.gauss(0.0, profile.scroll_jitter_px)
        frame_delta = current_delta + jitter

        # Frame dwell: shorter for fast initial frames, longer as we slow down
        # (16ms = 60fps, 33ms = 30fps — human visual smoothness)
        frame_dwell = 0.016 + (frame_count * 0.004)

        trajectory.append((int(frame_delta), frame_dwell))

        # Decay for next frame
        current_delta *= momentum
        frame_count += 1

        # Safety cap: never emit more than 60 frames (1 second of momentum)
        if frame_count >= 60:
            break

    return trajectory
