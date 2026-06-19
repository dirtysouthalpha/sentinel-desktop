"""Tests for the SENTINEL_HUMANIZE master switch (core/humanize/is_enabled).

This switch is the safety net that keeps the existing 7823-test baseline
green: tests run with humanization OFF (set in conftest.py), production runs
default ON. The chokepoints in desktop.py / stealth_input.py gate every
humanized path through is_enabled().
"""

from __future__ import annotations

import pytest

from core.humanize import is_enabled


class TestIsEnabled:
    def test_default_on_when_unset(self, monkeypatch):
        monkeypatch.delenv("SENTINEL_HUMANIZE", raising=False)
        assert is_enabled() is True

    @pytest.mark.parametrize("val", ["1", "on", "On", "ON", "true", "TRUE", "yes", "Yes"])
    def test_truthy_values_enable(self, monkeypatch, val):
        monkeypatch.setenv("SENTINEL_HUMANIZE", val)
        assert is_enabled() is True

    @pytest.mark.parametrize("val", ["0", "off", "Off", "OFF", "false", "FALSE", "no", "No"])
    def test_falsy_values_disable(self, monkeypatch, val):
        monkeypatch.setenv("SENTINEL_HUMANIZE", val)
        assert is_enabled() is False

    def test_conftest_forces_off_in_test_env(self):
        """The safety net: conftest.py sets SENTINEL_HUMANIZE=0 by default, so
        any test that doesn't monkeypatch it must see humanization disabled."""
        # This test does NOT touch the env var; it relies on conftest's default.
        # (If conftest's setdefault were removed, this test would catch it.)
        import os

        assert os.environ.get("SENTINEL_HUMANIZE", "1") == "0"
        assert is_enabled() is False

    def test_returns_bool_not_truthy(self, monkeypatch):
        monkeypatch.delenv("SENTINEL_HUMANIZE", raising=False)
        result = is_enabled()
        assert isinstance(result, bool)
        assert result is True
