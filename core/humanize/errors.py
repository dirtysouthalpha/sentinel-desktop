"""Error + self-correction injection for stealth typing.

This module injects realistic typing errors and corrections into text.
Real operators mistype, notice, backspace, and retype. Error-free typing
is a robotic fingerprint that ML-based detectors can identify.

The inject_errors_and_corrections function takes clean text and returns
a sequence of (typed_text, delay) actions that include mistypes,
backspaces, and corrections with realistic timing.
"""

from __future__ import annotations

import random
import string
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .profile import Profile, StealthProfile


def inject_errors_and_corrections(
    text: str,
    *,
    rng: random.Random,
    profile: Profile | StealthProfile,
) -> list[tuple[str, float]]:
    """Return a sequence of (typed_text, delay) actions with injected errors.

    Args:
        text: The intended final text.
        rng: Seeded random.Random.
        profile: Tempo profile with error_rate, error_delay_s, correction_delay_s.

    Returns:
        List of (typed_text, delay_s) tuples. Each entry is either:
        - A correct character (typo-free segment) with normal keystroke delay.
        - A mistyped character + backspace + correction with error-specific delays.

    Example:
        Input text: "password"
        Output: [
            ("passw", 0.12),  # Correct segment
            ("q", 0.18),      # Mistype
            ("", 0.22),       # Pause before backspace
            ("\b", 0.10),     # Backspace
            ("", 0.15),       # Pause before retype
            ("ord", 0.12),    # Correction + rest of word
        ]
    """
    # Import here to avoid circular dependency
    from .profile import StealthProfile

    if not isinstance(profile, StealthProfile):
        # No errors for naturalistic profile
        return [(text, 0.0)]

    error_prob = profile.error_rate / 100.0  # Convert to per-keystroke probability
    result: list[tuple[str, float]] = []
    current_segment = ""
    base_keystroke_delay = profile.mean_keystroke_s

    for i, char in enumerate(text):
        # Should we inject an error here?
        # Don't error on first character (harder to detect immediately)
        if rng.random() < error_prob and i > 0:
            # Emit the correct segment so far
            if current_segment:
                result.append((current_segment, base_keystroke_delay * len(current_segment)))
                current_segment = ""

            # Choose error type:
            # 40%: adjacent key (QWERTY proximity)
            # 30%: shifted character (wrong case)
            # 20%: skipped character
            # 10%: random wrong character
            error_type = rng.choices(
                ["adjacent", "shifted", "skip", "random"],
                weights=[0.40, 0.30, 0.20, 0.10],
            )[0]

            if error_type == "adjacent":
                mistyped_char = _adjacent_key_mistype(char, rng)
            elif error_type == "shifted":
                mistyped_char = char.swapcase()
            elif error_type == "skip":
                mistyped_char = ""  # Type nothing
            else:  # random
                mistyped_char = rng.choice(string.ascii_letters + string.digits)

            # Type the error
            result.append((mistyped_char, base_keystroke_delay))

            # Pause before noticing the error (subconscious detection delay)
            notice_delay = rng.gauss(profile.error_delay_s, 0.05)
            result.append(("", max(0.0, notice_delay)))

            # Backspace (may need multiple if error was multiple chars)
            backspace_count = len(mistyped_char) if mistyped_char else 1
            for _ in range(backspace_count):
                result.append(("\b", base_keystroke_delay * 0.8))  # Backspace is faster

            # Pause before retype
            correction_delay = rng.gauss(profile.correction_delay_s, 0.06)
            result.append(("", max(0.0, correction_delay)))

            # Now type the correct character (retry)
            result.append((char, base_keystroke_delay))
        else:
            current_segment += char

    # Emit remaining segment
    if current_segment:
        result.append((current_segment, base_keystroke_delay * len(current_segment)))

    return result


def _adjacent_key_mistype(char: str, rng: random.Random) -> str:
    """Return a physically adjacent key on QWERTY keyboard.

    Args:
        char: The character that should have been typed.
        rng: Seeded random.Random.

    Returns:
        A mistyped character from an adjacent key, or the original char if
        no adjacency data is available.
    """
    # Simplified QWERTY adjacency map (most common keys only)
    adjacency: dict[str, list[str]] = {
        # Top row
        "q": ["1", "w", "a"],
        "w": ["q", "e", "a", "s"],
        "e": ["w", "r", "s", "d"],
        "r": ["e", "t", "d", "f"],
        "t": ["r", "y", "f", "g"],
        "y": ["t", "u", "g", "h"],
        "u": ["y", "i", "h", "j"],
        "i": ["u", "o", "j", "k"],
        "o": ["i", "p", "k", "l"],
        "p": ["o", "[", "l"],
        # Home row
        "a": ["q", "w", "s", "z"],
        "s": ["q", "w", "e", "a", "d", "z", "x"],
        "d": ["w", "e", "r", "s", "f", "x", "c"],
        "f": ["e", "r", "t", "d", "g", "c", "v"],
        "g": ["r", "t", "y", "f", "h", "v", "b"],
        "h": ["t", "y", "u", "g", "j", "b", "n"],
        "j": ["y", "u", "i", "h", "k", "n", "m"],
        "k": ["u", "i", "o", "j", "l", "m", ","],
        "l": ["i", "o", "p", "k", ";", ","],
        # Bottom row
        "z": ["a", "s", "x"],
        "x": ["s", "d", "z", "c"],
        "c": ["d", "f", "x", "v"],
        "v": ["f", "g", "c", "b"],
        "b": ["g", "h", "v", "n"],
        "n": ["h", "j", "b", "m"],
        "m": ["j", "k", "n", ","],
        ",": ["k", "l", "m", "."],
        ".": ["l", ";", ",", "/"],
        "/": [";", ".", ""],
        # Numbers
        "1": ["q", "2"],
        "2": ["1", "q", "w", "3"],
        "3": ["2", "w", "e", "4"],
        "4": ["3", "e", "r", "5"],
        "5": ["4", "r", "t", "6"],
        "6": ["5", "t", "y", "7"],
        "7": ["6", "y", "u", "8"],
        "8": ["7", "u", "i", "9"],
        "9": ["8", "i", "o", "0"],
        "0": ["9", "o", "p", "-"],
    }

    char_lower = char.lower()
    if char_lower in adjacency:
        adjacent = rng.choice(adjacency[char_lower])
        # Preserve original case
        return adjacent.upper() if char.isupper() else adjacent

    return char  # No adjacency data, no mistype
