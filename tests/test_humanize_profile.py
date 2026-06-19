"""Tests for core/humanize/profile.py — tempo Profile dataclass.

The Profile is the single extension point for humanization tempo. It must be
a frozen dataclass (immutable, hashable), have sensible NATURALISTIC defaults,
clamp out-of-range derived values defensively, and — critically — be
subclassable so a future StealthProfile can override fields without any
chokepoint changes (stealth-readiness, see future-stealth-mode.md).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

from core.humanize.profile import (
    FAST,
    NATURALISTIC,
    Profile,
    get_default_profile,
)


class TestProfileShape:
    def test_profile_is_frozen_dataclass(self):
        p = NATURALISTIC
        with pytest.raises(FrozenInstanceError):
            p.name = "mutated"  # type: ignore[misc]

    def test_has_required_fields(self):
        names = {f.name for f in fields(Profile)}
        required = {
            "name",
            "move_speed",
            "curve_deviation",
            "landing_jitter_px",
            "mean_keystroke_s",
            "keystroke_jitter",
            "burst_probability",
            "think_bump_s",
            "click_hold_s",
        }
        assert required.issubset(names), f"missing fields: {required - names}"


class TestDefaults:
    def test_naturalistic_is_the_documented_default(self):
        assert NATURALISTIC.name == "naturalistic"

    def test_naturalistic_has_reasonable_motion(self):
        assert 0.5 <= NATURALISTIC.move_speed <= 2.0
        assert 0.0 < NATURALISTIC.curve_deviation
        assert 0.0 < NATURALISTIC.landing_jitter_px <= 10.0

    def test_naturalistic_has_reasonable_typing(self):
        # Mean inter-key delay in a believable human range (50–250 ms).
        assert 0.03 <= NATURALISTIC.mean_keystroke_s <= 0.30
        assert 0.0 <= NATURALISTIC.keystroke_jitter <= 1.0
        assert 0.0 <= NATURALISTIC.burst_probability <= 1.0

    def test_naturalistic_has_reasonable_timing(self):
        lo, hi = NATURALISTIC.think_bump_s
        assert 0.0 <= lo < hi
        clo, chi = NATURALISTIC.click_hold_s
        assert 0.0 <= clo < chi

    def test_fast_profile_is_faster_than_naturalistic(self):
        assert FAST.move_speed > NATURALISTIC.move_speed
        assert FAST.mean_keystroke_s < NATURALISTIC.mean_keystroke_s

    def test_fast_is_named(self):
        assert FAST.name == "fast"


class TestGetDefaultProfile:
    def test_default_is_naturalistic(self, monkeypatch):
        monkeypatch.delenv("SENTINEL_HUMANIZE_PROFILE", raising=False)
        assert get_default_profile() is NATURALISTIC

    def test_env_override_unknown_falls_back_to_naturalistic(self, monkeypatch):
        # Unknown name must not raise — fall back to naturalistic.
        monkeypatch.setenv("SENTINEL_HUMANIZE_PROFILE", "nonexistent-profile")
        result = get_default_profile()
        assert result is NATURALISTIC

    def test_env_override_fast(self, monkeypatch):
        monkeypatch.setenv("SENTINEL_HUMANIZE_PROFILE", "fast")
        assert get_default_profile() is FAST


class TestStealthReadiness:
    """The Profile contract must allow a StealthProfile subclass to slot in
    by overriding fields. This is the architectural-debt payment that keeps
    the deferred adversarial tier reachable without chokepoint rewrites.
    """

    def test_profile_is_subclassable_with_overrides(self):
        # A real StealthProfile subclasses Profile and supplies overrides via
        # __init__ (the natural pattern: a stealth profile samples its values
        # at construction from biometric data, not class-level defaults).
        class StealthProfile(Profile):
            pass

        s = StealthProfile(name="stealth", move_speed=0.9, mean_keystroke_s=0.18)
        assert s.name == "stealth"
        assert s.move_speed == 0.9
        assert s.mean_keystroke_s == 0.18
        assert isinstance(s, Profile)
        # Inherited fields still present with their naturalistic defaults.
        assert s.landing_jitter_px == NATURALISTIC.landing_jitter_px
