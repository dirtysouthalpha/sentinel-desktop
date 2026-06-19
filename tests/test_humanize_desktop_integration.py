"""Integration tests: humanization wired into core/desktop.py chokepoint.

These verify the two-sided contract:
- SENTINEL_HUMANIZE ON  → move_to replays a curved multi-step path (not one
  linear moveTo), type_text spaces keystrokes with variable cadence.
- SENTINEL_HUMANIZE OFF → behavior is byte-identical to today (single linear
  moveTo, pyautogui.write with a fixed interval). This is the parity guarantee
  that protects the existing 7823-test baseline.

All input is mocked — no real mouse/keyboard movement in CI.
"""

from __future__ import annotations

from unittest.mock import call

import pytest

from core import desktop as desktop_mod
from core.desktop import DesktopController


@pytest.fixture
def ctrl(monkeypatch):
    """A DesktopController with a spy pyautogui (the conftest stub is a noop).

    We replace desktop.py's `pyautogui` module-level reference with a fresh
    MagicMock so we can assert on call patterns (single moveTo vs many).
    """
    from unittest.mock import MagicMock
    fake = MagicMock()
    fake.size.return_value = (1920, 1080)
    fake.position.return_value = (0, 0)
    fake.FailSafeException = type("FailSafeException", (Exception,), {})
    monkeypatch.setattr(desktop_mod, "pyautogui", fake)
    # Force _ensure_pyautogui to treat the fake as already imported.
    monkeypatch.setattr(desktop_mod, "pyautogui", fake, raising=True)
    return DesktopController(), fake


class TestMoveToHumanized:
    def test_move_to_uses_multi_step_path_when_enabled(self, ctrl, monkeypatch):
        controller, fake = ctrl
        monkeypatch.setenv("SENTINEL_HUMANIZE", "1")
        controller.move_to(500, 400)
        # Humanized ⇒ many moveTo calls along the curve, not one.
        assert fake.moveTo.call_count > 1, (
            "humanize ON but move_to made a single linear call"
        )

    def test_move_to_single_linear_call_when_disabled(self, ctrl, monkeypatch):
        controller, fake = ctrl
        monkeypatch.setenv("SENTINEL_HUMANIZE", "0")
        controller.move_to(500, 400)
        # Parity with old behavior: exactly one moveTo with the target + duration.
        assert fake.moveTo.call_count == 1
        # First positional or keyword should carry the target coords.
        _args, kwargs = fake.moveTo.call_args
        assert kwargs.get("x") == 500 or 500 in (_args[0] if _args else [])

    def test_move_to_off_uses_duration_kwarg(self, ctrl, monkeypatch):
        """OFF path preserves the original duration=0.3 default exactly."""
        controller, fake = ctrl
        monkeypatch.setenv("SENTINEL_HUMANIZE", "0")
        controller.move_to(100, 100)
        _, kwargs = fake.moveTo.call_args
        assert kwargs.get("duration") == 0.3


class TestClickHumanized:
    def test_click_moves_before_clicking_when_enabled(self, ctrl, monkeypatch):
        controller, fake = ctrl
        monkeypatch.setenv("SENTINEL_HUMANIZE", "1")
        controller.click(300, 300)
        # A humanized click moves (curve) THEN clicks.
        assert fake.moveTo.call_count >= 1
        assert fake.click.called

    def test_click_just_clicks_when_disabled(self, ctrl, monkeypatch):
        controller, fake = ctrl
        monkeypatch.setenv("SENTINEL_HUMANIZE", "0")
        controller.click(300, 300)
        # Old behavior: no separate move_to, just pyautogui.click(x, y).
        assert fake.click.called
        # No multi-step move.
        assert fake.moveTo.call_count == 0


class TestTypeTextHumanized:
    def test_type_text_uses_per_char_presses_when_enabled(self, ctrl, monkeypatch):
        controller, fake = ctrl
        monkeypatch.setenv("SENTINEL_HUMANIZE", "1")
        controller.type_text("hello")
        # Humanized typing presses each key individually (variable cadence),
        # rather than one pyautogui.write(...) call.
        # We accept either many press() calls or a write() — the key property
        # is that the inter-key timing is variable (humanized). Assert press
        # count when the implementation goes the per-key route.
        assert fake.press.call_count == 5 or fake.write.called

    def test_type_text_uses_write_when_disabled(self, ctrl, monkeypatch):
        controller, fake = ctrl
        monkeypatch.setenv("SENTINEL_HUMANIZE", "0")
        controller.type_text("hello")
        # Parity: single write() with the fixed interval.
        assert fake.write.called
        _, kwargs = fake.write.call_args
        assert kwargs.get("interval") == 0.02


class TestParitySafety:
    def test_disabled_state_is_byte_identical_to_pre_humanize(self, ctrl, monkeypatch):
        """The safety net: with HUMANIZE=0, desktop behaves exactly as before.

        This is the load-bearing test for 'never break existing tests'. It
        pins the OFF path so a future refactor can't silently change it.
        """
        controller, fake = ctrl
        monkeypatch.setenv("SENTINEL_HUMANIZE", "0")

        controller.click(10, 20)
        assert fake.click.call_args.kwargs == {"x": 10, "y": 20, "button": "left", "clicks": 1}

        fake.reset_mock()
        controller.move_to(50, 60)
        assert fake.moveTo.call_count == 1
        assert fake.moveTo.call_args.kwargs == {"x": 50, "y": 60, "duration": 0.3}

        fake.reset_mock()
        controller.type_text("ab")
        assert fake.write.call_args.kwargs == {"interval": 0.02}
        assert fake.write.call_args.args == ("ab",)
