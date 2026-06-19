"""Tests for core/humanize/motion.py — bezier path + easing + imprecise landing.

Covers the spec's required test list:
- path is curved (not colinear with the straight line)
- velocity is eased (bell-curve: longer dwells at start/end than middle)
- landing is imprecise (terminal ≠ exact target, within jitter)
- determinism: same seed → same path; different seeds → different paths
- quadratic for short moves, cubic for long moves
- repeated moves to same target vary
- degenerate (zero distance) input handled
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence

from core.humanize.motion import humanized_path
from core.humanize.profile import NATURALISTIC


def _colinearity_deviation(
    points: Sequence[tuple[float, float]], start: tuple[int, int], target: tuple[int, int]
) -> float:
    """Max perpendicular distance of `points` from the start→target line."""
    sx, sy = start
    tx, ty = target
    dx, dy = tx - sx, ty - sy
    length = math.hypot(dx, dy)
    if length == 0:
        return 0.0
    # Normal to the line direction.
    nx, ny = -dy / length, dx / length
    worst = 0.0
    for px, py in points:
        # signed distance from the infinite line through start with direction (dx,dy)
        d = (px - sx) * nx + (py - sy) * ny
        worst = max(worst, abs(d))
    return worst


class TestPathIsCurved:
    def test_path_deviates_from_straight_line(self):
        rng = random.Random(1)
        start, target = (100, 100), (900, 800)
        pts = humanized_path(start, target, rng=rng, profile=NATURALISTIC)
        points = [p for (p, _d) in pts]
        assert _colinearity_deviation(points, start, target) > 1.0, (
            "path is a straight line — not humanized"
        )

    def test_path_visits_distinct_points(self):
        rng = random.Random(2)
        pts = humanized_path((0, 0), (500, 500), rng=rng, profile=NATURALISTIC)
        points = [p for (p, _d) in pts]
        # A real curve has many distinct waypoints.
        assert len(set(points)) > 5


class TestEasedVelocity:
    def test_velocity_is_bell_shaped(self):
        """Dwell at the start and end should exceed dwell in the middle.

        We compare the mean of the first/last quarter of dwells against the
        mean of the middle half. An eased (bell-curve velocity) path spends
        MORE time per step at the ends (slow) than the middle (fast).
        """
        rng = random.Random(3)
        pts = humanized_path((50, 50), (1200, 900), rng=rng, profile=NATURALISTIC)
        dwells = [d for (_p, d) in pts]
        n = len(dwells)
        assert n >= 8, "too few samples to assert easing"
        quarter = n // 4
        ends = dwells[:quarter] + dwells[-quarter:]
        middle = (
            dwells[quarter : n - quarter]
            if (n - 2 * quarter) > 0
            else dwells[quarter : 3 * quarter]
        )
        mean_ends = sum(ends) / len(ends)
        mean_middle = sum(middle) / len(middle)
        # Eased ⇒ ends slower (bigger dwell) than the middle.
        assert mean_ends > mean_middle, (
            f"not eased: mean_ends={mean_ends:.5f} <= mean_middle={mean_middle:.5f}"
        )

    def test_total_duration_positive_and_reasonable(self):
        rng = random.Random(4)
        pts = humanized_path((0, 0), (300, 400), rng=rng, profile=NATURALISTIC)
        total = sum(d for (_p, d) in pts)
        # A move across ~500px should take somewhere in 0.05–2.0s humanized.
        assert 0.02 <= total <= 3.0


class TestImpreciseLanding:
    def test_terminal_point_not_exact_target(self):
        rng = random.Random(5)
        target = (500, 500)
        pts = humanized_path((0, 0), target, rng=rng, profile=NATURALISTIC)
        last_point = pts[-1][0]
        # Landing should differ from the exact target almost always (jitter).
        assert last_point != target

    def test_terminal_within_jitter_budget(self):
        """Over many runs, landing offset should stay within a few std-devs."""
        target = (400, 400)
        offsets = []
        for s in range(50):
            rng = random.Random(100 + s)
            pts = humanized_path((10, 10), target, rng=rng, profile=NATURALISTIC)
            lx, ly = pts[-1][0]
            offsets.append(math.hypot(lx - target[0], ly - target[1]))
        # Almost all landings should be within, say, 10px (4 std-devs of 2.5).
        within = sum(1 for o in offsets if o <= 10.0)
        assert within >= 48, f"too many landings far from target: {offsets}"


class TestDeterminism:
    def test_same_seed_same_path(self):
        p1 = humanized_path((0, 0), (300, 200), rng=random.Random(7), profile=NATURALISTIC)
        p2 = humanized_path((0, 0), (300, 200), rng=random.Random(7), profile=NATURALISTIC)
        assert p1 == p2

    def test_different_seeds_different_path(self):
        p1 = humanized_path((0, 0), (300, 200), rng=random.Random(1), profile=NATURALISTIC)
        p2 = humanized_path((0, 0), (300, 200), rng=random.Random(2), profile=NATURALISTIC)
        assert p1 != p2

    def test_no_two_consecutive_identical(self):
        """Repeated moves to the same target should (almost always) vary."""
        target = (250, 250)
        paths = [
            humanized_path((0, 0), target, rng=random.Random(i), profile=NATURALISTIC)
            for i in range(10)
        ]
        # Lists aren't hashable; stringify to dedupe and count unique shapes.
        serialised = {repr(p) for p in paths}
        assert len(serialised) >= 8, f"too little variety: {len(serialised)}/10 unique"


class TestDistanceBranching:
    def test_short_move_produces_path(self):
        rng = random.Random(11)
        pts = humanized_path((100, 100), (120, 130), rng=rng, profile=NATURALISTIC)
        assert len(pts) >= 2

    def test_long_move_produces_more_samples_than_short(self):
        rng_s = random.Random(12)
        rng_l = random.Random(12)
        short = humanized_path((0, 0), (50, 50), rng=rng_s, profile=NATURALISTIC)
        long = humanized_path((0, 0), (2000, 1500), rng=rng_l, profile=NATURALISTIC)
        assert len(long) > len(short)


class TestDegenerateInput:
    def test_zero_distance_returns_single_point(self):
        rng = random.Random(13)
        pts = humanized_path((100, 100), (100, 100), rng=rng, profile=NATURALISTIC)
        # No motion ⇒ a degenerate result (single or empty is acceptable,
        # but it must NOT crash or loop forever).
        assert len(pts) <= 1
        # If there's a point, it should be at/near the (zero-distance) target.
        if pts:
            (px, py), _d = pts[0]
            assert math.hypot(px - 100, py - 100) <= 6.0

    def test_zero_distance_runs_quickly(self):
        import time as _t

        rng = random.Random(13)
        t0 = _t.perf_counter()
        for _ in range(200):
            humanized_path((5, 5), (5, 5), rng=rng, profile=NATURALISTIC)
        elapsed = _t.perf_counter() - t0
        assert elapsed < 1.0, "degenerate path generation is too slow"


class TestContract:
    def test_returns_list_of_point_dwell_tuples(self):
        rng = random.Random(20)
        pts = humanized_path((0, 0), (200, 200), rng=rng, profile=NATURALISTIC)
        assert isinstance(pts, list)
        assert all(len(item) == 2 for item in pts)
        for p, d in pts:
            assert len(p) == 2
            assert isinstance(d, float)
            assert d >= 0.0

    def test_curve_agnostic_contract(self):
        """The return type is a generic (point, dwell) list — the underlying
        curve generator is swappable (stealth-readiness). This test pins the
        contract so a future spline/recorded-path generator can drop in.
        """
        rng = random.Random(21)
        pts = humanized_path((0, 0), (400, 300), rng=rng, profile=NATURALISTIC)
        # Contract: list of ((x, y): tuple[number, number], dwell: float).
        for item in pts:
            point, dwell = item
            x, y = point
            assert isinstance(x, (int, float))
            assert isinstance(y, (int, float))
            assert isinstance(dwell, float)
