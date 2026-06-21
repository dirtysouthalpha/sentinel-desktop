"""Tests for stealth-input routing through ActionExecutor."""

import sys

import pytest

import core.desktop as desktop_mod
from core import stealth_input


class FakeDesktop:
    def __init__(self):
        self.calls = []

    def click(self, *a, **kw):
        self.calls.append(("click", a, kw))

    def type_text(self, text, **_):
        self.calls.append(("type_text", text))

    def press_key(self, key):
        self.calls.append(("press_key", key))

    def hotkey(self, *keys):
        self.calls.append(("hotkey", keys))

    def scroll(self, *a, **kw):
        pass


@pytest.fixture
def fake_executor(monkeypatch):
    monkeypatch.setattr(desktop_mod, "DesktopEngine", FakeDesktop)
    from core.action_executor import ActionExecutor, ExecutorConfig

    def make_executor(stealth=False):
        config = ExecutorConfig(stealth=stealth)
        return ActionExecutor(config=config)

    return make_executor


def test_stealth_off_uses_physical_input(fake_executor, monkeypatch):
    """When stealth=False, _click still goes through pyautogui-style desktop."""
    monkeypatch.setattr(stealth_input, "is_available", lambda: True)
    monkeypatch.setattr(stealth_input, "post_click", lambda *a, **kw: True)
    ex = fake_executor(stealth=False)
    ex.execute_sync({"action": "click", "x": 100, "y": 200})
    assert any(c[0] == "click" for c in ex._desktop.calls), (
        "stealth=False should hit physical desktop click"
    )


def test_stealth_on_uses_postmessage(fake_executor, monkeypatch):
    """When stealth=True and PostMessage succeeds, physical click is skipped."""
    monkeypatch.setattr(stealth_input, "is_available", lambda: True)
    calls = []

    def fake_post(x, y, button="left", **kw):
        calls.append((x, y, button))
        return True

    monkeypatch.setattr(stealth_input, "post_click", fake_post)
    ex = fake_executor(stealth=True)
    out = ex.execute_sync({"action": "click", "x": 100, "y": 200})
    assert calls == [(100, 200, "left")]
    assert ex._desktop.calls == [], "stealth click must NOT trigger physical click"
    assert "stealth" in out["output"]


def test_stealth_falls_back_when_postmessage_fails(fake_executor, monkeypatch):
    """If PostMessage can't reach the target, fall back to physical click."""
    monkeypatch.setattr(stealth_input, "is_available", lambda: True)
    monkeypatch.setattr(stealth_input, "post_click", lambda *a, **kw: False)
    ex = fake_executor(stealth=True)
    ex.execute_sync({"action": "click", "x": 50, "y": 60})
    assert any(c[0] == "click" for c in ex._desktop.calls), (
        "must fall back to physical click when stealth fails"
    )


def test_stealth_typing_uses_post_text(fake_executor, monkeypatch):
    monkeypatch.setattr(stealth_input, "is_available", lambda: True)
    calls = []
    monkeypatch.setattr(stealth_input, "post_text", lambda text, **kw: calls.append(text) or True)
    ex = fake_executor(stealth=True)
    ex.execute_sync({"action": "type_text", "text": "hello"})
    assert calls == ["hello"]
    assert all(c[0] != "type_text" for c in ex._desktop.calls)


def test_stealth_typing_still_blocks_sensitive_text(fake_executor, monkeypatch):
    """Sensitive-field protection still fires even in stealth mode."""
    monkeypatch.setattr(stealth_input, "is_available", lambda: True)
    ex = fake_executor(stealth=True)
    out = ex.execute_sync({"action": "type_text", "text": "my password is hunter2"})
    assert out["success"] is False
    assert out["error"] == "sensitive_field"


def test_stealth_press_named_key(fake_executor, monkeypatch):
    monkeypatch.setattr(stealth_input, "is_available", lambda: True)
    monkeypatch.setattr(stealth_input, "post_named_key", lambda name, **kw: True)
    ex = fake_executor(stealth=True)
    out = ex.execute_sync({"action": "press_key", "key": "enter"})
    assert "stealth" in out["output"]
    assert all(c[0] != "press_key" for c in ex._desktop.calls)


# ---- Stealth input: non-Windows / no-win32 fallback ----


def test_is_available_false_without_win32(monkeypatch):
    """Without win32 and without xdotool/macOS, is_available returns False."""
    monkeypatch.setattr(stealth_input, "_HAS_WIN32", False)
    monkeypatch.setattr(stealth_input, "is_linux", lambda: False)
    monkeypatch.setattr(stealth_input, "is_macos", lambda: False)
    assert stealth_input.is_available() is False


def test_post_click_returns_false_without_win32(monkeypatch):
    # v23: LinuxBackend now handles click, so 'no win32' alone isn't enough to
    # expect False. Neutralize the platform backend to test the genuine
    # 'no input subsystem' path on any host.
    monkeypatch.setattr(stealth_input, "_HAS_WIN32", False)
    monkeypatch.setattr(stealth_input, "get_backend", lambda: _NoInputBackend())
    assert stealth_input.post_click(100, 200) is False


def test_post_text_returns_false_without_win32(monkeypatch):
    """No Win32 AND no platform backend input → False.

    On Linux the platform backend now handles text (v23 cross-platform wiring),
    so 'no win32' alone isn't enough to expect False — we also neutralize the
    backend input to test the genuine 'no input subsystem available' path.
    """
    monkeypatch.setattr(stealth_input, "_HAS_WIN32", False)
    monkeypatch.setattr(stealth_input, "get_backend", lambda: _NoInputBackend())
    assert stealth_input.post_text("hello") is False


class _NoInputBackend:
    """Test double: a backend whose .input methods all return False / no-op.

    Lets the 'without win32' tests assert the False path on any platform
    regardless of whether a real LinuxBackend is present.
    """

    class _Input:
        def click(self, *a, **kw):
            return False

        def type_text(self, *a, **kw):
            return False

        def press_key(self, *a, **kw):
            return False

        def hotkey(self, *a, **kw):
            return False

        def scroll(self, *a, **kw):
            return False

    def __init__(self):
        self.input = self._Input()


def test_post_key_returns_false_without_win32(monkeypatch):
    monkeypatch.setattr(stealth_input, "_HAS_WIN32", False)
    assert stealth_input.post_key(0x0D) is False


def test_post_hotkey_returns_false_without_win32(monkeypatch):
    monkeypatch.setattr(stealth_input, "_HAS_WIN32", False)
    assert stealth_input.post_hotkey(["ctrl", "c"]) is False


def test_post_named_key_returns_false_without_win32(monkeypatch):
    monkeypatch.setattr(stealth_input, "_HAS_WIN32", False)
    assert stealth_input.post_named_key("enter") is False


def test_post_text_empty_string_returns_false(monkeypatch):
    """Even if win32 were available, empty string returns False."""
    monkeypatch.setattr(stealth_input, "_HAS_WIN32", True)
    assert stealth_input.post_text("") is False


def test_post_hotkey_empty_list_returns_false(monkeypatch):
    """Empty key list returns False even with win32."""
    monkeypatch.setattr(stealth_input, "_HAS_WIN32", True)
    assert stealth_input.post_hotkey([]) is False


def test_post_named_key_unknown_key_returns_false(monkeypatch):
    """Unknown key name with len > 1 returns False."""
    monkeypatch.setattr(stealth_input, "_HAS_WIN32", True)
    assert stealth_input.post_named_key("unknown_key") is False


@pytest.mark.skipif(sys.platform == "win32", reason="On Windows post_text succeeds")
def test_post_named_key_single_char_falls_back_to_post_text(monkeypatch):
    """Single-character key name falls through to post_text path."""
    # On Linux, win32gui is not imported so we can't fully test the path,
    # but we can verify that a single char doesn't hit VK_NAMES lookup
    from core.stealth_input import VK_NAMES

    assert "a" not in VK_NAMES  # single chars aren't in the lookup table
    # Neutralize the platform backend so the test asserts the genuine no-input
    # path on any host (v23 cross-platform wiring means LinuxBackend now handles
    # text, so without this stub the test would get True instead of False).
    monkeypatch.setattr(stealth_input, "get_backend", lambda: _NoInputBackend())
    # post_named_key("a") will try post_text, which returns False with no backend
    result = stealth_input.post_named_key("a")
    assert result is False


# ---- VK_NAMES mapping completeness ----


def test_vk_names_has_common_keys():
    from core.stealth_input import VK_NAMES

    for key in [
        "enter",
        "tab",
        "escape",
        "space",
        "backspace",
        "delete",
        "up",
        "down",
        "left",
        "right",
        "home",
        "end",
        "f1",
        "f12",
    ]:
        assert key in VK_NAMES, f"missing VK_NAMES entry for {key}"


def test_vk_names_values_are_ints():
    for name, vk in stealth_input.VK_NAMES.items():
        assert isinstance(vk, int), f"VK_NAMES[{name!r}] = {vk!r} not int"


def test_mod_vk_has_standard_modifiers():
    from core.stealth_input import _MOD_VK

    for mod in ["ctrl", "shift", "alt", "win"]:
        assert mod in _MOD_VK, f"missing modifier: {mod}"


# ---- Stealth hotkey through executor ----


def test_stealth_hotkey_uses_post_hotkey(fake_executor, monkeypatch):
    monkeypatch.setattr(stealth_input, "is_available", lambda: True)
    calls = []
    monkeypatch.setattr(stealth_input, "post_hotkey", lambda keys, **kw: calls.append(keys) or True)
    ex = fake_executor(stealth=True)
    out = ex.execute_sync({"action": "hotkey", "keys": ["ctrl", "c"]})
    assert calls == [["ctrl", "c"]]
    assert "stealth" in out["output"]


def test_stealth_hotkey_fallback_when_fails(fake_executor, monkeypatch):
    monkeypatch.setattr(stealth_input, "is_available", lambda: True)
    monkeypatch.setattr(stealth_input, "post_hotkey", lambda keys, **kw: False)
    ex = fake_executor(stealth=True)
    out = ex.execute_sync({"action": "hotkey", "keys": ["ctrl", "c"]})
    assert out["success"] is True
    assert any(c[0] == "hotkey" for c in ex._desktop.calls)
