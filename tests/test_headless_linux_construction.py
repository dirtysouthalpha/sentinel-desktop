"""Regression tests for headless-Linux construction (cross-platform support).

These pin the contract that ``AgentEngine`` and ``DesktopController`` construct
WITHOUT a ``$DISPLAY`` environment variable. On headless Linux, pyautogui's
import eagerly reads ``os.environ['DISPLAY']`` via mouseinfo and raises
``KeyError``, which used to crash ``AgentEngine.__init__``. The fixes
(graceful ``_ensure_pyautogui`` returning None + widened except clauses in
core/desktop.py and core/dpi.py) make construction degrade to a no-display
default instead of crashing.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def headless_env(monkeypatch):
    """Remove DISPLAY (and WAYLAND_DISPLAY) to simulate a headless Linux box."""
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("XAUTHORITY", raising=False)
    yield


class TestDesktopControllerHeadless:
    def test_constructs_without_display(self, headless_env):
        """DesktopController() must not raise when DISPLAY is unset."""
        from core.desktop import DesktopController

        controller = DesktopController()
        # Degrades to the default screen size rather than crashing.
        assert controller._screen_size == (1920, 1080)

    def test_screenshot_returns_blank_without_display(self, headless_env):
        """screenshot() returns a blank placeholder image, not a crash."""
        from PIL import Image

        from core.desktop import DesktopController

        controller = DesktopController()
        img = controller.screenshot()
        assert isinstance(img, Image.Image)
        # The contract is 'never raises'. Dimensions depend on whether a capture
        # backend (mss/PIL) is reachable without DISPLAY; we don't over-specify.

    def test_screenshot_base64_returns_empty_without_display(self, headless_env):
        """screenshot_base64() returns a string (possibly empty), not a crash.

        When a capture backend returns a small image we get a valid base64
        string; when fully unavailable we get ''. Both are acceptable — the bug
        was a KeyError crash.
        """
        from core.desktop import DesktopController

        result = DesktopController().screenshot_base64()
        assert isinstance(result, str)


class TestEnsurePyautoguiGraceful:
    def test_returns_none_when_display_unset(self, headless_env):
        """_ensure_pyautogui() returns None (not raises) when DISPLAY is missing."""
        from core import desktop as desktop_mod

        # Force a fresh import attempt by clearing the cached module-level None.
        with patch.object(desktop_mod, "pyautogui", None):
            result = desktop_mod._ensure_pyautogui()
        # On a headless box this is None; on a box WITH a display it may be the
        # module. Either is acceptable — the contract is "never raises".
        assert result is None or hasattr(result, "screenshot")


class TestDpiHeadlessFallback:
    def test_detect_monitors_falls_back_without_display(self, headless_env):
        """detect_monitors() returns the 1920x1080 fallback, not a KeyError."""
        from core.dpi import detect_monitors

        monitors = detect_monitors()
        # Either real monitors (if mss works) or the single fallback. The point
        # is it doesn't raise. If it degraded, we get exactly one 1920x1080 entry.
        assert isinstance(monitors, list)
        assert len(monitors) >= 1
        if len(monitors) == 1:
            assert (monitors[0].width, monitors[0].height) == (1920, 1080)


class TestAgentEngineHeadlessConstruction:
    """The headline fix: AgentEngine() must construct on a headless Linux box.

    This is the test the objective cares about — 'make sure sentinel desktop
    works for both windows and linux'. Construction is the first gate; if the
    engine can't be built, nothing else matters.
    """

    def test_agent_engine_constructs_without_display(self, headless_env, monkeypatch):
        # The engine needs API keys present to construct; stub them.
        monkeypatch.setenv("OPENAI_API_KEY", "sk-stub")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-stub")
        # Avoid touching real LLM/provider setup — we only need construction.
        monkeypatch.setenv("SENTINEL_DRY_RUN", "1")

        from core.engine import AgentEngine

        try:
            engine = AgentEngine(config={"dry_run": True})
        except Exception as exc:  # pragma: no cover - the point is it shouldn't raise
            pytest.fail(f"AgentEngine raised on headless construction: "
                        f"{type(exc).__name__}: {exc}")

        # Engine built; verify the desktop subsystem degraded sanely.
        assert engine.executor is not None
        assert engine.executor._desktop._screen_size == (1920, 1080)


# ---------------------------------------------------------------------------
# Phase B: input routing through the platform backend when headless
# ---------------------------------------------------------------------------


class _RecordingInput:
    """Test double for backend.input — records every call so we can assert
    the DesktopController routed through it instead of pyautogui."""

    def __init__(self):
        self.calls: list[str] = []

    def click(self, x, y, button="left", clicks=1):
        self.calls.append("click"); return True

    def doubleClick(self, x, y):
        self.calls.append("doubleClick"); return True

    def rightClick(self, x, y, clicks=1):
        self.calls.append("rightClick"); return True

    def moveTo(self, x, y, duration=0.0):
        self.calls.append("moveTo"); return True

    def drag(self, x1, y1, x2, y2, duration=0.5, button="left"):
        self.calls.append("drag"); return True

    def scroll(self, amount, x=None, y=None):
        self.calls.append("scroll"); return True

    def position(self):
        self.calls.append("position"); return (1, 2)

    def type_text(self, text):
        self.calls.append("type_text"); return True

    def press_key(self, key):
        self.calls.append("press_key"); return True

    def hotkey(self, *keys):
        self.calls.append("hotkey"); return True

    def screenshot(self):
        self.calls.append("screenshot")
        from PIL import Image
        return Image.new("RGB", (10, 10))


class TestDesktopControllerRoutesThroughBackendWhenHeadless:
    """When pyautogui is unavailable (None), every input method must route
    through backend.input rather than crashing. This is the Phase B contract."""

    def _controller_with_backend(self, monkeypatch):
        from core import desktop as desktop_mod

        # Force pyautogui to None (simulates headless where import fails).
        monkeypatch.setattr(desktop_mod, "pyautogui", None)
        # Avoid touching real pyautogui import during construction.
        monkeypatch.setattr(desktop_mod, "_ensure_pyautogui", lambda: None)
        ctrl = desktop_mod.DesktopController()
        recorder = _RecordingInput()
        ctrl._backend_input = recorder
        return ctrl, recorder

    def test_click_routes_to_backend(self, monkeypatch):
        ctrl, rec = self._controller_with_backend(monkeypatch)
        ctrl.click(10, 20)
        assert "click" in rec.calls

    def test_double_click_routes_to_backend(self, monkeypatch):
        ctrl, rec = self._controller_with_backend(monkeypatch)
        ctrl.double_click(1, 2)
        assert "doubleClick" in rec.calls

    def test_right_click_routes_to_backend(self, monkeypatch):
        ctrl, rec = self._controller_with_backend(monkeypatch)
        ctrl.right_click(1, 2)
        assert "rightClick" in rec.calls

    def test_move_to_routes_to_backend(self, monkeypatch):
        ctrl, rec = self._controller_with_backend(monkeypatch)
        ctrl.move_to(5, 6)
        assert "moveTo" in rec.calls

    def test_drag_routes_to_backend(self, monkeypatch):
        ctrl, rec = self._controller_with_backend(monkeypatch)
        ctrl.drag(1, 1, 2, 2)
        assert "drag" in rec.calls

    def test_scroll_routes_to_backend(self, monkeypatch):
        ctrl, rec = self._controller_with_backend(monkeypatch)
        ctrl.scroll(3)
        assert "scroll" in rec.calls

    def test_type_text_routes_to_backend(self, monkeypatch):
        ctrl, rec = self._controller_with_backend(monkeypatch)
        ctrl.type_text("hello")
        assert "type_text" in rec.calls

    def test_press_key_routes_to_backend(self, monkeypatch):
        ctrl, rec = self._controller_with_backend(monkeypatch)
        ctrl.press_key("enter")
        assert "press_key" in rec.calls

    def test_hotkey_routes_to_backend(self, monkeypatch):
        ctrl, rec = self._controller_with_backend(monkeypatch)
        ctrl.hotkey("ctrl", "c")
        assert "hotkey" in rec.calls

    def test_get_mouse_position_routes_to_backend(self, monkeypatch):
        ctrl, rec = self._controller_with_backend(monkeypatch)
        assert ctrl.get_mouse_position() == (1, 2)
        assert "position" in rec.calls

    def test_screenshot_routes_to_backend(self, monkeypatch):
        ctrl, rec = self._controller_with_backend(monkeypatch)
        ctrl.screenshot()
        assert "screenshot" in rec.calls


# Re-export for direct pytest invocation
if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
