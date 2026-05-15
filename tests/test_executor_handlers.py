"""Tests for ActionExecutor handler methods — note, finish, file ops, clipboard, etc."""

import pytest

import core.desktop as desktop_mod
from core.action_executor import (
    _contains_sensitive,
    _dry_run_result,
    _sanitize_params,
)


class FakeDesktop:
    """Minimal desktop stub that records calls."""

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

    def drag(self, *a, **kw):
        self.calls.append(("drag", a, kw))


@pytest.fixture
def fake_executor(monkeypatch):
    monkeypatch.setattr(desktop_mod, "DesktopEngine", FakeDesktop)
    from core.action_executor import ActionExecutor

    return ActionExecutor


# -------------------------------------------------------------------
# Module helpers
# -------------------------------------------------------------------


class TestContainsSensitive:
    @pytest.mark.parametrize(
        "text",
        ["my password is x", "api_key=123", "SSN: 000-00-0000", "credit_card=4111", "secret token"],
    )
    def test_detects_sensitive(self, text):
        assert _contains_sensitive(text) is True

    @pytest.mark.parametrize("text", ["hello world", "open chrome", "click button"])
    def test_allows_normal_text(self, text):
        assert _contains_sensitive(text) is False


class TestSanitizeParams:
    def test_truncates_long_strings(self):
        result = _sanitize_params({"data": "x" * 300})
        assert result["data"].endswith("...")
        assert len(result["data"]) == 203

    def test_passes_short_values_through(self):
        result = _sanitize_params({"x": 10, "y": 20})
        assert result == {"x": 10, "y": 20}

    def test_summarizes_large_dicts(self):
        big = {"k" + str(i): i for i in range(100)}
        result = _sanitize_params({"payload": big})
        assert "dict" in result["payload"]


class TestDryRunResult:
    def test_structure(self):
        result = _dry_run_result("click", {"x": 1, "y": 2})
        assert result["success"] is True
        assert result["dry_run"] is True
        assert "click" in result["output"]

    def test_truncates_long_preview(self):
        params = {f"key_{i}": "val" * 100 for i in range(10)}
        result = _dry_run_result("type_text", params)
        assert len(result["output"]) < 300


# -------------------------------------------------------------------
# Pure handler tests (no external deps)
# -------------------------------------------------------------------


class TestNote:
    def test_returns_success_with_text(self, fake_executor):
        ex = fake_executor()
        out = ex.execute_sync({"action": "note", "text": "observing screen"})
        assert out["success"] is True
        assert out["output"] == "observing screen"


class TestFinish:
    def test_returns_done_flag(self, fake_executor):
        ex = fake_executor()
        out = ex.execute_sync({"action": "finish", "summary": "task complete"})
        assert out["success"] is True
        assert out["done"] is True
        assert out["output"] == "task complete"

    def test_finish_without_summary(self, fake_executor):
        ex = fake_executor()
        out = ex.execute_sync({"action": "finish"})
        assert out["success"] is True
        assert out["done"] is True


class TestWait:
    def test_returns_success(self, fake_executor):
        ex = fake_executor()
        out = ex.execute_sync({"action": "wait", "seconds": 0.01})
        assert out["success"] is True
        assert "0.01" in out["output"]

    def test_caps_at_60_seconds(self, fake_executor):
        ex = fake_executor()
        # Use a mock to avoid actually sleeping 60s
        import time
        from unittest.mock import patch

        with patch.object(time, "sleep") as mock_sleep:
            out = ex.execute_sync({"action": "wait", "seconds": 999})
            mock_sleep.assert_called_once_with(60.0)
            assert out["success"] is True


class TestCloseApp:
    def test_returns_error_without_target(self, fake_executor):
        ex = fake_executor()
        out = ex.execute_sync({"action": "close_app"})
        assert out["success"] is False
        assert out["error"] == "missing_target"


# -------------------------------------------------------------------
# Handlers with mocked subsystems
# -------------------------------------------------------------------


class TestReadFile:
    def test_success(self, fake_executor, monkeypatch):
        from core import file_ops

        monkeypatch.setattr(file_ops, "read_file", lambda p: "file contents here")

        ex = fake_executor()
        out = ex.execute_sync({"action": "read_file", "path": "test.txt"})  # noqa: S108
        assert out["success"] is True
        assert out["output"] == "file contents here"

    def test_file_not_found(self, fake_executor, monkeypatch):
        from core import file_ops

        monkeypatch.setattr(file_ops, "read_file", lambda p: None)

        ex = fake_executor()
        out = ex.execute_sync({"action": "read_file", "path": "/nope.txt"})
        assert out["success"] is False
        assert out["error"] == "file_not_found"

    def test_read_failure(self, fake_executor, monkeypatch):
        from core import file_ops

        monkeypatch.setattr(
            file_ops, "read_file", lambda p: (_ for _ in ()).throw(RuntimeError("disk error"))
        )

        ex = fake_executor()
        out = ex.execute_sync({"action": "read_file", "path": "/bad"})
        assert out["success"] is False
        assert "read_file_failed" in out["error"]


class TestWriteFile:
    def test_success(self, fake_executor, monkeypatch):
        from core import file_ops

        monkeypatch.setattr(file_ops, "write_file", lambda p, c: True)

        ex = fake_executor()
        out = ex.execute_sync({"action": "write_file", "path": "out.txt", "content": "hello"})  # noqa: S108
        assert out["success"] is True

    def test_write_failure(self, fake_executor, monkeypatch):
        from core import file_ops

        monkeypatch.setattr(file_ops, "write_file", lambda p, c: False)

        ex = fake_executor()
        out = ex.execute_sync({"action": "write_file", "path": "out.txt", "content": "hello"})  # noqa: S108
        assert out["success"] is False


class TestListDirectory:
    def test_success(self, fake_executor, monkeypatch):
        from core import file_ops

        monkeypatch.setattr(file_ops, "list_directory", lambda p: ["a.txt", "b.txt"])

        ex = fake_executor()
        out = ex.execute_sync({"action": "list_directory", "path": "."})
        assert out["success"] is True
        assert out["output"] == ["a.txt", "b.txt"]

    def test_not_found(self, fake_executor, monkeypatch):
        from core import file_ops

        monkeypatch.setattr(file_ops, "list_directory", lambda p: None)

        ex = fake_executor()
        out = ex.execute_sync({"action": "list_directory", "path": "/nope"})
        assert out["success"] is False
        assert out["error"] == "dir_not_found"


class TestClipboardRead:
    def test_success(self, fake_executor, monkeypatch):
        from core import clipboard

        monkeypatch.setattr(clipboard, "clipboard_read", lambda: "copied text")

        ex = fake_executor()
        out = ex.execute_sync({"action": "clipboard_read"})
        assert out["success"] is True
        assert out["output"] == "copied text"

    def test_failure(self, fake_executor, monkeypatch):
        from core import clipboard

        monkeypatch.setattr(
            clipboard, "clipboard_read", lambda: (_ for _ in ()).throw(RuntimeError("no clipboard"))
        )

        ex = fake_executor()
        out = ex.execute_sync({"action": "clipboard_read"})
        assert out["success"] is False


class TestClipboardWrite:
    def test_success(self, fake_executor, monkeypatch):
        from core import clipboard

        monkeypatch.setattr(clipboard, "clipboard_write", lambda t: True)

        ex = fake_executor()
        out = ex.execute_sync({"action": "clipboard_write", "text": "hello"})
        assert out["success"] is True

    def test_failure(self, fake_executor, monkeypatch):
        from core import clipboard

        monkeypatch.setattr(clipboard, "clipboard_write", lambda t: False)

        ex = fake_executor()
        out = ex.execute_sync({"action": "clipboard_write", "text": "hello"})
        assert out["success"] is False


class TestSystemInfo:
    def test_success(self, fake_executor, monkeypatch):
        from core import system_info

        monkeypatch.setattr(system_info, "system_info", lambda: {"os": "Windows"})

        ex = fake_executor()
        out = ex.execute_sync({"action": "system_info"})
        assert out["success"] is True
        assert out["output"]["os"] == "Windows"

    def test_failure(self, fake_executor, monkeypatch):
        from core import system_info

        monkeypatch.setattr(
            system_info, "system_info", lambda: (_ for _ in ()).throw(RuntimeError("fail"))
        )

        ex = fake_executor()
        out = ex.execute_sync({"action": "system_info"})
        assert out["success"] is False


class TestListProcesses:
    def test_caps_at_100(self, fake_executor, monkeypatch):
        from core import process_manager

        procs = [{"pid": i, "name": f"proc_{i}"} for i in range(150)]
        monkeypatch.setattr(process_manager, "list_processes", lambda: procs)

        ex = fake_executor()
        out = ex.execute_sync({"action": "list_processes"})
        assert out["success"] is True
        assert len(out["output"]) == 100


class TestStartProcess:
    def test_success(self, fake_executor, monkeypatch):
        from core import process_manager

        monkeypatch.setattr(process_manager, "start_process", lambda p, a=None: 42)

        ex = fake_executor()
        out = ex.execute_sync({"action": "start_process", "path": "notepad.exe"})
        assert out["success"] is True
        assert "42" in out["output"]

    def test_failure(self, fake_executor, monkeypatch):
        from core import process_manager

        monkeypatch.setattr(process_manager, "start_process", lambda p, a=None: None)

        ex = fake_executor()
        out = ex.execute_sync({"action": "start_process", "path": "nonexistent.exe"})
        assert out["success"] is False


class TestKillProcess:
    def test_success(self, fake_executor, monkeypatch):
        from core import process_manager

        monkeypatch.setattr(process_manager, "kill_process", lambda t: True)

        ex = fake_executor()
        out = ex.execute_sync({"action": "kill_process", "pid": 1234})
        assert out["success"] is True

    def test_not_found(self, fake_executor, monkeypatch):
        from core import process_manager

        monkeypatch.setattr(process_manager, "kill_process", lambda t: False)

        ex = fake_executor()
        out = ex.execute_sync({"action": "kill_process", "name": "nope.exe"})
        assert out["success"] is False


class TestListWindows:
    def test_success(self, fake_executor, monkeypatch):
        from core import window_manager

        monkeypatch.setattr(
            window_manager, "list_windows", lambda: [{"title": "Chrome", "is_focused": True}]
        )

        ex = fake_executor()
        out = ex.execute_sync({"action": "list_windows"})
        assert out["success"] is True
        assert len(out["output"]) == 1


class TestFocusWindow:
    def test_success(self, fake_executor, monkeypatch):
        from core import window_manager

        monkeypatch.setattr(window_manager, "focus_window", lambda t: True)

        ex = fake_executor()
        out = ex.execute_sync({"action": "focus_window", "title": "Chrome"})
        assert out["success"] is True

    def test_not_found(self, fake_executor, monkeypatch):
        from core import window_manager

        monkeypatch.setattr(window_manager, "focus_window", lambda t: False)
        monkeypatch.setattr(window_manager, "list_windows", lambda: [])

        ex = fake_executor()
        out = ex.execute_sync({"action": "focus_window", "title": "Ghost"})
        assert out["success"] is False
        assert out["error"] == "window_not_found"


class TestCloseWindow:
    def test_success(self, fake_executor, monkeypatch):
        from core import window_manager

        monkeypatch.setattr(window_manager, "close_window", lambda t: True)

        ex = fake_executor()
        out = ex.execute_sync({"action": "close_window", "title": "Notepad"})
        assert out["success"] is True


class TestScreenshot:
    def test_success(self, fake_executor, monkeypatch):
        import core.action_executor as ae_mod

        monkeypatch.setattr(ae_mod, "capture_to_base64", lambda monitor=None: "fakebase64data")

        ex = fake_executor()
        out = ex.execute_sync({"action": "screenshot"})
        assert out["success"] is True
        assert out["screenshot"] == "fakebase64data"

    def test_failure(self, fake_executor, monkeypatch):
        import core.action_executor as ae_mod

        monkeypatch.setattr(
            ae_mod,
            "capture_to_base64",
            lambda monitor=None: (_ for _ in ()).throw(RuntimeError("no screen")),
        )

        ex = fake_executor()
        out = ex.execute_sync({"action": "screenshot"})
        assert out["success"] is False


class TestFindImage:
    def test_found(self, fake_executor, monkeypatch):
        import core.action_executor as ae_mod

        monkeypatch.setattr(ae_mod, "find_template", lambda t, c=0.8: (100, 200))

        ex = fake_executor()
        out = ex.execute_sync({"action": "find_image", "template_path": "btn.png"})
        assert out["success"] is True
        assert out["position"] == [100, 200]

    def test_not_found(self, fake_executor, monkeypatch):
        import core.action_executor as ae_mod

        monkeypatch.setattr(ae_mod, "find_template", lambda t, c=0.8: None)

        ex = fake_executor()
        out = ex.execute_sync({"action": "find_image", "template_path": "missing.png"})
        assert out["success"] is False
        assert out["error"] == "image_not_found"


# -------------------------------------------------------------------
# Click offset and dispatch routing
# -------------------------------------------------------------------


class TestClickOffset:
    def test_offset_applied_to_click(self, fake_executor):
        ex = fake_executor(click_offset=(100, 50))
        out = ex.execute_sync({"action": "click", "x": 10, "y": 20})
        assert out["success"] is True
        # FakeDesktop records the actual args passed
        call = ex._desktop.calls[0]
        assert call[1][0] == 110  # x + offset_x
        assert call[1][1] == 70  # y + offset_y


class TestLogProperty:
    def test_log_records_entries(self, fake_executor):
        ex = fake_executor()
        ex.execute_sync({"action": "note", "text": "first"})
        ex.execute_sync({"action": "note", "text": "second"})
        assert len(ex.log) == 2
        assert ex.log[0]["action"] == "note"
        assert ex.log[1]["action"] == "note"

    def test_log_includes_success_flag(self, fake_executor):
        ex = fake_executor()
        ex.execute_sync({"action": "note", "text": "ok"})
        ex.execute_sync({"action": "warp_drive"})
        assert ex.log[0]["success"] is True
        assert ex.log[1]["success"] is False


class TestDispatchAliases:
    def test_double_click_alias(self, fake_executor):
        ex = fake_executor()
        out = ex.execute_sync({"action": "double_click", "x": 5, "y": 5})
        assert out["success"] is True
        assert any(c[0] == "click" for c in ex._desktop.calls)

    def test_right_click_alias(self, fake_executor):
        ex = fake_executor()
        out = ex.execute_sync({"action": "right_click", "x": 5, "y": 5})
        assert out["success"] is True


class TestTypeTextBlocked:
    def test_set_text_blocks_sensitive(self, fake_executor):
        ex = fake_executor()
        out = ex.execute_sync({"action": "set_text", "text": "my password", "name": "field"})
        assert out["success"] is False
        assert out["error"] == "sensitive_field"


class TestPressKey:
    def test_press_key_routes_to_desktop(self, fake_executor):
        ex = fake_executor()
        out = ex.execute_sync({"action": "press_key", "key": "enter"})
        assert out["success"] is True
        assert any(c[0] == "press_key" for c in ex._desktop.calls)


class TestHotkey:
    def test_hotkey_routes_to_desktop(self, fake_executor):
        ex = fake_executor()
        out = ex.execute_sync({"action": "hotkey", "keys": ["ctrl", "c"]})
        assert out["success"] is True
        assert any(c[0] == "hotkey" for c in ex._desktop.calls)


class TestScroll:
    def test_scroll_routes_to_desktop(self, fake_executor):
        ex = fake_executor()
        out = ex.execute_sync({"action": "scroll", "amount": 3})
        assert out["success"] is True
        assert any(c[0] == "scroll" for c in ex._desktop.calls)
