"""Attention drift + dwell simulation for human-like pauses.

Humans don't execute actions at constant tempo — we pause, re-read, and hesitate.
This module simulates those attention patterns to defeat behavioral biometric
classifiers that flag "machine-like" rhythm.

Only active for StealthProfile (see core/humanize/profile.py). Naturalistic tier
gets zero pauses (no attention simulation).
"""

from __future__ import annotations

import random


def attention_pause(
    action_context: str,
    *,
    rng: random.Random,
    profile,
) -> float:
    """Return a gaze-like pause duration (0.0 if no pause).

    Pause probability is context-aware:
    - Baseline: profile.attention_drift_probability (default 8%)
    - Destructive actions (delete, destroy, confirm): 2× baseline
    - Password/credential fields: 1.5× baseline
    - Repetitive actions (flow state): 0.5× baseline

    Args:
        action_context: Human-readable description of the action (e.g.,
            "clicking_submit_button", "typing_password"). Used for context-aware
            pause probability adjustments.
        rng: Seeded random.Random for reproducible pauses.
        profile: Tempo profile (must be StealthProfile for attention pauses).

    Returns:
        Pause duration in seconds (0.0 if no pause this time).

    Examples:
        >>> # No pause for naturalistic profile
        >>> attention_pause("click", rng=Random(0), profile=NATURALISTIC)
        0.0

        >>> # Stealth profile may pause (probabilistic)
        >>> profile = StealthProfile()
        >>> duration = attention_pause("clicking_delete_button", rng=Random(42), profile=profile)
        >>> # Returns 0.0 or a positive duration (sampled from Gaussian)
    """
    # Check for StealthProfile
    if not isinstance(profile, StealthProfile):
        return 0.0

    base_prob = profile.attention_drift_probability

    # Context-aware probability adjustment
    context_lower = action_context.lower()
    if any(keyword in context_lower for keyword in ["delete", "destroy", "confirm"]):
        prob = base_prob * 2.0
    elif any(keyword in context_lower for keyword in ["password", "credential", "secret"]):
        prob = base_prob * 1.5
    elif "repetitive" in context_lower:
        prob = base_prob * 0.5
    else:
        prob = base_prob

    # Determine if we should pause this time
    if rng.random() < prob:
        # Sample duration from profile with jitter
        # Mean from profile, std 0.15s (from spec)
        duration = rng.gauss(profile.attention_drift_duration_s, 0.15)
        return max(0.0, duration)

    return 0.0


def re_read_pause(
    field_type: str,
    *,
    rng: random.Random,
    profile,
) -> float:
    """Return a re-read pause duration before typing (0.0 if no pause).

    Re-reading is more common for sensitive fields (passwords, emails) where
    operators double-check for typos. Less common for simple fields.

    Args:
        field_type: Type of field being typed into (e.g., "email", "password",
            "username"). Used for context-aware pause probability.
        rng: Seeded random.Random for reproducible pauses.
        profile: Tempo profile (must be StealthProfile for re-read pauses).

    Returns:
        Pause duration in seconds (0.0 if no pause this time).

    Examples:
        >>> # No pause for naturalistic profile
        >>> re_read_pause("email", rng=Random(0), profile=NATURALISTIC)
        0.0

        >>> # Stealth profile more likely to pause on passwords
        >>> profile = StealthProfile()
        >>> duration = re_read_pause("password", rng=Random(42), profile=profile)
        >>> # Higher probability (2× baseline) for password fields
    """
    # Check for StealthProfile
    if not isinstance(profile, StealthProfile):
        return 0.0

    base_prob = profile.re_read_probability

    # Context-aware probability adjustment
    field_lower = field_type.lower()
    if field_lower in ["password", "email"]:
        prob = base_prob * 2.0
    elif field_lower in ["username", "phone"]:
        prob = base_prob * 1.5
    else:
        prob = base_prob

    # Determine if we should pause this time
    if rng.random() < prob:
        # Shorter than general attention pause (mean 0.4s, std 0.10s from spec)
        duration = rng.gauss(0.4, 0.10)
        return max(0.0, duration)

    return 0.0


# Avoid circular import — import here for type checking
from core.humanize.profile import StealthProfile  # noqa: E402
