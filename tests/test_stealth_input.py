"""Tests for stealth-input routing through ActionExecutor."""
import pytest
import core.desktop as desktop_mod
from core import stealth_input


class FakeDesktop:
    def __init__(self):
        self.calls = []
    def click(self, *a, **kw): self.calls.append(("click", a, kw))
    def type_text(self, text, **_): self.calls.append(("type_text", text))
    def press_key(self, key): self.calls.append(("press_key", key))
    def hotkey(self, *keys): self.calls.append(("hotkey", keys))
    def scroll(self, *a, **kw): pass


@pytest.fixture
def fake_executor(monkeypatch):
    monkeypatch.setattr(desktop_mod, "DesktopEngine", FakeDesktop)
    from core.action_executor import ActionExecutor
    return ActionExecutor


def test_stealth_off_uses_physical_input(fake_executor, monkeypatch):
    """When stealth=False, _click still goes through pyautogui-style desktop."""
    monkeypatch.setattr(stealth_input, "is_available", lambda: True)
    monkeypatch.setattr(stealth_input, "post_click", lambda *a, **kw: True)
    ex = fake_executor(stealth=False)
    ex.execute_sync({"action": "click", "x": 100, "y": 200})
    assert any(c[0] == "click" for c in ex._desktop.calls), \
        "stealth=False should hit physical desktop click"


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
    assert any(c[0] == "click" for c in ex._desktop.calls), \
        "must fall back to physical click when stealth fails"


def test_stealth_typing_uses_post_text(fake_executor, monkeypatch):
    monkeypatch.setattr(stealth_input, "is_available", lambda: True)
    calls = []
    monkeypatch.setattr(stealth_input, "post_text",
                        lambda text, **kw: calls.append(text) or True)
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
    monkeypatch.setattr(stealth_input, "post_named_key",
                        lambda name, **kw: True)
    ex = fake_executor(stealth=True)
    out = ex.execute_sync({"action": "press_key", "key": "enter"})
    assert "stealth" in out["output"]
    assert all(c[0] != "press_key" for c in ex._desktop.calls)
