"""Tests for core/humanize/rng.py — seeded reproducible RNG.

The RNG must be deterministic for a fixed seed (required for session replay
and for the deferred adversarial/stealth tier; see
docs/superpowers/notes/future-stealth-mode.md).
"""

from __future__ import annotations

import random

import pytest

from core.humanize import rng as rng_mod
from core.humanize.rng import get_rng, reset


class TestGetRng:
    def test_get_rng_returns_random_instance(self):
        r = get_rng()
        assert isinstance(r, random.Random)

    def test_same_seed_same_sequence(self):
        r1 = get_rng(seed=42)
        r2 = get_rng(seed=42)
        seq1 = [r1.random() for _ in range(10)]
        seq2 = [r2.random() for _ in range(10)]
        assert seq1 == seq2

    def test_different_seeds_different_sequence(self):
        r1 = get_rng(seed=1)
        r2 = get_rng(seed=2)
        seq1 = [r1.random() for _ in range(10)]
        seq2 = [r2.random() for _ in range(10)]
        assert seq1 != seq2

    def test_get_rng_does_not_mutate_module_default(self):
        """A one-off seeded get_rng must not re-seed the module-level rng.

        Invariant: calling get_rng(seed=X) returns a separate instance and
        leaves the default rng's *future* draws deterministic. We verify by
        resetting the default to a known seed, drawing a baseline stream,
        interleaving seeded one-off calls, then confirming the default's
        stream matches a fresh seeded replay.
        """
        # Baseline stream from default, with a known reset point.
        reset(seed=55)
        expected = [get_rng().random() for _ in range(10)]

        # Now interleave: reset to the same seed, draw a few, do seeded
        # one-offs (which must not disturb default), then continue drawing.
        reset(seed=55)
        actual = []
        for i in range(10):
            # Seeded one-off calls interspersed — must be independent.
            _ = get_rng(seed=1000 + i)
            _ = [get_rng(seed=2000 + i).random() for _ in range(3)]
            actual.append(get_rng().random())

        assert actual == expected

    def test_seeded_get_rng_is_separate_instance(self):
        """get_rng(seed=X) returns a fresh instance, not the module default."""
        default_ref = get_rng()
        seeded_ref = get_rng(seed=1)
        assert seeded_ref is not default_ref


class TestReset:
    def test_reset_with_seed_reproduces_sequence(self):
        reset(seed=123)
        seq1 = [get_rng().random() for _ in range(10)]

        reset(seed=123)
        seq2 = [get_rng().random() for _ in range(10)]
        assert seq1 == seq2

    def test_reset_changes_module_default_state(self):
        reset(seed=1)
        a = get_rng().random()
        reset(seed=2)
        b = get_rng().random()
        assert a != b

    def test_reset_default_none_is_time_seeded_and_runs(self):
        """reset(None) must not raise and must yield a usable rng."""
        reset()  # time-seeded
        val = get_rng().random()
        assert 0.0 <= val < 1.0


class TestReplayability:
    def test_two_full_sessions_same_seed_identical(self):
        """Simulate two replayed sessions: same seed → identical draw stream."""
        def session(seed: int) -> list[float]:
            reset(seed=seed)
            r = get_rng()
            return [r.uniform(0, 100) for _ in range(20)]

        assert session(seed=7) == session(seed=7)
