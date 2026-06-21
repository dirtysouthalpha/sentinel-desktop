"""Tests for core/humanize/fitts.py — Fitts's-Law targeting time.

Covers the spec's required test list:
- ID (Index of Difficulty) computation is correct
- duration scales with distance AND target width (small targets → longer time)
- zero-distance moves return base intercept time
- tiny targets (< 5px) are clamped to avoid division issues
- StealthProfile uses Fittsian timing, non-StealthProfile falls back
- same seed → same duration (determinism)
- duration is always non-negative
"""

from __future__ import annotations

import math
import random

from core.humanize.fitts import fitts_move_duration
from core.humanize.profile import NATURALISTIC, STEALTH, StealthProfile


class TestIDComputation:
    """Index of Difficulty (ID) = log2(2 * distance / width)."""

    def test_id_increases_with_distance(self):
        """For a fixed target width, ID should increase as distance increases."""
        profile = STEALTH
        rng = random.Random(1)

        target_size = (50, 50)  # 50px effective width
        start = (0, 0)

        # Short distance
        dur_short = fitts_move_duration(start, (100, 0), target_size, rng=rng, profile=profile)

        # Long distance (same seed for deterministic jitter)
        rng = random.Random(1)
        dur_long = fitts_move_duration(start, (1000, 0), target_size, rng=rng, profile=profile)

        # Longer distance should produce longer duration (higher ID)
        assert dur_long > dur_short, f"ID didn't increase: short={dur_short}, long={dur_long}"

    def test_id_increases_as_width_decreases(self):
        """For a fixed distance, ID should increase as target width decreases."""
        profile = STEALTH
        rng = random.Random(1)

        start = (0, 0)
        target = (500, 0)

        # Large target
        rng = random.Random(1)
        dur_large = fitts_move_duration(start, target, (100, 100), rng=rng, profile=profile)

        # Small target (same seed for deterministic jitter)
        rng = random.Random(1)
        dur_small = fitts_move_duration(start, target, (10, 10), rng=rng, profile=profile)

        # Smaller target should produce longer duration (higher ID)
        assert dur_small > dur_large, f"ID didn't increase with smaller width: large={dur_large}, small={dur_small}"

    def test_id_uses_min_dimension_for_rectangles(self):
        """For rectangular targets, width = min(width, height)."""
        profile = STEALTH
        rng = random.Random(1)

        start = (0, 0)
        target = (500, 0)

        # Wide rectangle (200x20) — effective width = 20
        rng = random.Random(1)
        dur_wide = fitts_move_duration(start, target, (200, 20), rng=rng, profile=profile)

        # Square (20x20) — effective width = 20 (same as wide rectangle)
        rng = random.Random(1)
        dur_square = fitts_move_duration(start, target, (20, 20), rng=rng, profile=profile)

        # Should be nearly identical (same effective width)
        assert abs(dur_wide - dur_square) < 0.001, f"ID should use min dimension: wide={dur_wide}, square={dur_square}"


class TestDurationScaling:
    """Duration = a + b * ID, where b scales with profile.fitts_width_scaling."""

    def test_duration_scales_with_fitts_width_scaling(self):
        """Higher fitts_width_scaling should produce longer durations."""
        rng = random.Random(1)

        start = (0, 0)
        target = (500, 0)
        target_size = (50, 50)

        # Low scaling
        profile_low = StealthProfile(name="test_low", fitts_width_scaling=1.0)
        rng = random.Random(1)
        dur_low = fitts_move_duration(start, target, target_size, rng=rng, profile=profile_low)

        # High scaling
        profile_high = StealthProfile(name="test_high", fitts_width_scaling=3.0)
        rng = random.Random(1)
        dur_high = fitts_move_duration(start, target, target_size, rng=rng, profile=profile_high)

        # Higher scaling should produce longer duration
        assert dur_high > dur_low, f"Scaling didn't affect duration: low={dur_low}, high={dur_high}"

    def test_fitts_coefficients_are_reasonable(self):
        """The base coefficients (a=0.05s, b≈0.10s) should produce reasonable durations."""
        profile = STEALTH  # fitts_width_scaling = 2.0
        rng = random.Random(1)

        # Typical move: 500px distance, 50px target
        start = (0, 0)
        target = (500, 0)
        target_size = (50, 50)

        duration = fitts_move_duration(start, target, target_size, rng=rng, profile=profile)

        # Should be somewhere in a human range (not too fast, not too slow)
        # ID = log2(2 * 500 / 50) = log2(20) ≈ 4.32
        # time ≈ 0.05 + 0.10 * 2.0 * 4.32 ≈ 0.05 + 0.864 ≈ 0.91s
        assert 0.1 <= duration <= 3.0, f"Duration out of human range: {duration}s"


class TestEdgeCases:
    """Tiny targets, zero distance, clamp bounds."""

    def test_tiny_target_clamped_to_minimum(self):
        """Targets smaller than 5px should be clamped to avoid division issues."""
        profile = STEALTH
        rng = random.Random(1)

        start = (0, 0)
        target = (500, 0)

        # 1px target (should be clamped to 5px)
        rng = random.Random(1)
        dur_1px = fitts_move_duration(start, target, (1, 1), rng=rng, profile=profile)

        # 5px target (minimum clamp)
        rng = random.Random(1)
        dur_5px = fitts_move_duration(start, target, (5, 5), rng=rng, profile=profile)

        # Should be nearly identical (both clamped to 5px effective width)
        assert abs(dur_1px - dur_5px) < 0.001, f"Tiny target wasn't clamped: 1px={dur_1px}, 5px={dur_5px}"

    def test_zero_distance_returns_base_intercept(self):
        """Zero-distance moves should return the base intercept time (a) + jitter."""
        profile = STEALTH
        rng = random.Random(1)

        start = (100, 100)
        target = (100, 100)  # Same position
        target_size = (50, 50)

        duration = fitts_move_duration(start, target, target_size, rng=rng, profile=profile)

        # Should be close to base intercept (0.05s) + small jitter
        # Jitter is Gaussian(0, 0.02), so range ~0.01-0.09s
        assert 0.01 <= duration <= 0.15, f"Zero-distance duration out of range: {duration}s"

    def test_duration_never_negative(self):
        """Duration should always be non-negative (max with 0.0)."""
        profile = STEALTH
        rng = random.Random(1)

        # Even with extreme jitter (which could be negative), result should be >= 0
        for i in range(100):
            duration = fitts_move_duration(
                (0, 0), (10, 0), (5, 5), rng=rng, profile=profile
            )
            assert duration >= 0.0, f"Negative duration: {duration}s"

    def test_very_small_nonzero_distance_handled(self):
        """Distance < 0.5px but > 0 should be treated as zero-distance."""
        profile = STEALTH
        rng = random.Random(1)

        start = (100, 100)
        target = (100.2, 100.1)  # ~0.22px distance
        target_size = (50, 50)

        duration = fitts_move_duration(start, target, target_size, rng=rng, profile=profile)

        # Should return base intercept time (not crash or return huge duration)
        assert 0.01 <= duration <= 0.15, f"Tiny distance not handled: {duration}s"


class TestProfileFallback:
    """Non-StealthProfile should fall back to distance-only naturalistic timing."""

    def test_non_stealth_profile_falls_back(self):
        """NATURALISTIC profile should use distance-only timing from motion.py."""
        profile = NATURALISTIC
        rng = random.Random(1)

        start = (0, 0)
        target = (500, 0)
        target_size = (50, 50)

        # Should not crash; should return a duration
        duration = fitts_move_duration(start, target, target_size, rng=rng, profile=profile)

        # Should be positive and reasonable
        assert duration > 0.0
        assert duration < 5.0

    def test_target_size_ignored_for_naturalistic(self):
        """For NATURALISTIC profile, target_size should not affect duration."""
        profile = NATURALISTIC
        rng = random.Random(1)

        start = (0, 0)
        target = (500, 0)

        # Large target
        rng = random.Random(1)
        dur_large = fitts_move_duration(start, target, (100, 100), rng=rng, profile=profile)

        # Small target (same distance, different target_size)
        rng = random.Random(1)
        dur_small = fitts_move_duration(start, target, (10, 10), rng=rng, profile=profile)

        # Should be identical (target_size ignored for naturalistic)
        assert dur_large == dur_small, f"target_size should be ignored for NATURALISTIC: large={dur_large}, small={dur_small}"


class TestDeterminism:
    """Same seed → same duration (reproducibility for session replay)."""

    def test_same_seed_same_duration(self):
        """Deterministic RNG state should produce identical durations."""
        profile = STEALTH

        dur1 = fitts_move_duration((0, 0), (500, 0), (50, 50), rng=random.Random(42), profile=profile)
        dur2 = fitts_move_duration((0, 0), (500, 0), (50, 50), rng=random.Random(42), profile=profile)

        assert dur1 == dur2, f"Same seed produced different durations: {dur1} vs {dur2}"

    def test_different_seeds_different_durations(self):
        """Different RNG states should (almost always) produce different durations."""
        profile = STEALTH

        dur1 = fitts_move_duration((0, 0), (500, 0), (50, 50), rng=random.Random(1), profile=profile)
        dur2 = fitts_move_duration((0, 0), (500, 0), (50, 50), rng=random.Random(2), profile=profile)

        # With jitter, different seeds should produce different results
        assert dur1 != dur2, f"Different seeds produced identical durations: {dur1}"

    def test_repeated_calls_vary(self):
        """Repeated calls with fresh seeds should (almost always) vary."""
        profile = STEALTH

        durations = [
            fitts_move_duration((0, 0), (500, 0), (50, 50), rng=random.Random(i), profile=profile)
            for i in range(20)
        ]

        # Not all identical (at least some variation due to jitter)
        unique_count = len(set(durations))
        assert unique_count >= 15, f"Too little variation: {unique_count}/20 unique"


class TestContract:
    """Function signature and return type."""

    def test_returns_float(self):
        """Should return a float (duration in seconds)."""
        profile = STEALTH
        rng = random.Random(1)

        duration = fitts_move_duration((0, 0), (500, 0), (50, 50), rng=rng, profile=profile)

        assert isinstance(duration, float)

    def test_accepts_integer_and_float_positions(self):
        """Start and target can be integers; function handles float conversion."""
        profile = STEALTH
        rng = random.Random(1)

        # Integer positions
        dur1 = fitts_move_duration((0, 0), (500, 0), (50, 50), rng=rng, profile=profile)

        # Should not crash or return NaN/inf
        assert math.isfinite(dur1)
        assert dur1 > 0
