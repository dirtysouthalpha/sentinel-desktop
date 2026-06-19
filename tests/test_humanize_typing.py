"""Tests for core/humanize/typing.py — per-keystroke cadence from real distributions.

The whole point: NOT a fixed interval (pyautogui.write's `interval=` is constant
— that's the robotic fingerprint). Real typing has variable inter-key timing.
"""

from __future__ import annotations

import random
from statistics import mean

import pytest

from core.humanize.profile import FAST, NATURALISTIC, Profile
from core.humanize.typing import keystroke_delays


class TestVariableCadence:
    def test_delays_not_all_equal(self):
        """The headline property: inter-key delays are NOT a constant stream."""
        rng = random.Random(1)
        text = "the quick brown fox jumps over the lazy dog 12345"
        delays = keystroke_delays(text, rng=rng, profile=NATURALISTIC)
        # A human-typed string of this length must have varied timing.
        assert len(set(round(d, 6) for d in delays)) > 5, (
            "delays are nearly constant — robotic fingerprint"
        )

    def test_returns_one_delay_per_gap(self):
        """For text of length N, return N-1 inter-key delays (between chars)."""
        rng = random.Random(2)
        delays = keystroke_delays("hello", rng=rng, profile=NATURALISTIC)
        assert len(delays) == 4  # 5 chars → 4 gaps

    def test_single_char_no_delays(self):
        rng = random.Random(3)
        assert keystroke_delays("x", rng=rng, profile=NATURALISTIC) == []

    def test_empty_string_no_delays(self):
        rng = random.Random(4)
        assert keystroke_delays("", rng=rng, profile=NATURALISTIC) == []


class TestWordBoundaries:
    def test_space_delays_longer_than_mean(self):
        """Hesitation at word boundaries: space should slow the typist."""
        rng = random.Random(5)
        text = "word another onemore"
        delays = keystroke_delays(text, rng=rng, profile=NATURALISTIC)
        # Spaces are at indices 4, 11 (after 'word', after 'another').
        # The delay *before* a space char is delays[space_index - 1].
        m = mean(delays)
        # The space-preceding delays should exceed the mean more often than not.
        space_indices = [i for i, c in enumerate(text) if c == " "]
        pre_space = [delays[i - 1] for i in space_indices if i - 1 >= 0]
        # Allow some randomness, but the mean of pre-space delays should be
        # at least as large as the overall mean (word-boundary slowdown).
        assert mean(pre_space) >= m * 0.9


class TestBursts:
    def test_burst_present_over_many_samples(self):
        """Over a long text, some fast clusters appear (bursts)."""
        rng = random.Random(6)
        text = "a" * 200  # long uniform text
        delays = keystroke_delays(text, rng=rng, profile=NATURALISTIC)
        # With burst_probability=0.15, we expect at least a few fast delays
        # significantly below the mean.
        m = mean(delays)
        fast = [d for d in delays if d < m * 0.4]
        assert len(fast) >= 3, f"no typing bursts observed (fast={len(fast)})"


class TestDeterminism:
    def test_same_seed_same_delays(self):
        d1 = keystroke_delays("deterministic", rng=random.Random(42), profile=NATURALISTIC)
        d2 = keystroke_delays("deterministic", rng=random.Random(42), profile=NATURALISTIC)
        assert d1 == d2

    def test_different_seeds_different_delays(self):
        d1 = keystroke_delays("hello world", rng=random.Random(1), profile=NATURALISTIC)
        d2 = keystroke_delays("hello world", rng=random.Random(2), profile=NATURALISTIC)
        assert d1 != d2


class TestProfileEffect:
    def test_fast_profile_yields_shorter_mean_delay(self):
        """FAST profile should produce shorter mean inter-key delays on average."""
        text = "abcdefghij" * 10
        # Average over several seeds to smooth RNG noise.
        nat_means = [mean(keystroke_delays(text, rng=random.Random(s), profile=NATURALISTIC))
                     for s in range(8)]
        fast_means = [mean(keystroke_delays(text, rng=random.Random(s), profile=FAST))
                      for s in range(8)]
        assert mean(fast_means) < mean(nat_means)


class TestBoundsAndSanity:
    def test_all_delays_positive(self):
        rng = random.Random(7)
        delays = keystroke_delays("sample text here", rng=rng, profile=NATURALISTIC)
        assert all(d > 0.0 for d in delays)

    def test_delays_within_human_range(self):
        """Inter-key delays should stay in a believable human range."""
        rng = random.Random(8)
        delays = keystroke_delays("typing some words " * 5, rng=rng, profile=NATURALISTIC)
        # Human single-finger typing: ~30ms to ~600ms is the believable band.
        assert all(0.01 <= d <= 1.5 for d in delays), (
            f"delays outside human range: min={min(delays)}, max={max(delays)}"
        )
