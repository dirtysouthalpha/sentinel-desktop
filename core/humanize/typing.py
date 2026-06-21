"""Per-keystroke typing cadence from real distributions.

Why this exists: pyautogui's ``write(text, interval=0.02)`` uses a *constant*
inter-key delay — a dead robotic fingerprint. Real human typing has:
- A log-normal-ish base cadence (most keys fast, occasional slow ones).
- Occasional bursts (several keys fired very quickly in a row).
- Longer pauses at word boundaries (space) and after punctuation.

Contract:
    keystroke_delays(text, *, rng, profile) -> list[float]
    For text of length N, returns N-1 inter-key delays (the gaps between
    consecutive characters). Single-char / empty text → [].
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from core.humanize.profile import Profile

if TYPE_CHECKING:
    from core.humanize.profile import StealthProfile  # noqa: F401

# Believable human typing band (seconds). Delays are clamped into this range
# so no pathological RNG draw produces something unphysical.
_MIN_DELAY_S = 0.018  # ~55 WPM peak burst speed per key
_MAX_DELAY_S = 0.60  # a noticeable (but not absurd) hesitation

# Word-boundary characters that trigger a longer pause AFTER being typed.
_BOUNDARY_CHARS = set(" ,.;:!?")

# Multiplier applied to the delay that PRECEDES a boundary char (the typist
# slows approaching a space/punctuation).
_BOUNDARY_SLOWDOWN = 1.6


def _lognormal_delay(rng: random.Random, mean: float, jitter: float) -> float:
    """Sample one inter-key delay from a log-normal-ish distribution.

    The log-normal is a good model for reaction/inter-key timing: positive,
    right-skewed (most fast, occasional slow), no negatives.

    Args:
        mean:   target mean delay (seconds).
        jitter: coefficient of variation controlling spread.
    """
    if mean <= 0.0:
        return _MIN_DELAY_S
    # Parametrise log-normal so its mean ≈ `mean` and CV ≈ `jitter`.
    # For log-normal: mean = exp(mu + sigma^2/2), CV^2 = exp(sigma^2) - 1.
    sigma2 = math.log1p(jitter * jitter)
    sigma = math.sqrt(sigma2)
    mu = math.log(mean) - sigma2 / 2.0
    return rng.lognormvariate(mu, sigma)


def keystroke_delays(
    text: str,
    *,
    rng: random.Random,
    profile: Profile,
    errors: bool = False,
) -> list[float]:
    """Return per-keystroke inter-key delays sampled from a human distribution.

    Args:
        text:    The string that will be typed.
        rng:     Seeded random.Random.
        profile: Tempo profile (mean_keystroke_s, keystroke_jitter,
                 burst_probability).
        errors:  If True, inject errors for StealthProfile (naturalistic tier
                 ignores this flag). When errors are injected, the returned list
                 includes delays for backspaces and corrections, so its length
                 may not match len(text) - 1.

    Returns:
        list[float] of delays (seconds). When errors=False, length is
        max(0, len(text) - 1): the delay between each consecutive pair of
        characters. When errors=True and profile is StealthProfile, length
        includes backspaces and corrections. Empty for len <= 1.
    """
    if len(text) <= 1:
        return []

    # Error injection for StealthProfile
    if errors and _is_stealth_profile(profile):
        from core.humanize.errors import inject_errors_and_corrections

        error_actions = inject_errors_and_corrections(text, rng=rng, profile=profile)  # type: ignore[arg-type]
        # Convert (typed_text, delay) → flat delay list
        # For each action, extract the delay and append it
        delays: list[float] = []
        for _, delay in error_actions:
            delays.append(delay)
        return delays

    delays: list[float] = []
    burst_prob = max(0.0, min(1.0, profile.burst_probability))
    mean_base = max(_MIN_DELAY_S, profile.mean_keystroke_s)
    jitter = max(0.0, profile.keystroke_jitter)

    in_burst = False
    burst_remaining = 0

    for i in range(1, len(text)):
        # Possibly start or continue a burst (a run of fast keystrokes).
        if not in_burst and burst_prob > 0.0 and rng.random() < burst_prob:
            in_burst = True
            burst_remaining = rng.randint(2, 5)

        if in_burst:
            # Burst: tight, fast delays well below the mean.
            d = rng.uniform(_MIN_DELAY_S, mean_base * 0.35)
            burst_remaining -= 1
            if burst_remaining <= 0:
                in_burst = False
        else:
            d = _lognormal_delay(rng, mean_base, jitter)

        # Word-boundary slowdown: if the char we're about to type (text[i])
        # is a boundary char, the typist hesitates approaching it. Use BOTH a
        # multiplier AND a floor at the profile mean so a randomly-low sample
        # can't wash out the boundary effect (the test_space_delays_longer_than_mean
        # mean asserts the slowdown is observable, not just occasionally applied).
        if text[i] in _BOUNDARY_CHARS:
            d = max(d * _BOUNDARY_SLOWDOWN, mean_base * 1.1)

        # Clamp to believable human range.
        delays.append(max(_MIN_DELAY_S, min(_MAX_DELAY_S, d)))

    return delays


def _is_stealth_profile(profile: Profile) -> bool:
    """Check if a profile is a StealthProfile (type-check compatible).

    Avoids circular import by checking attribute instead of isinstance.
    """
    return hasattr(profile, "error_rate")
