"""Humanized cursor motion: bezier path + eased velocity + imprecise landing.

Contract (curve-agnostic — stealth-readiness):
    humanized_path(start, target, *, rng, profile) -> list[((x, y), dwell_seconds)]

The returned trajectory is a list of (point, dwell) tuples to be replayed as
a sequence of micro-movements. The underlying curve generator is swappable
(bezier now; a future spline or recorded-path generator can replace it) as
long as it produces this same list shape.

Algorithm (naturalistic tier):
- Path: quadratic bezier for short moves, cubic for long moves (bow in two
  directions). Control points pulled off the straight line by
  ``profile.curve_deviation`` and jittered per-move.
- Velocity: eased (ease-in/ease-out) so dwell is longer at the start/end
  (slow) than the middle (fast) — a bell-curve velocity profile. This is the
  opposite of pyautogui's constant-velocity linear moveTo.
- Landing: terminal point = target + Gaussian(0, profile.landing_jitter_px).
  Humans don't pixel-perfect a target.

No new dependencies. Pure math + random.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from typing import TYPE_CHECKING

from core.humanize.profile import Profile

if TYPE_CHECKING:
    from core.humanize.profile import StealthProfile  # noqa: F401

# Distance (in pixels) above which we switch quadratic → cubic.
_CUBIC_THRESHOLD_PX = 400.0

# Distance over which a baseline move takes ~0.3s; used for duration scaling.
_REFERENCE_DISTANCE_PX = 600.0
_BASE_MOVE_S = 0.30  # baseline move duration at the reference distance


def _ease_in_out(t: float) -> float:
    """Smoothstep-like ease-in/ease-out: 0 at t=0, 1 at t=1, slow at both ends.

    Velocity (derivative) peaks at t=0.5 — i.e. the bell-curve profile we want.
    """
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


def _ease_velocity(t: float) -> float:
    """Instantaneous velocity fraction at parameter t.

    Smoothstep derivative: 6t(1−t). Peaks (≈1.5) at t=0.5, →0 at the ends.
    This is the bell curve: slow at start/end, fast in the middle.
    """
    t = max(0.0, min(1.0, t))
    return 6.0 * t * (1.0 - t)


def _quadratic_point(
    p0: tuple[float, float], p1: tuple[float, float], p2: tuple[float, float], t: float
) -> tuple[float, float]:
    """Quadratic bezier point at parameter t ∈ [0, 1]."""
    u = 1.0 - t
    x = u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0]
    y = u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]
    return (x, y)


def _cubic_point(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    """Cubic bezier point at parameter t ∈ [0, 1]."""
    u = 1.0 - t
    x = (u**3) * p0[0] + 3 * (u**2) * t * p1[0] + 3 * u * (t**2) * p2[0] + (t**3) * p3[0]
    y = (u**3) * p0[1] + 3 * (u**2) * t * p1[1] + 3 * u * (t**2) * p2[1] + (t**3) * p3[1]
    return (x, y)


def _control_point(
    start: tuple[float, float],
    target: tuple[float, float],
    rng: random.Random,
    deviation: float,
    t_at: float,
) -> tuple[float, float]:
    """Build a control point on the perpendicular at parameter position t_at.

    The control point sits on the line through the start→target point at
    fraction t_at, displaced perpendicular by a random signed amount scaled
    by `deviation` and the move length.
    """
    sx, sy = start
    tx, ty = target
    dx, dy = tx - sx, ty - sy
    length = math.hypot(dx, dy)
    if length == 0:
        return start
    # Point on the line at t_at.
    base_x = sx + dx * t_at
    base_y = sy + dy * t_at
    # Perpendicular unit vector.
    nx, ny = -dy / length, dx / length
    # Signed displacement: a fraction of the move length, jittered.
    # Scale magnitude with deviation and move length (longer moves bow more).
    magnitude = length * 0.15 * deviation * rng.uniform(0.6, 1.4)
    sign = rng.choice((-1.0, 1.0))
    return (base_x + nx * magnitude * sign, base_y + ny * magnitude * sign)


def _build_curve(
    start: tuple[float, float], target: tuple[float, float], rng: random.Random, deviation: float
) -> tuple[Sequence[tuple[float, float]], int]:
    """Pick quadratic or cubic based on distance; return control points + degree."""
    length = math.hypot(target[0] - start[0], target[1] - start[1])
    if length >= _CUBIC_THRESHOLD_PX:
        c1 = _control_point(start, target, rng, deviation, t_at=0.33)
        c2 = _control_point(start, target, rng, deviation, t_at=0.66)
        return (start, c1, c2, target), 3
    c1 = _control_point(start, target, rng, deviation, t_at=0.5)
    return (start, c1, target), 2


def _curve_point(
    points: Sequence[tuple[float, float]], degree: int, t: float
) -> tuple[float, float]:
    if degree == 3:
        return _cubic_point(points[0], points[1], points[2], points[3], t)
    return _quadratic_point(points[0], points[1], points[2], t)


def _sample_count(length: float) -> int:
    """Number of waypoints scales with distance (longer moves get more samples)."""
    # Floor of 8 (so easing is observable), grows ~linearly with distance.
    n = int(8 + length / 25.0)
    return min(n, 240)


def _total_duration(length: float, profile: Profile) -> float:
    """Distance-scaled total move time with diminishing returns + jitter-free base.

    Fitts-ish (distance only; target-width timing is stealth-tier, deferred).
    """
    # Scaled, sub-linear in distance so very long moves don't take forever.
    scaled = (length / _REFERENCE_DISTANCE_PX) ** 0.85
    return _BASE_MOVE_S * (0.4 + scaled) * profile.move_speed


def humanized_path(
    start: tuple[int, int],
    target: tuple[int, int],
    target_size: tuple[int, int] | None = None,
    *,
    rng: random.Random,
    profile: Profile,
) -> list[tuple[tuple[float, float], float]]:
    """Return [(point, dwell_seconds), ...] — the humanized cursor trajectory.

    Each entry is a screen position and how long to dwell before the next.
    The trajectory is generated from a (quadratic|cubic) bezier with eased
    timing and a slightly-off terminal point.

    Args:
        start:  Current cursor position (x, y).
        target: Intended target (x, y).
        target_size: Optional target dimensions (width, height) in pixels for
                stealth-tier Fitts's-Law timing and overshoot/correction.
        rng:    Seeded random.Random (use core.humanize.rng.get_rng for the
                shared default; pass a seeded one for replay).
        profile: Tempo profile (see core.humanize.profile).

    Returns:
        List of ((x, y), dwell_seconds). For a zero-distance move, returns a
        single point at the (jittered) target with zero dwell, or an empty
        list if the jittered target coincides with the start.
    """
    sx_f, sy_f = float(start[0]), float(start[1])
    tx_f, ty_f = float(target[0]), float(target[1])
    length = math.hypot(tx_f - sx_f, ty_f - sy_f)

    # Imprecise landing: the curve terminates near, not exactly on, the target.
    jx = rng.gauss(0.0, profile.landing_jitter_px)
    jy = rng.gauss(0.0, profile.landing_jitter_px)
    land_x, land_y = tx_f + jx, ty_f + jy

    # Degenerate (zero-distance) move: nothing to animate.
    if length < 0.5:
        # Only emit a point if we actually landed somewhere different.
        if math.hypot(land_x - sx_f, land_y - sy_f) < 0.5:
            return []
        return [((land_x, land_y), 0.0)]

    # Check for overshoot + correction trajectory for StealthProfile
    # This must happen BEFORE building the curve so we can generate a two-segment path
    overshoot_landing = None
    correction_target = None

    if target_size and _is_stealth_profile(profile):
        from core.humanize.overshoot import apply_overshoot_and_correction

        overshoot_landing, correction_target = apply_overshoot_and_correction(
            target,
            target_size,
            rng=rng,
            profile=profile,  # type: ignore[arg-type]
        )

    # Build the curve to the landing point (overshoot point if applicable)
    actual_target = overshoot_landing if overshoot_landing else (land_x, land_y)
    points, degree = _build_curve((sx_f, sy_f), actual_target, rng, profile.curve_deviation)
    n = _sample_count(length)

    # Calculate total duration with Fitts's-Law for StealthProfile if target_size is known
    if target_size and _is_stealth_profile(profile):
        from core.humanize.fitts import fitts_move_duration

        total = fitts_move_duration(start, target, target_size, rng=rng, profile=profile)  # type: ignore[arg-type]
    else:
        total = _total_duration(length, profile)

    # Build trajectory (single-segment or two-segment for overshoot + correction)
    if correction_target is not None:
        # TWO movements: start → overshoot → correction
        # Segment 1: start → overshoot_landing
        trajectory_segment_1 = _build_trajectory_from_curve(
            start, actual_target, length, total, points, degree, n, rng, profile
        )

        # Tiny dwell at overshoot point (human reorients)
        trajectory_segment_1.append(((actual_target[0], actual_target[1]), 0.02))

        # Segment 2: overshoot → correction_target
        # Re-calculate curve and duration for correction move
        cor_length = math.hypot(
            correction_target[0] - actual_target[0], correction_target[1] - actual_target[1]
        )
        cor_points, cor_degree = _build_curve(
            actual_target, correction_target, rng, profile.curve_deviation
        )
        cor_n = _sample_count(cor_length)
        # Correction is faster (sweep-back)
        cor_total = total * profile.sweep_back_speed  # type: ignore[attr-defined]

        trajectory_segment_2 = _build_trajectory_from_curve(
            actual_target,
            correction_target,
            cor_length,
            cor_total,
            cor_points,
            cor_degree,
            cor_n,
            rng,
            profile,
        )

        # Combine segments
        trajectory = trajectory_segment_1 + trajectory_segment_2
    else:
        # Single-segment trajectory
        trajectory = _build_trajectory_from_curve(
            start, actual_target, length, total, points, degree, n, rng, profile
        )

    # Final dwell (after the last waypoint) is intentionally 0 — the click
    # handler inserts its own hold duration via humanize.timing.
    return trajectory


def _is_stealth_profile(profile: Profile) -> bool:
    """Check if a profile is a StealthProfile (type-check compatible)."""
    # Avoid circular import by checking attribute instead of isinstance
    return hasattr(profile, "fitts_width_scaling")


def _build_trajectory_from_curve(
    start: tuple[int, int],
    target: tuple[float, float],
    length: float,
    total: float,
    points: Sequence[tuple[float, float]],
    degree: int,
    n: int,
    rng: random.Random,
    profile: Profile,
) -> list[tuple[tuple[float, float], float]]:
    """Build a single trajectory segment from curve parameters.

    Args:
        start: Current cursor position (x, y).
        target: Target position (x, y).
        length: Distance in pixels.
        total: Total duration for the move.
        points: Control points for the curve.
        degree: Curve degree (2 for quadratic, 3 for cubic).
        n: Number of samples.
        rng: Seeded random.Random.
        profile: Tempo profile.

    Returns:
        List of ((x, y), dwell_seconds) trajectory points.
    """
    trajectory: list[tuple[tuple[float, float], float]] = []
    # Bell-curve velocity via INVERSE-easing: with N spatially-uniform samples,
    # the time spent dwelling at each sample is inversely proportional to the
    # local eased velocity. Where velocity is high (middle), each sample is
    # passed quickly → small dwell. Where velocity is low (ends), the cursor
    # lingers → large dwell. This produces the desired slow-fast-slow profile.
    weights: list[float] = []
    for i in range(n):
        t_param = i / (n - 1) if n > 1 else 1.0
        v = _ease_velocity(t_param)
        # Floor velocity to avoid div-by-zero at the exact endpoints (v=0 at
        # t=0 and t=1); use a small epsilon so endpoints still get a finite,
        # large dwell rather than infinite.
        weights.append(1.0 / (v + 0.15))
    weight_sum = sum(weights)
    for i in range(n):
        t_param = i / (n - 1) if n > 1 else 1.0
        pt = _curve_point(points, degree, t_param)
        dwell = (weights[i] / weight_sum) * total if weight_sum > 0 else 0.0
        trajectory.append((pt, dwell))
    return trajectory
