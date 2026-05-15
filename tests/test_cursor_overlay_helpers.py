"""Tests for gui/cursor_overlay.py pure helper function."""

import math

from gui.cursor_overlay import _ease_out


class TestEaseOut:
    def test_start(self):
        assert _ease_out(0.0) == 0.0

    def test_end(self):
        assert _ease_out(1.0) == 1.0

    def test_midpoint(self):
        result = _ease_out(0.5)
        expected = 1.0 - (1.0 - 0.5) ** 3
        assert math.isclose(result, expected)

    def test_monotonic(self):
        prev = _ease_out(0.0)
        for t in (i / 20 for i in range(1, 21)):
            val = _ease_out(t)
            assert val >= prev
            prev = val

    def test_always_in_range(self):
        for i in range(101):
            t = i / 100
            val = _ease_out(t)
            assert 0.0 <= val <= 1.0

    def test_ease_out_curve(self):
        # Ease-out should be faster at start, slower at end
        val_25 = _ease_out(0.25)
        val_75 = _ease_out(0.75)
        # At 25% input, should already be > 50% output (ease-out is fast early)
        assert val_25 > 0.5
        # At 75% input, should be > 75% output
        assert val_75 > 0.75
