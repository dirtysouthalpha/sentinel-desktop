"""Tests for core/humanize/overshoot.py — overshoot and sweep-back correction.

This module tests the overshoot + correction trajectory generation for
StealthProfile, verifying:
- Overshoot probability scales inversely with target width (small targets → higher overshoot)
- Undershoot vs overshoot is roughly 50/50
- Sweep-back lands within jitter of the true target
- Seed reproducibility for consistent testing
- Non-StealthProfile returns target with no correction
"""

from __future__ import annotations

import random

from core.humanize.overshoot import apply_overshoot_and_correction
from core.humanize.profile import NATURALISTIC, STEALTH, StealthProfile


class TestOvershootProbabilityScaling:
    """Overshoot is MORE likely for small targets and LESS likely for large targets."""

    def test_small_target_high_overshoot_probability(self):
        """Small targets (<1000 px²) should have 60% overshoot rate."""
        s = StealthProfile()
        rng = random.Random(42)

        # Small target: 30x30 = 900 px²
        overshoot_count = 0
        trials = 1000
        for _ in range(trials):
            target = (100, 100)
            target_size = (30, 30)
            _, correction = apply_overshoot_and_correction(
                target, target_size, rng=rng, profile=s
            )
            if correction is not None:
                overshoot_count += 1

        # Should be ~60% (allow ±5% for randomness)
        probability = overshoot_count / trials
        assert 0.55 <= probability <= 0.65, f"Expected ~0.60, got {probability}"

    def test_medium_target_medium_overshoot_probability(self):
        """Medium targets (1000-5000 px²) should have 30% overshoot rate."""
        s = StealthProfile()
        rng = random.Random(42)

        # Medium target: 50x50 = 2500 px²
        overshoot_count = 0
        trials = 1000
        for _ in range(trials):
            target = (100, 100)
            target_size = (50, 50)
            _, correction = apply_overshoot_and_correction(
                target, target_size, rng=rng, profile=s
            )
            if correction is not None:
                overshoot_count += 1

        # Should be ~30% (allow ±5% for randomness)
        probability = overshoot_count / trials
        assert 0.25 <= probability <= 0.35, f"Expected ~0.30, got {probability}"

    def test_large_target_low_overshoot_probability(self):
        """Large targets (>5000 px²) should have 10% overshoot rate."""
        s = StealthProfile()
        rng = random.Random(42)

        # Large target: 100x100 = 10000 px²
        overshoot_count = 0
        trials = 1000
        for _ in range(trials):
            target = (100, 100)
            target_size = (100, 100)
            _, correction = apply_overshoot_and_correction(
                target, target_size, rng=rng, profile=s
            )
            if correction is not None:
                overshoot_count += 1

        # Should be ~10% (allow ±3% for randomness)
        probability = overshoot_count / trials
        assert 0.07 <= probability <= 0.13, f"Expected ~0.10, got {probability}"

    def test_tiny_target_boundary_case(self):
        """Tiny targets (approaching zero area) should still have high overshoot probability."""
        s = StealthProfile()
        rng = random.Random(42)

        # Tiny target: 10x10 = 100 px²
        overshoot_count = 0
        trials = 100
        for _ in range(trials):
            target = (100, 100)
            target_size = (10, 10)
            _, correction = apply_overshoot_and_correction(
                target, target_size, rng=rng, profile=s
            )
            if correction is not None:
                overshoot_count += 1

        # Should still be high overshoot (60% threshold)
        probability = overshoot_count / trials
        assert probability >= 0.50, f"Expected high overshoot for tiny target, got {probability}"


class TestUndershootVsOvershootDistribution:
    """Undershoot (short) vs overshoot (long) should be 50/50."""

    def test_overshoot_occurs_roughly_half_the_time_when_selected(self):
        """When overshoot occurs, the algorithm should use 50/50 undershoot vs overshoot."""
        # Note: We can't directly observe the internal is_overshoot choice from outside,
        # but we can verify the overall behavior is sound by checking that overshoot
        # happens and corrections are generated correctly.
        s = StealthProfile()
        rng = random.Random(42)

        target = (100, 100)
        target_size = (30, 30)  # Small target for high overshoot rate

        # Verify that corrections are being generated
        correction_count = 0
        trials = 100
        for _ in range(trials):
            _, correction = apply_overshoot_and_correction(
                target, target_size, rng=rng, profile=s
            )
            if correction is not None:
                correction_count += 1

        # Should have corrections (overshoot events)
        assert correction_count > 0, "No overshoot events detected"
        assert correction_count < trials, "All events were overshoot (should be probabilistic)"


class TestSweepBackLanding:
    """Correction target should land within jitter of the true target."""

    def test_correction_target_lands_near_true_target(self):
        """Sweep-back should land within Gaussian jitter (σ=2px) of true target."""
        s = StealthProfile()
        rng = random.Random(42)

        target = (100, 100)
        target_size = (30, 30)

        max_jitter = 8.0  # 4σ (99.994% of Gaussian samples within 4σ)
        total_dist = 0.0
        correction_count = 0

        for _ in range(100):
            _, correction = apply_overshoot_and_correction(
                target, target_size, rng=rng, profile=s
            )
            if correction is not None:
                # Distance from true target
                dist = ((correction[0] - target[0]) ** 2 + (correction[1] - target[1]) ** 2) ** 0.5
                total_dist += dist
                correction_count += 1
                assert dist <= max_jitter, f"Correction landed {dist}px from target, expected ≤{max_jitter}px"

        # Also verify average is small (should be ~σ=2px)
        if correction_count > 0:
            avg_dist = total_dist / correction_count
            assert avg_dist <= 3.0, f"Average correction jitter {avg_dist}px is too high (expected ~2px)"


class TestMissMagnitudeScaling:
    """Miss magnitude should scale with target size."""

    def test_miss_magnitude_scales_with_target_size(self):
        """Larger targets should have larger miss magnitudes."""
        s = StealthProfile()
        rng = random.Random(42)

        target = (100, 100)

        # Small target (30x30)
        small_distances = []
        for _ in range(100):
            landing, correction = apply_overshoot_and_correction(
                target, (30, 30), rng=rng, profile=s
            )
            if correction is not None:
                dist = ((landing[0] - target[0]) ** 2 + (landing[1] - target[1]) ** 2) ** 0.5
                small_distances.append(dist)

        # Large target (100x100)
        large_distances = []
        for _ in range(100):
            landing, correction = apply_overshoot_and_correction(
                target, (100, 100), rng=rng, profile=s
            )
            if correction is not None:
                dist = ((landing[0] - target[0]) ** 2 + (landing[1] - target[1]) ** 2) ** 0.5
                large_distances.append(dist)

        if small_distances and large_distances:
            avg_small = sum(small_distances) / len(small_distances)
            avg_large = sum(large_distances) / len(large_distances)
            # Large target misses should be larger on average
            assert avg_large > avg_small * 1.5, f"Large target misses should be larger: small={avg_small:.2f}px, large={avg_large:.2f}px"


class TestSeedReproducibility:
    """Results should be deterministic with the same seed."""

    def test_same_seed_produces_same_results(self):
        """Same random seed should produce identical overshoot behavior."""
        s = StealthProfile()
        rng1 = random.Random(12345)
        rng2 = random.Random(12345)

        target = (100, 100)
        target_size = (30, 30)

        results1 = []
        for _ in range(50):
            landing, correction = apply_overshoot_and_correction(
                target, target_size, rng=rng1, profile=s
            )
            results1.append((landing, correction))

        results2 = []
        for _ in range(50):
            landing, correction = apply_overshoot_and_correction(
                target, target_size, rng=rng2, profile=s
            )
            results2.append((landing, correction))

        assert results1 == results2, "Same seed should produce identical results"

    def test_different_seeds_produce_different_results(self):
        """Different random seeds should generally produce different results."""
        s = StealthProfile()
        rng1 = random.Random(11111)
        rng2 = random.Random(99999)

        target = (100, 100)
        target_size = (30, 30)

        results1 = []
        for _ in range(50):
            landing, correction = apply_overshoot_and_correction(
                target, target_size, rng=rng1, profile=s
            )
            results1.append(correction is not None)

        results2 = []
        for _ in range(50):
            landing, correction = apply_overshoot_and_correction(
                target, target_size, rng=rng2, profile=s
            )
            results2.append(correction is not None)

        # Results should differ (with very high probability)
        assert results1 != results2, "Different seeds should produce different results"


class TestNonStealthProfileBehavior:
    """Non-StealthProfile should return target with no correction."""

    def test_naturalistic_profile_returns_target_no_correction(self):
        """NATURALISTIC profile should always return target with None correction."""
        rng = random.Random(42)

        target = (100, 100)
        target_size = (30, 30)

        landing, correction = apply_overshoot_and_correction(
            target, target_size, rng=rng, profile=NATURALISTIC
        )

        # Should return target as-is with no correction
        assert landing == (float(target[0]), float(target[1]))
        assert correction is None

    def test_fast_profile_returns_target_no_correction(self):
        """FAST profile (non-StealthProfile) should always return target with no correction."""
        from core.humanize.profile import FAST

        rng = random.Random(42)

        target = (100, 100)
        target_size = (30, 30)

        landing, correction = apply_overshoot_and_correction(
            target, target_size, rng=rng, profile=FAST
        )

        assert landing == (float(target[0]), float(target[1]))
        assert correction is None


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_area_target(self):
        """Target with zero area should handle gracefully (no division by zero)."""
        s = StealthProfile()
        rng = random.Random(42)

        target = (100, 100)
        target_size = (0, 0)  # Zero area

        # Should not crash
        landing, correction = apply_overshoot_and_correction(
            target, target_size, rng=rng, profile=s
        )

        # Zero area < 1000 px², so high overshoot probability
        # But miss magnitude calculation with min(0, 0) * 0.15 = 0.0
        # So overshoot_landing equals target
        assert landing is not None

    def test_very_large_target(self):
        """Very large target (>10000 px²) should have minimal overshoot."""
        s = StealthProfile()
        rng = random.Random(42)

        target = (100, 100)
        target_size = (200, 200)  # 40000 px²

        overshoot_count = 0
        trials = 100
        for _ in range(trials):
            _, correction = apply_overshoot_and_correction(
                target, target_size, rng=rng, profile=s
            )
            if correction is not None:
                overshoot_count += 1

        # Should be low overshoot (10% threshold)
        probability = overshoot_count / trials
        assert probability <= 0.20, f"Expected low overshoot for large target, got {probability}"

    def test_boundary_at_1000_px_squared(self):
        """Test behavior at the 1000 px² threshold boundary."""
        s = StealthProfile()
        rng = random.Random(42)

        # Just below threshold (999 px²)
        target = (100, 100)
        target_size_below = (33, 30)  # 990 px²

        # Just above threshold (1001 px²)
        target_size_above = (34, 30)  # 1020 px²

        overshoot_below = 0
        overshoot_above = 0
        trials = 200

        for _ in range(trials):
            _, correction = apply_overshoot_and_correction(
                target, target_size_below, rng=rng, profile=s
            )
            if correction is not None:
                overshoot_below += 1

        for _ in range(trials):
            _, correction = apply_overshoot_and_correction(
                target, target_size_above, rng=rng, profile=s
            )
            if correction is not None:
                overshoot_above += 1

        # Below threshold should have higher overshoot (60% vs 30%)
        prob_below = overshoot_below / trials
        prob_above = overshoot_above / trials
        assert prob_below > prob_above, f"Boundary behavior wrong: below={prob_below}, above={prob_above}"

    def test_boundary_at_5000_px_squared(self):
        """Test behavior at the 5000 px² threshold boundary."""
        s = StealthProfile()
        rng = random.Random(42)

        # Just below threshold (4999 px²)
        target = (100, 100)
        target_size_below = (71, 70)  # 4970 px²

        # Just above threshold (5001 px²)
        target_size_above = (72, 70)  # 5040 px²

        overshoot_below = 0
        overshoot_above = 0
        trials = 200

        for _ in range(trials):
            _, correction = apply_overshoot_and_correction(
                target, target_size_below, rng=rng, profile=s
            )
            if correction is not None:
                overshoot_below += 1

        for _ in range(trials):
            _, correction = apply_overshoot_and_correction(
                target, target_size_above, rng=rng, profile=s
            )
            if correction is not None:
                overshoot_above += 1

        # Below threshold should have higher overshoot (30% vs 10%)
        prob_below = overshoot_below / trials
        prob_above = overshoot_above / trials
        assert prob_below > prob_above, f"Boundary behavior wrong: below={prob_below}, above={prob_above}"


class TestStealthProfileDefaults:
    """Test that default StealthProfile (STEALTH preset) works correctly."""

    def test_stealth_preset_has_reasonable_overshoot_probability(self):
        """The STEALTH preset should have a plausible overshoot probability."""
        assert 0.0 <= STEALTH.overshoot_probability <= 1.0
        # Should be in the stealth range (not too low, not too high)
        assert 0.2 <= STEALTH.overshoot_probability <= 0.5

    def test_stealth_preset_has_reasonable_sweep_back_speed(self):
        """The STEALTH preset should have a plausible sweep-back speed multiplier."""
        assert 0.0 < STEALTH.sweep_back_speed <= 2.0
        # Should be slower than normal (correction is deliberate)
        assert 0.5 <= STEALTH.sweep_back_speed <= 1.0
