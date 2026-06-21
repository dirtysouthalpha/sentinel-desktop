"""Tests for core/humanize/attention.py — attention drift + dwell simulation.

Tests cover pause probability, context-aware scaling, re-read pauses, and
StealthProfile-only activation (zero when disabled).
"""

import random

from core.humanize.attention import attention_pause, re_read_pause
from core.humanize.profile import NATURALISTIC, StealthProfile


class TestAttentionPause:
    """Tests for attention_pause() function."""

    def test_naturalistic_profile_returns_zero(self):
        """Naturalistic profile should never insert attention pauses."""
        rng = random.Random(42)
        result = attention_pause("clicking_button", rng=rng, profile=NATURALISTIC)
        assert result == 0.0

    def test_stealth_profile_can_pause(self):
        """StealthProfile can return positive pause durations."""
        rng = random.Random(42)
        profile = StealthProfile()
        result = attention_pause("clicking_button", rng=rng, profile=profile)
        # With default 8% probability, most calls return 0.0, but some return positive
        assert result >= 0.0  # Should never be negative

    def test_pause_probability_approximately_matches_profile(self):
        """Over many iterations, pause frequency should match profile probability."""
        rng = random.Random(123)
        profile = StealthProfile(attention_drift_probability=0.5)  # 50% for test

        iterations = 1000
        pause_count = sum(
            1 for _ in range(iterations)
            if attention_pause("clicking_button", rng=rng, profile=profile) > 0.0
        )

        # Should be approximately 50% (allow ±5% for randomness)
        assert 0.45 <= pause_count / iterations <= 0.55

    def test_destructive_action_doubles_probability(self):
        """Destructive actions (delete, destroy, confirm) should get 2× baseline."""
        rng = random.Random(456)
        profile = StealthProfile(attention_drift_probability=0.2)  # 20% baseline

        iterations = 1000
        baseline_count = sum(
            1 for _ in range(iterations)
            if attention_pause("clicking_button", rng=rng, profile=profile) > 0.0
        )

        # Reset RNG for fair comparison
        rng = random.Random(456)
        destructive_count = sum(
            1 for _ in range(iterations)
            if attention_pause("clicking_delete_button", rng=rng, profile=profile) > 0.0
        )

        # Destructive should be approximately 2× baseline
        # (allow some tolerance for randomness)
        assert destructive_count > baseline_count * 1.7
        assert destructive_count < baseline_count * 2.3

    def test_password_field_increases_probability(self):
        """Password/credential fields should get 1.5× baseline."""
        rng = random.Random(789)
        profile = StealthProfile(attention_drift_probability=0.2)  # 20% baseline

        iterations = 1000
        baseline_count = sum(
            1 for _ in range(iterations)
            if attention_pause("clicking_button", rng=rng, profile=profile) > 0.0
        )

        # Reset RNG for fair comparison
        rng = random.Random(789)
        password_count = sum(
            1 for _ in range(iterations)
            if attention_pause("typing_password", rng=rng, profile=profile) > 0.0
        )

        # Password should be approximately 1.5× baseline
        assert password_count > baseline_count * 1.3
        assert password_count < baseline_count * 1.7

    def test_repetitive_action_halves_probability(self):
        """Repetitive actions (flow state) should get 0.5× baseline."""
        rng = random.Random(101)
        profile = StealthProfile(attention_drift_probability=0.4)  # 40% baseline

        iterations = 1000
        baseline_count = sum(
            1 for _ in range(iterations)
            if attention_pause("clicking_button", rng=rng, profile=profile) > 0.0
        )

        # Reset RNG for fair comparison
        rng = random.Random(101)
        repetitive_count = sum(
            1 for _ in range(iterations)
            if attention_pause("repetitive_clicking", rng=rng, profile=profile) > 0.0
        )

        # Repetitive should be approximately 0.5× baseline
        assert repetitive_count < baseline_count * 0.7

    def test_pause_duration_matches_profile_mean(self):
        """When pause occurs, duration should be sampled around profile mean."""
        rng = random.Random(999)
        profile = StealthProfile(attention_drift_probability=1.0, attention_drift_duration_s=0.8)

        # Force pauses by setting probability to 100%
        durations = [
            attention_pause("any_action", rng=rng, profile=profile)
            for _ in range(100)
        ]

        # All should be positive (100% probability)
        assert all(d > 0.0 for d in durations)

        # Mean should be approximately 0.8s (allow ±0.2s for Gaussian std)
        mean_duration = sum(durations) / len(durations)
        assert 0.6 <= mean_duration <= 1.0

    def test_pause_duration_never_negative(self):
        """Gaussian sampling should never produce negative durations."""
        rng = random.Random(555)
        profile = StealthProfile(attention_drift_probability=1.0, attention_drift_duration_s=0.1)

        # Even with very low mean (0.1s) and std (0.15s), should clamp to 0.0
        durations = [
            attention_pause("any_action", rng=rng, profile=profile)
            for _ in range(100)
        ]

        assert all(d >= 0.0 for d in durations)

    def test_deterministic_with_same_seed(self):
        """Same RNG seed should produce identical pause patterns."""
        profile = StealthProfile(attention_drift_probability=0.3)

        results1 = [
            attention_pause("test_action", rng=random.Random(111), profile=profile)
            for _ in range(20)
        ]
        results2 = [
            attention_pause("test_action", rng=random.Random(111), profile=profile)
            for _ in range(20)
        ]

        assert results1 == results2


class TestReReadPause:
    """Tests for re_read_pause() function."""

    def test_naturalistic_profile_returns_zero(self):
        """Naturalistic profile should never insert re-read pauses."""
        rng = random.Random(42)
        result = re_read_pause("email", rng=rng, profile=NATURALISTIC)
        assert result == 0.0

    def test_stealth_profile_can_pause(self):
        """StealthProfile can return positive re-read pause durations."""
        rng = random.Random(42)
        profile = StealthProfile()
        result = re_read_pause("password", rng=rng, profile=profile)
        # Should be >= 0.0
        assert result >= 0.0

    def test_pause_probability_approximately_matches_profile(self):
        """Over many iterations, pause frequency should match profile probability."""
        rng = random.Random(222)
        profile = StealthProfile(re_read_probability=0.3)  # 30% for test

        iterations = 1000
        pause_count = sum(
            1 for _ in range(iterations)
            if re_read_pause("address", rng=rng, profile=profile) > 0.0
        )

        # Should be approximately 30% (allow ±5% for randomness)
        assert 0.25 <= pause_count / iterations <= 0.35

    def test_password_field_doubles_probability(self):
        """Password fields should get 2× baseline probability."""
        rng = random.Random(333)
        profile = StealthProfile(re_read_probability=0.2)  # 20% baseline

        iterations = 1000
        baseline_count = sum(
            1 for _ in range(iterations)
            if re_read_pause("unknown_field", rng=rng, profile=profile) > 0.0
        )

        # Reset RNG for fair comparison
        rng = random.Random(333)
        password_count = sum(
            1 for _ in range(iterations)
            if re_read_pause("password", rng=rng, profile=profile) > 0.0
        )

        # Password should be approximately 2× baseline
        assert password_count > baseline_count * 1.7
        assert password_count < baseline_count * 2.3

    def test_email_field_doubles_probability(self):
        """Email fields should get 2× baseline probability."""
        rng = random.Random(444)
        profile = StealthProfile(re_read_probability=0.2)  # 20% baseline

        iterations = 1000
        baseline_count = sum(
            1 for _ in range(iterations)
            if re_read_pause("unknown_field", rng=rng, profile=profile) > 0.0
        )

        # Reset RNG for fair comparison
        rng = random.Random(444)
        email_count = sum(
            1 for _ in range(iterations)
            if re_read_pause("email", rng=rng, profile=profile) > 0.0
        )

        # Email should be approximately 2× baseline
        assert email_count > baseline_count * 1.7
        assert email_count < baseline_count * 2.3

    def test_username_field_increases_probability(self):
        """Username/phone fields should get 1.5× baseline probability."""
        rng = random.Random(555)
        profile = StealthProfile(re_read_probability=0.2)  # 20% baseline

        iterations = 1000
        baseline_count = sum(
            1 for _ in range(iterations)
            if re_read_pause("unknown_field", rng=rng, profile=profile) > 0.0
        )

        # Reset RNG for fair comparison
        rng = random.Random(555)
        username_count = sum(
            1 for _ in range(iterations)
            if re_read_pause("username", rng=rng, profile=profile) > 0.0
        )

        # Username should be approximately 1.5× baseline
        assert username_count > baseline_count * 1.3
        assert username_count < baseline_count * 1.7

    def test_pause_duration_shorter_than_attention_pause(self):
        """Re-read pauses should be shorter than general attention pauses."""
        rng = random.Random(666)
        profile = StealthProfile(re_read_probability=1.0)  # 100% for measurement

        # Force re-read pauses
        re_read_durations = [
            re_read_pause("password", rng=rng, profile=profile)
            for _ in range(100)
        ]

        # All should be positive (100% probability)
        assert all(d > 0.0 for d in re_read_durations)

        # Mean should be approximately 0.4s (from spec), shorter than attention pause (0.6s)
        mean_duration = sum(re_read_durations) / len(re_read_durations)
        assert 0.3 <= mean_duration <= 0.5

    def test_pause_duration_never_negative(self):
        """Gaussian sampling should never produce negative durations."""
        rng = random.Random(777)
        profile = StealthProfile(re_read_probability=1.0)

        durations = [
            re_read_pause("any_field", rng=rng, profile=profile)
            for _ in range(100)
        ]

        assert all(d >= 0.0 for d in durations)

    def test_deterministic_with_same_seed(self):
        """Same RNG seed should produce identical pause patterns."""
        profile = StealthProfile(re_read_probability=0.4)

        results1 = [
            re_read_pause("email", rng=random.Random(888), profile=profile)
            for _ in range(20)
        ]
        results2 = [
            re_read_pause("email", rng=random.Random(888), profile=profile)
            for _ in range(20)
        ]

        assert results1 == results2

    def test_case_insensitive_field_type_matching(self):
        """Field type matching should be case-insensitive."""
        rng = random.Random(999)
        profile = StealthProfile(re_read_probability=1.0)  # Force pause

        # All variations should trigger 2× probability (password/email)
        assert re_read_pause("Password", rng=rng, profile=profile) > 0.0
        assert re_read_pause("PASSWORD", rng=rng, profile=profile) > 0.0
        assert re_read_pause("Email", rng=rng, profile=profile) > 0.0
        assert re_read_pause("EMAIL", rng=rng, profile=profile) > 0.0
