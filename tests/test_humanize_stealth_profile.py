"""Tests for core/humanize/profile.py — StealthProfile dataclass.

StealthProfile extends Profile with biometric-sampled fields for adversarial
stealth. This module tests instantiation, field validation, and preset registry
lookup via get_default_profile() under SENTINEL_HUMANIZE_PROFILE=stealth.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

from core.humanize.profile import (
    NATURALISTIC,
    StealthProfile,
    get_default_profile,
)


class TestStealthProfileShape:
    def test_stealth_profile_is_frozen_dataclass(self):
        s = StealthProfile()
        with pytest.raises(FrozenInstanceError):
            s.name = "mutated"  # type: ignore[misc]

    def test_has_all_profile_fields(self):
        """StealthProfile must inherit all base Profile fields."""
        stealth_names = {f.name for f in fields(StealthProfile)}
        profile_names = {f.name for f in fields(NATURALISTIC.__class__)}
        assert profile_names.issubset(
            stealth_names
        ), f"StealthProfile missing base Profile fields: {profile_names - stealth_names}"

    def test_has_stealth_specific_fields(self):
        """StealthProfile must have all biometric-sampled stealth fields."""
        names = {f.name for f in fields(StealthProfile)}
        stealth_fields = {
            "fitts_width_scaling",
            "overshoot_probability",
            "sweep_back_speed",
            "error_rate",
            "error_delay_s",
            "correction_delay_s",
            "scroll_momentum",
            "scroll_jitter_px",
            "attention_drift_probability",
            "attention_drift_duration_s",
            "re_read_probability",
            "biometric_id",
        }
        assert stealth_fields.issubset(names), f"missing stealth fields: {stealth_fields - names}"


class TestStealthProfileDefaults:
    def test_stealth_has_biometric_id_default(self):
        s = StealthProfile()
        assert s.biometric_id == "unknown"

    def test_stealth_has_name_default(self):
        s = StealthProfile()
        assert s.name == "stealth"

    def test_stealth_has_reasonable_fitts_scaling(self):
        s = StealthProfile()
        assert 1.0 <= s.fitts_width_scaling <= 3.0

    def test_stealth_has_reasonable_overshot_probability(self):
        s = StealthProfile()
        assert 0.0 <= s.overshoot_probability <= 1.0

    def test_stealth_has_reasonable_sweep_back_speed(self):
        s = StealthProfile()
        assert 0.0 < s.sweep_back_speed <= 2.0

    def test_stealth_has_reasonable_error_rate(self):
        s = StealthProfile()
        assert 0.0 <= s.error_rate <= 20.0

    def test_stealth_has_reasonable_error_delays(self):
        s = StealthProfile()
        assert 0.0 < s.error_delay_s <= 1.0
        assert 0.0 < s.correction_delay_s <= 1.0

    def test_stealth_has_reasonable_scroll_momentum(self):
        s = StealthProfile()
        assert 0.0 <= s.scroll_momentum < 1.0

    def test_stealth_has_reasonable_scroll_jitter(self):
        s = StealthProfile()
        assert 0.0 <= s.scroll_jitter_px <= 10.0

    def test_stealth_has_reasonable_attention_drift_probability(self):
        s = StealthProfile()
        assert 0.0 <= s.attention_drift_probability <= 1.0

    def test_stealth_has_reasonable_attention_drift_duration(self):
        s = StealthProfile()
        assert 0.0 < s.attention_drift_duration_s <= 10.0

    def test_stealth_has_reasonable_re_read_probability(self):
        s = StealthProfile()
        assert 0.0 <= s.re_read_probability <= 1.0


class TestStealthProfileInstantiation:
    def test_can_instantiate_with_custom_biometric_id(self):
        s = StealthProfile(biometric_id="OPERATOR_001")
        assert s.biometric_id == "OPERATOR_001"

    def test_can_override_all_stealth_fields(self):
        s = StealthProfile(
            fitts_width_scaling=1.8,
            overshoot_probability=0.40,
            sweep_back_speed=0.6,
            error_rate=2.5,
            error_delay_s=0.15,
            correction_delay_s=0.20,
            scroll_momentum=0.80,
            scroll_jitter_px=1.0,
            attention_drift_probability=0.10,
            attention_drift_duration_s=0.5,
            re_read_probability=0.05,
            biometric_id="CUSTOM_OPERATOR",
        )
        assert s.fitts_width_scaling == 1.8
        assert s.overshoot_probability == 0.40
        assert s.sweep_back_speed == 0.6
        assert s.error_rate == 2.5
        assert s.error_delay_s == 0.15
        assert s.correction_delay_s == 0.20
        assert s.scroll_momentum == 0.80
        assert s.scroll_jitter_px == 1.0
        assert s.attention_drift_probability == 0.10
        assert s.attention_drift_duration_s == 0.5
        assert s.re_read_probability == 0.05
        assert s.biometric_id == "CUSTOM_OPERATOR"

    def test_inherits_profile_fields(self):
        """StealthProfile must inherit all base Profile fields with their defaults."""
        s = StealthProfile()
        # Base Profile fields should match NATURALISTIC defaults
        assert s.name == "stealth"  # overridden
        assert s.move_speed == NATURALISTIC.move_speed
        assert s.curve_deviation == NATURALISTIC.curve_deviation
        assert s.landing_jitter_px == NATURALISTIC.landing_jitter_px
        assert s.mean_keystroke_s == NATURALISTIC.mean_keystroke_s
        assert s.keystroke_jitter == NATURALISTIC.keystroke_jitter
        assert s.burst_probability == NATURALISTIC.burst_probability
        assert s.think_bump_s == NATURALISTIC.think_bump_s
        assert s.click_hold_s == NATURALISTIC.click_hold_s

    def test_can_override_inherited_profile_fields(self):
        """StealthProfile must allow overriding base Profile fields."""
        s = StealthProfile(
            move_speed=0.9,
            mean_keystroke_s=0.18,
            curve_deviation=1.5,
        )
        assert s.move_speed == 0.9
        assert s.mean_keystroke_s == 0.18
        assert s.curve_deviation == 1.5
        # Non-overridden fields still have defaults
        assert s.landing_jitter_px == NATURALISTIC.landing_jitter_px


class TestStealthProfileIsProfile:
    def test_stealth_profile_is_instance_of_profile(self):
        s = StealthProfile()
        assert isinstance(s, StealthProfile)
        assert isinstance(s, NATURALISTIC.__class__)

    def test_stealth_profile_can_be_used_where_profile_expected(self):
        """StealthProfile must be substitutable for Profile in type checks."""

        def accepts_profile(p: type[NATURALISTIC.__class__]) -> type[NATURALISTIC.__class__]:
            return p

        s = StealthProfile()
        result = accepts_profile(s)  # type: ignore[arg-type]
        assert result is s


class TestStealthProfileImmutability:
    def test_stealth_profile_is_hashable(self):
        """Frozen dataclasses are hashable — essential for dict/set usage."""
        s = StealthProfile()
        hash(s)  # Should not raise

    def test_stealth_profiles_with_same_values_have_same_hash(self):
        s1 = StealthProfile(biometric_id="OP1")
        s2 = StealthProfile(biometric_id="OP1")
        assert hash(s1) == hash(s2)

    def test_stealth_profiles_with_different_values_have_different_hashes(self):
        s1 = StealthProfile(biometric_id="OP1")
        s2 = StealthProfile(biometric_id="OP2")
        assert hash(s1) != hash(s2)


class TestGetDefaultProfileStealth:
    def test_env_override_stealth(self, monkeypatch):
        """Setting SENTINEL_HUMANIZE_PROFILE=stealth returns the STEALTH preset."""
        monkeypatch.setenv("SENTINEL_HUMANIZE_PROFILE", "stealth")
        from core.humanize.profile import STEALTH

        result = get_default_profile()
        assert result is STEALTH

    def test_stealth_preset_is_named_stealth(self):
        """The STEALTH preset must have name='stealth' for env override."""
        from core.humanize.profile import STEALTH

        assert STEALTH.name == "stealth"

    def test_stealth_preset_has_population_median_biometric_id(self):
        """Default STEALTH preset uses population median as biometric_id."""
        from core.humanize.profile import STEALTH

        assert STEALTH.biometric_id == "sampled-population-median"

    def test_stealth_preset_is_instance_of_stealth_profile(self):
        """The STEALTH preset must be a StealthProfile instance."""
        from core.humanize.profile import STEALTH

        assert isinstance(STEALTH, StealthProfile)

    def test_stealth_preset_in_registry(self):
        """The STEALTH preset must be registered in _PRESETS."""
        from core.humanize.profile import _PRESETS

        assert "stealth" in _PRESETS
        assert isinstance(_PRESETS["stealth"], StealthProfile)


class TestStealthProfileValuesAreBiometric:
    def test_default_values_are_within_human_ranges(self):
        """All StealthProfile defaults should be within plausible human biometric ranges."""
        s = StealthProfile()

        # Fitts's-Law scaling: 1.0 (naturalistic) to 3.0 (strong width sensitivity)
        assert 1.0 <= s.fitts_width_scaling <= 3.0

        # Overshoot probability: humans miss small targets often (20-50%)
        assert 0.2 <= s.overshoot_probability <= 0.5

        # Error rate: 1-5 errors per 100 keystrokes for typical typists
        assert 1.0 <= s.error_rate <= 10.0

        # Correction delays: 100-300ms for backspace-retype
        assert 0.10 <= s.error_delay_s <= 0.30
        assert 0.15 <= s.correction_delay_s <= 0.35

        # Scroll momentum: decay factor 0.7-0.95 (inertial but stops)
        assert 0.7 <= s.scroll_momentum <= 0.95

        # Attention drift: 5-15% chance of a gaze pause
        assert 0.05 <= s.attention_drift_probability <= 0.15

        # Re-read probability: 2-8% chance to re-read before typing
        assert 0.02 <= s.re_read_probability <= 0.08


class TestStealthProfileSubclassability:
    """The StealthProfile contract must allow further subclassing for operator-specific profiles."""

    def test_stealth_profile_is_subclassable(self):
        """A real operator profile might subclass StealthProfile for custom logic."""

        class OperatorProfile(StealthProfile):
            pass

        o = OperatorProfile(biometric_id="OPERATOR_042")
        assert o.biometric_id == "OPERATOR_042"
        assert isinstance(o, StealthProfile)
        assert isinstance(o, NATURALISTIC.__class__)
