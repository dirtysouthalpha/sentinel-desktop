"""
Tests for gui/cursor_overlay.py — Cursor overlay utility functions.

Tests the pure helper function _ease_out. Class tests are not included
(require tkinter runtime).
"""

from __future__ import annotations

from gui.cursor_overlay import _ease_out


class TestEaseOut:
    """Tests for gui.cursor_overlay._ease_out."""

    def test_at_zero(self):
        assert _ease_out(0.0) == 0.0

    def test_at_one(self):
        assert _ease_out(1.0) == 1.0

    def test_at_half(self):
        result = _ease_out(0.5)
        # 1 - (1 - 0.5)^3 = 1 - 0.125 = 0.875
        assert abs(result - 0.875) < 1e-6

    def test_monotonically_increasing(self):
        prev = 0.0
        for i in range(1, 100):
            t = i / 100.0
            val = _ease_out(t)
            assert val > prev
            prev = val

    def test_near_zero_returns_near_zero(self):
        result = _ease_out(0.01)
        assert result < 0.03

    def test_near_one_returns_near_one(self):
        result = _ease_out(0.99)
        assert result > 0.97

    def test_output_always_between_zero_and_one(self):
        for i in range(101):
            t = i / 100.0
            val = _ease_out(t)
            assert 0.0 <= val <= 1.0

    def test_is_cubic_ease_out(self):
        # Verify the formula: 1 - (1-t)^3
        for t in [0.1, 0.25, 0.5, 0.75, 0.9]:
            expected = 1.0 - (1.0 - t) ** 3
            assert abs(_ease_out(t) - expected) < 1e-10
