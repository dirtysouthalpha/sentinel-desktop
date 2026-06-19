"""Tests for core/humanize/timing.py — click-hold, think-bump, maybe-pause.

These helpers feed the action-execution timing: how long to hold a click
(down→up), how long to pause between actions, and occasional longer
hesitations. All values flow through the profile (never hardcoded in
action_executor.py — that's the stealth-readiness rule).
"""

from __future__ import annotations

import random

from core.humanize.profile import NATURALISTIC, Profile
from core.humanize.timing import click_hold_duration, maybe_pause, think_bump


class TestClickHoldDuration:
    def test_within_profile_range(self):
        rng = random.Random(1)
        for _ in range(50):
            d = click_hold_duration(rng=rng, profile=NATURALISTIC)
            lo, hi = NATURALISTIC.click_hold_s
            assert lo <= d <= hi, f"{d} outside {NATURALISTIC.click_hold_s}"

    def test_varies_across_draws(self):
        rng = random.Random(2)
        draws = {round(click_hold_duration(rng=rng, profile=NATURALISTIC), 6) for _ in range(20)}
        assert len(draws) > 5

    def test_positive(self):
        rng = random.Random(3)
        assert click_hold_duration(rng=rng, profile=NATURALISTIC) > 0.0

    def test_respects_different_profile_range(self):
        rng = random.Random(4)
        custom = Profile(name="custom", click_hold_s=(0.20, 0.25))
        for _ in range(30):
            d = click_hold_duration(rng=rng, profile=custom)
            assert 0.20 <= d <= 0.25


class TestThinkBump:
    def test_within_profile_range(self):
        rng = random.Random(5)
        for _ in range(50):
            d = think_bump(rng=rng, profile=NATURALISTIC)
            lo, hi = NATURALISTIC.think_bump_s
            assert lo <= d <= hi

    def test_varies_across_draws(self):
        rng = random.Random(6)
        draws = {round(think_bump(rng=rng, profile=NATURALISTIC), 6) for _ in range(20)}
        assert len(draws) > 5

    def test_positive(self):
        rng = random.Random(7)
        assert think_bump(rng=rng, profile=NATURALISTIC) > 0.0


class TestMaybePause:
    def test_zero_when_probability_zero(self):
        rng = random.Random(8)
        for _ in range(50):
            # prob=0 must always return 0.0 (no pause).
            assert maybe_pause(prob=0.0, rng=rng, profile=NATURALISTIC) == 0.0

    def test_nonzero_when_probability_one(self):
        rng = random.Random(9)
        for _ in range(20):
            # prob=1 must always pause (return a positive value).
            assert maybe_pause(prob=1.0, rng=rng, profile=NATURALISTIC) > 0.0

    def test_default_probability_used_when_omitted(self):
        """Calling without prob= uses a sane default (not 0, not 1)."""
        rng = random.Random(10)
        # Over many draws with the default, we should see both zero (no pause)
        # and nonzero (pause) outcomes — i.e. a probabilistic middle ground.
        results = [maybe_pause(rng=rng, profile=NATURALISTIC) for _ in range(200)]
        zeros = sum(1 for r in results if r == 0.0)
        nonzeros = sum(1 for r in results if r > 0.0)
        assert zeros > 0 and nonzeros > 0, (
            "default probability is degenerate (all-zero or all-nonzero)"
        )

    def test_pause_value_within_human_hesitation_range(self):
        rng = random.Random(11)
        pauses = [maybe_pause(prob=1.0, rng=rng, profile=NATURALISTIC) for _ in range(50)]
        # A "longer hesitation": at least a think-bump's worth, not minutes.
        for p in pauses:
            assert 0.0 < p <= 2.0


class TestDeterminism:
    def test_same_seed_same_click_hold(self):
        d1 = click_hold_duration(rng=random.Random(42), profile=NATURALISTIC)
        d2 = click_hold_duration(rng=random.Random(42), profile=NATURALISTIC)
        assert d1 == d2

    def test_same_seed_same_think_bump(self):
        d1 = think_bump(rng=random.Random(42), profile=NATURALISTIC)
        d2 = think_bump(rng=random.Random(42), profile=NATURALISTIC)
        assert d1 == d2
