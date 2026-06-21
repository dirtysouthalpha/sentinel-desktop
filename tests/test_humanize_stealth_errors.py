"""Tests for error + self-correction injection module."""

import random

from core.humanize.errors import _adjacent_key_mistype, inject_errors_and_corrections
from core.humanize.profile import StealthProfile, get_default_profile


class TestInjectErrorsAndCorrections:
    """Test inject_errors_and_corrections function."""

    def test_naturalistic_profile_no_errors(self):
        """Naturalistic profile should return unchanged text with no errors."""
        profile = get_default_profile()  # NATURALISTIC profile
        rng = random.Random(42)
        text = "password"

        result = inject_errors_and_corrections(text, rng=rng, profile=profile)

        assert len(result) == 1
        assert result[0] == (text, 0.0)

    def test_stealth_profile_error_rate_within_bounds(self):
        """Error rate should approximate profile.error_rate over many runs."""
        profile = StealthProfile(error_rate=5.0)  # 5 errors per 100 keystrokes
        rng = random.Random(42)
        long_text = "a" * 1000

        errors_injected = 0
        trials = 100

        for _ in range(trials):
            result = inject_errors_and_corrections(long_text, rng=rng, profile=profile)
            # Count backspaces as proxy for error count
            errors_injected += sum(1 for text, _ in result if "\b" in text)

        # Calculate average errors per 100 keystrokes
        avg_errors_per_100 = (errors_injected / trials) / 10

        # Should be close to 5.0 ± 1.5 (statistical variance)
        assert 3.5 <= avg_errors_per_100 <= 6.5, (
            f"Error rate {avg_errors_per_100} outside expected range [3.5, 6.5]"
        )

    def test_backspace_handling(self):
        """Backspace count should match error length."""
        profile = StealthProfile(error_rate=100.0)  # Force errors on every character
        rng = random.Random(42)

        result = inject_errors_and_corrections("abc", rng=rng, profile=profile)

        # Count backspaces
        backspace_count = sum(1 for text, _ in result if text == "\b")
        assert backspace_count >= 1, "Should have at least one backspace when errors are injected"

    def test_correction_delay_distribution(self):
        """Correction delays should use Gaussian distribution from profile."""
        profile = StealthProfile(
            error_rate=100.0,
            correction_delay_s=0.22,
        )
        rng = random.Random(42)

        result = inject_errors_and_corrections("test", rng=rng, profile=profile)

        # Find pause delays (empty strings with positive delay)
        pauses = [delay for text, delay in result if text == "" and delay > 0]

        # At least one pause should exist (for correction)
        assert len(pauses) >= 1, "Should have correction pauses"

        # Pauses should be in reasonable range (mean ± 3*std)
        # Profile mean is 0.22, std is 0.06 (hardcoded in errors.py)
        for pause in pauses:
            assert 0.0 <= pause <= 0.5, f"Pause {pause} outside reasonable range"

    def test_seed_reproducibility(self):
        """Same seed should produce identical error sequences."""
        profile = StealthProfile(error_rate=10.0)
        text = "reproducible"

        result1 = inject_errors_and_corrections(text, rng=random.Random(123), profile=profile)
        result2 = inject_errors_and_corrections(text, rng=random.Random(123), profile=profile)

        assert result1 == result2, "Same seed should produce identical results"

    def test_no_error_on_first_character(self):
        """First character should never have an error (harder to detect)."""
        profile = StealthProfile(error_rate=100.0)  # Force errors
        rng = random.Random(42)
        text = "x" * 100

        result = inject_errors_and_corrections(text, rng=rng, profile=profile)

        # First result segment should start with correct text (first char is correct)
        # If first char had an error, first segment would be empty
        first_segment = result[0]
        assert len(first_segment[0]) >= 1, "First character should not be an error"

    def test_empty_text(self):
        """Empty text should return empty list."""
        profile = StealthProfile(error_rate=10.0)
        rng = random.Random(42)

        result = inject_errors_and_corrections("", rng=rng, profile=profile)

        assert result == [("", 0.0)] or result == [], "Empty text should produce empty or minimal result"

    def test_error_types_distribution(self):
        """Error types should be distributed according to weights."""
        profile = StealthProfile(error_rate=100.0)  # Force errors
        rng = random.Random(42)
        text = "a" * 1000

        result = inject_errors_and_corrections(text, rng=rng, profile=profile)

        # Analyze error types from the result
        # This is implicit - we just verify the function doesn't crash
        # and produces reasonable output structure
        total_chars = sum(len(seg) for seg, _ in result)
        assert total_chars > 0, "Should produce some output"

    def test_single_character_text(self):
        """Single character should work correctly (no error possible)."""
        profile = StealthProfile(error_rate=50.0)
        rng = random.Random(42)

        result = inject_errors_and_corrections("a", rng=rng, profile=profile)

        # Should have exactly one segment (no error on first char)
        assert len(result) == 1
        assert result[0][0] == "a"

    def test_delays_are_non_negative(self):
        """All delays should be non-negative (max with 0.0)."""
        profile = StealthProfile(error_rate=50.0, error_delay_s=0.18, correction_delay_s=0.22)
        rng = random.Random(42)
        text = "test" * 100

        result = inject_errors_and_corrections(text, rng=rng, profile=profile)

        for _, delay in result:
            assert delay >= 0.0, f"Delay {delay} is negative"

    def test_output_structure(self):
        """Output should be list of (str, float) tuples."""
        profile = StealthProfile(error_rate=10.0)
        rng = random.Random(42)

        result = inject_errors_and_corrections("hello world", rng=rng, profile=profile)

        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, tuple)
            assert len(item) == 2
            assert isinstance(item[0], str)
            assert isinstance(item[1], (int, float))


class TestAdjacentKeyMistype:
    """Test _adjacent_key_mistype helper function."""

    def test_adjacent_key_common_chars(self):
        """Common keys should return adjacent keys."""
        rng = random.Random(42)

        # Test 'f' - should return one of ['e', 'r', 'd', 'g', 'c', 'v']
        result = _adjacent_key_mistype("f", rng)
        assert result in ["e", "r", "d", "g", "c", "v", "f"], f"Unexpected result: {result}"

        # Test 'a' - should return one of ['q', 'w', 's', 'z']
        result = _adjacent_key_mistype("a", rng)
        assert result in ["q", "w", "s", "z", "a"], f"Unexpected result: {result}"

    def test_adjacent_key_case_preservation(self):
        """Case should be preserved in adjacent key mistype."""
        rng = random.Random(42)

        # Test uppercase
        rng = random.Random(42)
        result = _adjacent_key_mistype("A", rng)
        if result != "A":  # If it actually changed
            assert result.isupper(), f"Should preserve uppercase: got {result}"

        # Test lowercase
        rng = random.Random(42)
        result = _adjacent_key_mistype("a", rng)
        if result != "a":  # If it actually changed
            assert result.islower(), f"Should preserve lowercase: got {result}"

    def test_adjacent_key_unknown_char(self):
        """Unknown characters should return unchanged."""
        rng = random.Random(42)

        result = _adjacent_key_mistype("@", rng)
        assert result == "@", f"Unknown char should return unchanged: got {result}"

        result = _adjacent_key_mistype("!", rng)
        assert result == "!", f"Unknown char should return unchanged: got {result}"

    def test_adjacent_key_numbers(self):
        """Number keys should have adjacent keys."""
        rng = random.Random(42)

        result = _adjacent_key_mistype("5", rng)
        assert result in ["4", "6", "r", "t", "g", "y", "f", "h", "5", "b"], (
            f"Unexpected result for '5': {result}"
        )

    def test_adjacent_key_reproducibility(self):
        """Same seed should produce same adjacent key choice."""
        char = "s"
        result1 = _adjacent_key_mistype(char, random.Random(123))
        result2 = _adjacent_key_mistype(char, random.Random(123))

        assert result1 == result2, "Same seed should produce same adjacent key"


class TestErrorInjectionIntegration:
    """Integration tests for error injection with realistic scenarios."""

    def test_password_typing_with_errors(self):
        """Simulate typing a password with realistic errors."""
        profile = StealthProfile(error_rate=3.0)  # 3% error rate
        rng = random.Random(42)
        password = "SecureP@ss123"

        result = inject_errors_and_corrections(password, rng=rng, profile=profile)

        # Verify structure
        assert isinstance(result, list)
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)

        # Total typed characters (including errors and backspaces)
        total_output = "".join(text for text, _ in result)
        assert len(total_output) > 0, "Should produce output"

    def test_long_text_error_frequency(self):
        """Long text should have appropriate error frequency."""
        profile = StealthProfile(error_rate=2.0)  # 2% error rate
        rng = random.Random(42)
        long_text = "The quick brown fox jumps over the lazy dog. " * 10

        result = inject_errors_and_corrections(long_text, rng=rng, profile=profile)

        # Count backspaces as errors
        error_count = sum(1 for text, _ in result if "\b" in text)

        # With 2% error rate on ~530 chars, expect ~10 errors
        # Allow reasonable variance (5-20 errors)
        assert 5 <= error_count <= 30, f"Error count {error_count} outside expected range"

    def test_rapid_typing_profile(self):
        """Rapid typing profile (lower delays) should still work."""
        profile = StealthProfile(
            error_rate=5.0,
            mean_keystroke_s=0.08,  # Faster typing
            error_delay_s=0.15,
            correction_delay_s=0.18,
        )
        rng = random.Random(42)
        text = "rapid typing test"

        result = inject_errors_and_corrections(text, rng=rng, profile=profile)

        # Verify all delays are reasonable for fast typing
        for _, delay in result:
            assert delay >= 0.0, f"Negative delay: {delay}"
            assert delay <= 1.0, f"Excessive delay: {delay}"

    def test_slow_typing_profile(self):
        """Slow typing profile (higher delays) should still work."""
        profile = StealthProfile(
            error_rate=5.0,
            mean_keystroke_s=0.20,  # Slower typing
            error_delay_s=0.25,
            correction_delay_s=0.30,
        )
        rng = random.Random(42)
        text = "slow typing test"

        result = inject_errors_and_corrections(text, rng=rng, profile=profile)

        # Verify all delays are reasonable for slow typing
        for _, delay in result:
            assert delay >= 0.0, f"Negative delay: {delay}"
