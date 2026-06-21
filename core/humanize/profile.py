"""Tempo Profile for humanization.

The Profile is the single extension point for all humanization tempo numbers.
Subclassable so a future StealthProfile (adversarial tier, see
docs/superpowers/notes/future-stealth-mode.md) can override fields with
biometric-sampled values WITHOUT any chokepoint changes downstream.

Why a frozen dataclass: immutability makes profiles safely shareable and
hashable; subclassing still works for the stealth extension point.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    """Humanization tempo. Subclass to override (e.g. StealthProfile later).

    Motion:
        move_speed:        multiplier on base move duration (1.0 = baseline)
        curve_deviation:   how far control points bow off the straight line
        landing_jitter_px: std-dev of Gaussian landing error (pixels)
    Typing:
        mean_keystroke_s:  mean inter-key delay (seconds)
        keystroke_jitter:  coefficient of variation for inter-key spread
        burst_probability: chance of a fast burst within a word
    Timing:
        think_bump_s:  (lo, hi) range for inter-action micro-pauses
        click_hold_s:  (lo, hi) range for click down→up duration
    """

    name: str = "naturalistic"
    # Motion
    move_speed: float = 1.0
    curve_deviation: float = 1.0
    landing_jitter_px: float = 2.5
    # Typing
    mean_keystroke_s: float = 0.12
    keystroke_jitter: float = 0.45
    burst_probability: float = 0.15
    # Timing
    think_bump_s: tuple[float, float] = (0.05, 0.35)
    click_hold_s: tuple[float, float] = (0.04, 0.09)


@dataclass(frozen=True)
class StealthProfile(Profile):
    """Biometric-sampled tempo profile for adversarial stealth.

    Extends Profile with stealth-specific fields:
    - fitts_width_scaling:  how strongly target width affects move time
    - overshoot_probability: chance of undershooting/overshooting small targets
    - error_rate:            mistypes per 100 keystrokes
    - correction_delay_s:    mean backspace-to-retype latency
    - scroll_momentum:       inertial scroll decay rate
    - attention_drift_s:    mean duration of "gaze-like" pauses
    - biometric_id:          identifier of the sampled human operator

    All fields are sampled from real human operators (see
    core/humanize/biometric_sampler.py). DO NOT invent synthetic values.
    """

    # Fitts's-Law target-width sensitivity (1.0 = naturalistic, 1.5-2.5 = stealth)
    fitts_width_scaling: float = 2.0

    # Overshoot + correction
    overshoot_probability: float = 0.35
    sweep_back_speed: float = 0.7  # multiplier for correction move speed

    # Error + correction injection
    error_rate: float = 3.0  # errors per 100 keystrokes
    error_delay_s: float = 0.18  # mean delay before backspace
    correction_delay_s: float = 0.22  # mean backspace-to-retype latency

    # Scroll momentum
    scroll_momentum: float = 0.85  # decay factor (0.0 = instant stop, 1.0 = never stop)
    scroll_jitter_px: float = 1.2  # per-frame position jitter during momentum scroll

    # Attention drift + dwell
    attention_drift_probability: float = 0.08  # chance of a "gaze pause" per action
    attention_drift_duration_s: float = 0.6  # mean duration of attention pauses
    re_read_probability: float = 0.04  # chance of re-reading a field before typing

    # Biometric provenance
    biometric_id: str = "unknown"  # operator identifier from sampling session

    name: str = "stealth"


# Preset profiles ----------------------------------------------------------
NATURALISTIC: Profile = Profile(name="naturalistic")
"""Default naturalistic profile — defeats naive heuristics, looks human."""

FAST: Profile = Profile(
    name="fast",
    move_speed=1.8,
    mean_keystroke_s=0.06,
)
"""Faster profile for speed-tolerant contexts."""

STEALTH: StealthProfile = StealthProfile(
    name="stealth",
    biometric_id="sampled-population-median",  # Default: median of sampled operators
)
"""Stealth profile sampled from real human operators."""

# Registry of named presets — the env override resolves against this.
_PRESETS: dict[str, Profile] = {
    "naturalistic": NATURALISTIC,
    "fast": FAST,
    "stealth": STEALTH,  # NEW
}


def get_default_profile() -> Profile:
    """Return the active profile.

    Resolved from the ``SENTINEL_HUMANIZE_PROFILE`` env var if set and known;
    otherwise :data:`NATURALISTIC`. Unknown names fall back silently to
    NATURALISTIC (never raise — humanization must never break input).
    """
    name = os.environ.get("SENTINEL_HUMANIZE_PROFILE")
    if name and name in _PRESETS:
        return _PRESETS[name]
    return NATURALISTIC
