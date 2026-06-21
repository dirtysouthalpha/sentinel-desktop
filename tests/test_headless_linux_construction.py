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


# Re-export for direct pytest invocation
if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
