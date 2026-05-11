"""Tests for ActionExecutor — sensitive filter, dry-run, unknown actions."""
import pytest

# Avoid importing pyautogui-touching modules by patching DesktopEngine at
# import time. The test executes only the routing logic that doesn't call
# into pyautogui.
from unittest import mock

import core.desktop as desktop_mod


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
        self.calls.append(("scroll", a, kw))


@pytest.fixture
def fake_executor(monkeypatch):
    monkeypatch.setattr(desktop_mod, "DesktopEngine", FakeDesktop)
    from core.action_executor import ActionExecutor
    return ActionExecutor


def test_unknown_action_returns_error(fake_executor):
    ex = fake_executor()
    out = ex.execute_sync({"action": "warp_drive"})
    assert out["success"] is False
    assert "unknown" in out.get("error", "").lower()


def test_sensitive_text_is_blocked(fake_executor):
    ex = fake_executor()
    out = ex.execute_sync({"action": "type_text", "text": "my password is hunter2"})
    assert out["success"] is False
    assert out.get("error") == "sensitive_field"


def test_dry_run_does_not_invoke_handler(fake_executor):
    ex = fake_executor(dry_run=True)
    out = ex.execute_sync({"action": "click", "x": 1, "y": 2})
    assert out["success"] is True
    assert out.get("dry_run") is True
    assert ex._desktop.calls == []  # no real click happened


def test_dry_run_still_runs_read_only_actions(fake_executor):
    ex = fake_executor(dry_run=True)
    # `note` is read-only — should still report success and not be marked dry_run.
    out = ex.execute_sync({"action": "note", "text": "hi"})
    assert out["success"] is True
    assert not out.get("dry_run")


def test_normal_click_routes_to_desktop(fake_executor):
    ex = fake_executor(dry_run=False)
    out = ex.execute_sync({"action": "click", "x": 5, "y": 6})
    assert out["success"] is True
    assert any(c[0] == "click" for c in ex._desktop.calls)


def test_pre_action_callback_fires_before_dispatch(fake_executor):
    seen = []
    ex = fake_executor(pre_action_callback=lambda a: seen.append(a["action"]))
    ex.execute_sync({"action": "click", "x": 1, "y": 2})
    ex.execute_sync({"action": "press_key", "key": "enter"})
    assert seen == ["click", "press_key"]


def test_pre_action_callback_failure_does_not_break_dispatch(fake_executor):
    def boom(_a):
        raise RuntimeError("kaboom")
    ex = fake_executor(pre_action_callback=boom)
    out = ex.execute_sync({"action": "click", "x": 1, "y": 2})
    assert out["success"] is True


def test_click_text_handler_returns_text_not_found_without_ocr(fake_executor,
                                                               monkeypatch):
    # When Tesseract isn't available, find_text returns None and the
    # handler must report a clean error rather than crashing.
    from core import ocr
    monkeypatch.setattr(ocr, "_have_tesseract", lambda: False)
    ex = fake_executor()
    out = ex.execute_sync({"action": "click_text", "text": "Send"})
    assert out["success"] is False
    assert out["error"] == "text_not_found"


def test_dispatch_has_new_uia_and_ocr_handlers(fake_executor):
    ex = fake_executor()
    for name in ("click_text", "read_text", "click_control", "set_text", "list_controls"):
        assert name in ex._dispatch_table, f"missing handler: {name}"
